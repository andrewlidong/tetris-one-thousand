#!/usr/bin/env python3
"""
Tetris × 1000 — Server
Supports up to 1000 concurrent WebSocket players with asyncio + aiohttp.
"""

import asyncio
import logging
import random
import time
from pathlib import Path

import aiohttp
from aiohttp import web

# Use orjson when available (5-10x faster than stdlib json)
try:
    import orjson as _json_lib
    def _dumps(obj: object) -> str:
        return _json_lib.dumps(obj).decode()
    def _loads(s: str) -> object:
        return _json_lib.loads(s)
except ImportError:
    import json as _json_lib  # type: ignore[no-redef]
    def _dumps(obj: object) -> str:
        return _json_lib.dumps(obj)
    def _loads(s: str) -> object:
        return _json_lib.loads(s)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Board constants ────────────────────────────────────────────────────────────

W = 10   # board width
H = 20   # board height

# ── Piece definitions (4 rotations each) ──────────────────────────────────────
# Each rotation is a list of rows; 1 = filled cell.

PIECES = [
    # 0 I (cyan)
    [
        [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],
        [[0,0,1,0],[0,0,1,0],[0,0,1,0],[0,0,1,0]],
        [[0,0,0,0],[0,0,0,0],[1,1,1,1],[0,0,0,0]],
        [[0,1,0,0],[0,1,0,0],[0,1,0,0],[0,1,0,0]],
    ],
    # 1 O (yellow) — same all rotations
    [[[0,1,1,0],[0,1,1,0],[0,0,0,0]]] * 4,
    # 2 T (purple)
    [
        [[0,1,0],[1,1,1],[0,0,0]],
        [[0,1,0],[0,1,1],[0,1,0]],
        [[0,0,0],[1,1,1],[0,1,0]],
        [[0,1,0],[1,1,0],[0,1,0]],
    ],
    # 3 S (green)
    [
        [[0,1,1],[1,1,0],[0,0,0]],
        [[0,1,0],[0,1,1],[0,0,1]],
        [[0,0,0],[0,1,1],[1,1,0]],
        [[1,0,0],[1,1,0],[0,1,0]],
    ],
    # 4 Z (red)
    [
        [[1,1,0],[0,1,1],[0,0,0]],
        [[0,0,1],[0,1,1],[0,1,0]],
        [[0,0,0],[1,1,0],[0,1,1]],
        [[0,1,0],[1,1,0],[1,0,0]],
    ],
    # 5 J (blue)
    [
        [[1,0,0],[1,1,1],[0,0,0]],
        [[0,1,1],[0,1,0],[0,1,0]],
        [[0,0,0],[1,1,1],[0,0,1]],
        [[0,1,0],[0,1,0],[1,1,0]],
    ],
    # 6 L (orange)
    [
        [[0,0,1],[1,1,1],[0,0,0]],
        [[0,1,0],[0,1,0],[0,1,1]],
        [[0,0,0],[1,1,1],[1,0,0]],
        [[1,1,0],[0,1,0],[0,1,0]],
    ],
]

# Color index per piece type (1-7); 8 = garbage gray
PIECE_COLORS = [1, 2, 3, 4, 5, 6, 7]
GARBAGE_COLOR = 8

# Lines → garbage sent to a random opponent
GARBAGE_TABLE = {1: 0, 2: 1, 3: 2, 4: 4}


# ── TetrisGame ─────────────────────────────────────────────────────────────────

class TetrisGame:
    """All server-side logic for one player's board."""

    def __init__(self, player_id: int) -> None:
        self.player_id = player_id
        self.board: list[list[int]] = [[0] * W for _ in range(H)]
        self.score = 0
        self.level = 1
        self.lines_cleared = 0
        self.alive = True

        # Piece bag (7-bag randomizer)
        self._bag: list[int] = []
        self.next_pieces: list[int] = []
        self.held: int | None = None
        self.hold_used = False

        # Active piece
        self.ptype = 0
        self.prot = 0
        self.px = 0
        self.py = 0

        # Garbage queue
        self.garbage_in = 0   # incoming (to receive on next lock)
        self.garbage_out = 0  # outgoing (server will distribute)

        # Gravity
        self._last_gravity = time.monotonic()

        # Seed with two bags, then fill next queue and spawn
        self._refill()
        self._refill()
        for _ in range(5):
            self.next_pieces.append(self._draw())
        self._spawn()

    # ── Bag randomizer ──────────────────────────────────────────────────────

    def _refill(self) -> None:
        bag = list(range(7))
        random.shuffle(bag)
        self._bag.extend(bag)

    def _draw(self) -> int:
        if len(self._bag) < 7:
            self._refill()
        return self._bag.pop(0)

    # ── Spawn / cells / validity ─────────────────────────────────────────────

    def _spawn(self) -> None:
        self.next_pieces.append(self._draw())
        self.ptype = self.next_pieces.pop(0)
        self.prot = 0
        shape = PIECES[self.ptype][0]
        self.px = (W - len(shape[0])) // 2
        self.py = 0
        self.hold_used = False
        if not self._valid(self.ptype, self.prot, self.px, self.py):
            self.alive = False

    def _cells(self, ptype: int, prot: int, px: int, py: int) -> list[tuple[int, int]]:
        return [
            (px + c, py + r)
            for r, row in enumerate(PIECES[ptype][prot])
            for c, v in enumerate(row)
            if v
        ]

    def _valid(self, ptype: int, prot: int, px: int, py: int) -> bool:
        for cx, cy in self._cells(ptype, prot, px, py):
            if cx < 0 or cx >= W or cy >= H:
                return False
            if cy >= 0 and self.board[cy][cx]:
                return False
        return True

    def _ghost_y(self) -> int:
        y = self.py
        while self._valid(self.ptype, self.prot, self.px, y + 1):
            y += 1
        return y

    # ── Player actions ───────────────────────────────────────────────────────

    def move_left(self) -> None:
        if self.alive and self._valid(self.ptype, self.prot, self.px - 1, self.py):
            self.px -= 1

    def move_right(self) -> None:
        if self.alive and self._valid(self.ptype, self.prot, self.px + 1, self.py):
            self.px += 1

    def soft_drop(self) -> None:
        if not self.alive:
            return
        if self._valid(self.ptype, self.prot, self.px, self.py + 1):
            self.py += 1
            self.score += 1
        else:
            self._lock()

    def hard_drop(self) -> None:
        if not self.alive:
            return
        gy = self._ghost_y()
        self.score += (gy - self.py) * 2
        self.py = gy
        self._lock()

    def rotate_cw(self) -> None:
        if not self.alive:
            return
        new_rot = (self.prot + 1) % 4
        for dx, dy in [(0,0),(-1,0),(1,0),(0,-1),(-2,0),(2,0),(0,-2)]:
            if self._valid(self.ptype, new_rot, self.px + dx, self.py + dy):
                self.prot, self.px, self.py = new_rot, self.px + dx, self.py + dy
                return

    def rotate_ccw(self) -> None:
        if not self.alive:
            return
        new_rot = (self.prot - 1) % 4
        for dx, dy in [(0,0),(1,0),(-1,0),(0,-1),(2,0),(-2,0),(0,-2)]:
            if self._valid(self.ptype, new_rot, self.px + dx, self.py + dy):
                self.prot, self.px, self.py = new_rot, self.px + dx, self.py + dy
                return

    def hold(self) -> None:
        if not self.alive or self.hold_used:
            return
        self.hold_used = True
        if self.held is None:
            self.held = self.ptype
            self._spawn()
        else:
            self.ptype, self.held = self.held, self.ptype
            self.prot = 0
            shape = PIECES[self.ptype][0]
            self.px = (W - len(shape[0])) // 2
            self.py = 0

    # ── Lock / line clear / garbage ──────────────────────────────────────────

    def _lock(self) -> None:
        color = PIECE_COLORS[self.ptype]
        for cx, cy in self._cells(self.ptype, self.prot, self.px, self.py):
            if 0 <= cy < H and 0 <= cx < W:
                self.board[cy][cx] = color

        # Clear complete lines
        new_board = [row for row in self.board if not all(row)]
        cleared = H - len(new_board)
        if cleared:
            new_board[:0] = [[0] * W for _ in range(cleared)]
            self.board = new_board
            self.lines_cleared += cleared
            self.level = self.lines_cleared // 10 + 1
            score_table = [0, 100, 300, 500, 800]
            self.score += score_table[min(cleared, 4)] * self.level
            sent = GARBAGE_TABLE.get(cleared, 4)
            # Cancel out incoming garbage first
            cancel = min(sent, self.garbage_in)
            sent -= cancel
            self.garbage_in -= cancel
            self.garbage_out += sent

        # Apply incoming garbage
        if self.garbage_in > 0:
            lines = min(self.garbage_in, H - 1)
            self.garbage_in -= lines
            self.board = self.board[lines:]
            gap = random.randrange(W)
            for _ in range(lines):
                row = [GARBAGE_COLOR] * W
                row[gap] = 0
                self.board.append(row)

        self._spawn()

    # ── Gravity ──────────────────────────────────────────────────────────────

    def gravity_tick(self) -> bool:
        """Apply gravity if enough time has passed. Returns True if piece moved/locked."""
        if not self.alive:
            return False
        now = time.monotonic()
        interval = max(0.05, 1.0 / self.level)
        if now - self._last_gravity < interval:
            return False
        self._last_gravity = now
        old_y = self.py
        if self._valid(self.ptype, self.prot, self.px, self.py + 1):
            self.py += 1
        else:
            self._lock()
        return True

    # ── State serialization ──────────────────────────────────────────────────

    def get_state(self) -> dict:
        """Full state for the owning player."""
        # Encode board with ghost: negative color = ghost
        board = [row[:] for row in self.board]
        if self.alive:
            gy = self._ghost_y()
            for cx, cy in self._cells(self.ptype, self.prot, self.px, gy):
                if 0 <= cy < H and 0 <= cx < W and not board[cy][cx]:
                    board[cy][cx] = -(PIECE_COLORS[self.ptype])
        return {
            "board": board,
            "piece": {"type": self.ptype, "rot": self.prot, "x": self.px, "y": self.py},
            "held": self.held,
            "next": self.next_pieces[:5],
            "score": self.score,
            "level": self.level,
            "lines": self.lines_cleared,
            "alive": self.alive,
            "garbage_in": self.garbage_in,
        }

    def encode_preview(self) -> str:
        """Compact 200-char board string for the overview broadcast (0-8 per cell)."""
        board = [row[:] for row in self.board]
        if self.alive:
            color = PIECE_COLORS[self.ptype]
            for cx, cy in self._cells(self.ptype, self.prot, self.px, self.py):
                if 0 <= cy < H and 0 <= cx < W:
                    board[cy][cx] = color
        return "".join(str(cell) for row in board for cell in row)


# ── GameServer ─────────────────────────────────────────────────────────────────

# How many sends to gather concurrently. Keeps per-broadcast memory bounded.
_BROADCAST_CHUNK = 50

# Max input messages accepted per player per second (token-bucket ceiling)
_MAX_MOVES_PER_SEC = 20


class GameServer:
    def __init__(self) -> None:
        self._players: dict[int, dict] = {}
        self._next_id = 1

    # ── WebSocket handler ────────────────────────────────────────────────────

    async def ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30, max_msg_size=64 * 1024)
        await ws.prepare(request)

        pid = self._next_id
        self._next_id += 1
        self._players[pid] = {
            "ws": ws,
            "game": TetrisGame(pid),
            "name": f"Player{pid}",
            # Rate limiting: track move timestamps in a small ring
            "_move_times": [],
        }
        log.info("[+] player %d  total=%d", pid, len(self._players))

        try:
            await ws.send_str(_dumps({"type": "init", "player_id": pid}))
            await self._send_state(pid)

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        await self._on_message(pid, _loads(msg.data))
                    except Exception as exc:
                        log.debug("message error pid=%d: %s", pid, exc)
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                    break
        except Exception as exc:
            log.debug("ws error pid=%d: %s", pid, exc)
        finally:
            self._players.pop(pid, None)
            log.info("[-] player %d  total=%d", pid, len(self._players))

        return ws

    # ── Message handling ─────────────────────────────────────────────────────

    async def _on_message(self, pid: int, data: dict) -> None:
        p = self._players.get(pid)
        if not p:
            return
        game: TetrisGame = p["game"]
        mtype = data.get("type")

        if mtype == "input":
            if not game.alive:
                return
            # Token-bucket rate limit: drop excess inputs beyond _MAX_MOVES_PER_SEC
            now_ts = time.monotonic()
            times = p["_move_times"]
            times.append(now_ts)
            cutoff = now_ts - 1.0
            # Prune entries older than 1 second
            while times and times[0] < cutoff:
                times.pop(0)
            if len(times) > _MAX_MOVES_PER_SEC:
                return
            action = data.get("action", "")
            if   action == "left":       game.move_left()
            elif action == "right":      game.move_right()
            elif action == "down":       game.soft_drop()
            elif action == "hard_drop":  game.hard_drop()
            elif action == "rotate_cw":  game.rotate_cw()
            elif action == "rotate_ccw": game.rotate_ccw()
            elif action == "hold":       game.hold()
            await self._send_state(pid)
            await self._distribute_garbage(pid)

        elif mtype == "restart":
            p["game"] = TetrisGame(pid)
            await self._send_state(pid)

        elif mtype == "name":
            raw = str(data.get("name", "")).strip()[:20]
            if raw:
                p["name"] = raw

    # ── State / garbage helpers ──────────────────────────────────────────────

    async def _send_state(self, pid: int) -> None:
        p = self._players.get(pid)
        if not p:
            return
        msg = p["game"].get_state()
        msg["type"] = "state"
        try:
            await p["ws"].send_str(_dumps(msg))
        except Exception:
            pass

    async def _distribute_garbage(self, pid: int) -> None:
        p = self._players.get(pid)
        if not p or p["game"].garbage_out <= 0:
            return
        lines = p["game"].garbage_out
        p["game"].garbage_out = 0
        targets = [q for qid, q in self._players.items()
                   if qid != pid and q["game"].alive]
        if targets:
            random.choice(targets)["game"].garbage_in += lines

    # ── Game loop ────────────────────────────────────────────────────────────

    async def game_loop(self) -> None:
        last_broadcast = 0.0

        while True:
            await asyncio.sleep(0.05)   # 20 Hz

            # Gravity for all alive players
            updated: list[int] = []
            for pid, p in list(self._players.items()):
                game: TetrisGame = p["game"]
                if game.alive and game.gravity_tick():
                    updated.append(pid)
                    if game.garbage_out > 0:
                        await self._distribute_garbage(pid)

            # Send state to players whose piece moved due to gravity (chunked)
            for i in range(0, len(updated), _BROADCAST_CHUNK):
                chunk = updated[i : i + _BROADCAST_CHUNK]
                await asyncio.gather(
                    *[self._send_state(pid) for pid in chunk],
                    return_exceptions=True,
                )

            # Broadcast overview at ~2 Hz
            now = time.monotonic()
            if now - last_broadcast >= 0.5:
                last_broadcast = now
                await self._broadcast_overview()

    # ── Overview broadcast ───────────────────────────────────────────────────

    async def _broadcast_overview(self) -> None:
        if not self._players:
            return

        alive_count = sum(1 for p in self._players.values() if p["game"].alive)

        # Sort by score descending
        ranked = sorted(
            self._players.items(),
            key=lambda kv: (-kv[1]["game"].score, not kv[1]["game"].alive),
        )

        leaderboard = [
            {
                "id": pid,
                "name": p["name"],
                "score": p["game"].score,
                "level": p["game"].level,
                "lines": p["game"].lines_cleared,
                "alive": p["game"].alive,
            }
            for pid, p in ranked[:50]
        ]

        # Compact board previews for top 80 alive players
        boards: dict[str, dict] = {}
        alive_ranked = [(pid, p) for pid, p in ranked if p["game"].alive]
        for pid, p in alive_ranked[:80]:
            boards[str(pid)] = {
                "name": p["name"],
                "score": p["game"].score,
                "b": p["game"].encode_preview(),  # compact 200-char string
            }

        payload = _dumps({
            "type": "overview",
            "total": len(self._players),
            "alive": alive_count,
            "leaderboard": leaderboard,
            "boards": boards,
        })

        # Chunked gather: bound the number of concurrent send coroutines to
        # avoid excessive memory allocation when fan-out reaches 1000 clients.
        dead: list[int] = []
        items = list(self._players.items())
        for i in range(0, len(items), _BROADCAST_CHUNK):
            chunk = items[i : i + _BROADCAST_CHUNK]
            await asyncio.gather(
                *[self._send_raw(pid, p, payload, dead) for pid, p in chunk],
                return_exceptions=True,
            )
        for pid in dead:
            self._players.pop(pid, None)

    @staticmethod
    async def _send_raw(pid: int, p: dict, payload: str, dead: list) -> None:
        try:
            await p["ws"].send_str(payload)
        except Exception:
            dead.append(pid)


# ── HTTP app setup ─────────────────────────────────────────────────────────────

async def build_app() -> web.Application:
    server = GameServer()
    # Disable per-message WebSocket compression: at 1000 clients, per-message
    # deflate adds ~50µs CPU per send, totalling ~50ms per broadcast cycle.
    app = web.Application(client_max_size=64 * 1024)
    app.router.add_get("/ws", server.ws_handler)
    app.router.add_get("/", lambda _: web.FileResponse(Path("static/index.html")))
    app.router.add_static("/", Path("static"))

    async def start_game_loop(app: web.Application) -> None:
        app["game_loop"] = asyncio.create_task(server.game_loop())

    async def stop_game_loop(app: web.Application) -> None:
        app["game_loop"].cancel()

    app.on_startup.append(start_game_loop)
    app.on_cleanup.append(stop_game_loop)
    return app


async def main() -> None:
    app = await build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8765)
    await site.start()
    log.info("Tetris × 1000 running at http://0.0.0.0:8765")
    await asyncio.Event().wait()


if __name__ == "__main__":
    # Install uvloop when available: drop-in asyncio replacement, ~2x faster I/O
    try:
        import uvloop
        uvloop.install()
        log.info("uvloop active")
    except ImportError:
        pass
    asyncio.run(main())
