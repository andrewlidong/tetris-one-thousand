#!/usr/bin/env python3
"""
Tetris × 1000 — Cooperative Massive Board
All players share a single 100×30 board. Work together to clear lines!
Active pieces pass through each other; only the settled board blocks movement.
"""

import asyncio
import logging
import random
import time
from pathlib import Path

import aiohttp
from aiohttp import web

try:
    import orjson as _jlib
    def _dumps(o): return _jlib.dumps(o).decode()
    def _loads(s): return _jlib.loads(s)
except ImportError:
    import json as _jlib  # type: ignore[no-redef]
    def _dumps(o): return _jlib.dumps(o)
    def _loads(s): return _jlib.loads(s)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Shared board dimensions ────────────────────────────────────────────────────
W = 100   # 10× standard width
H = 30    # board height

# ── Piece definitions (4 rotations each) ──────────────────────────────────────
PIECES = [
    # 0 I (cyan)
    [
        [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],
        [[0,0,1,0],[0,0,1,0],[0,0,1,0],[0,0,1,0]],
        [[0,0,0,0],[0,0,0,0],[1,1,1,1],[0,0,0,0]],
        [[0,1,0,0],[0,1,0,0],[0,1,0,0],[0,1,0,0]],
    ],
    # 1 O (yellow)
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

PIECE_COLORS = [1, 2, 3, 4, 5, 6, 7]

# Scoring for line clears (shared bonus for all alive players)
LINE_SCORE = [0, 100, 300, 500, 800]

_BROADCAST_CHUNK = 50
_MAX_MOVES_PER_SEC = 20
_GRAVITY_INTERVAL = 2.0   # seconds; slow so players have time to maneuver


# ── SharedBoard ────────────────────────────────────────────────────────────────

class SharedBoard:
    """The single board all players place pieces on."""

    def __init__(self) -> None:
        self.cells: list[list[int]] = [[0] * W for _ in range(H)]
        self.total_lines = 0
        self.dirty = True   # True = encode and broadcast on next world tick

    def can_place(self, cells: list[tuple[int, int]]) -> bool:
        """Check against board boundaries and settled cells only.
        Active pieces are transparent to each other."""
        for cx, cy in cells:
            if cx < 0 or cx >= W or cy >= H:
                return False
            if cy >= 0 and self.cells[cy][cx]:
                return False
        return True

    def lock(self, cells: list[tuple[int, int]], color: int) -> int:
        """Place cells on board, clear completed lines, return count cleared."""
        for cx, cy in cells:
            if 0 <= cy < H and 0 <= cx < W:
                self.cells[cy][cx] = color
        cleared = self._clear_lines()
        if cleared:
            self.dirty = True
        else:
            self.dirty = True   # still dirty from the lock itself
        return cleared

    def _clear_lines(self) -> int:
        full = [row for row in self.cells if all(row)]
        count = len(full)
        if count:
            self.cells = [row for row in self.cells if not all(row)]
            self.cells[:0] = [[0] * W for _ in range(count)]
            self.total_lines += count
        return count

    def encode(self) -> str:
        """3000-char hex string. Each cell → one hex digit (0-8 fit in '0'-'8')."""
        return "".join(hex(c)[2:] for row in self.cells for c in row)


# ── ActivePiecesOverlay ────────────────────────────────────────────────────────

class ActivePiecesOverlay:
    """Tracks every player's active (unsettled) piece cells.

    O(1) per-cell lookup so _valid() stays fast even at 1000 players.
    Internally maintains two indices:
      _by_player : pid  → frozenset of (cx, cy) currently occupied
      _by_cell   : cell → set of pids occupying that cell
    """

    def __init__(self) -> None:
        self._by_player: dict[int, frozenset[tuple[int, int]]] = {}
        self._by_cell:   dict[tuple[int, int], set[int]]       = {}

    def update(self, pid: int, cells: list[tuple[int, int]]) -> None:
        """Replace pid's footprint with the new cell list."""
        self._clear(pid)
        bounded = frozenset((cx, cy) for cx, cy in cells if 0 <= cy < H and 0 <= cx < W)
        self._by_player[pid] = bounded
        for cell in bounded:
            self._by_cell.setdefault(cell, set()).add(pid)

    def remove(self, pid: int) -> None:
        """Erase pid's footprint entirely (on lock or disconnect)."""
        self._clear(pid)
        self._by_player.pop(pid, None)

    def _clear(self, pid: int) -> None:
        for cell in self._by_player.get(pid, frozenset()):
            occupants = self._by_cell.get(cell)
            if occupants:
                occupants.discard(pid)
                if not occupants:
                    del self._by_cell[cell]

    def blocks(self, pid: int, cx: int, cy: int) -> bool:
        """True if (cx, cy) is occupied by someone other than pid."""
        occupants = self._by_cell.get((cx, cy))
        return bool(occupants and any(p != pid for p in occupants))


# ── PlayerPiece ────────────────────────────────────────────────────────────────

class PlayerPiece:
    """One player's active piece on the shared board."""

    def __init__(self, player_id: int, board: SharedBoard,
                 overlay: ActivePiecesOverlay) -> None:
        self.player_id = player_id
        self.board   = board
        self.overlay = overlay
        self.color = (player_id % 7) + 1   # deterministic 1-7 assignment

        self._bag: list[int] = []
        self.next: list[int] = []
        self.held: int | None = None
        self.hold_used = False

        self.ptype = 0
        self.prot = 0
        self.px = 0
        self.py = 0

        self.alive = True
        self.score = 0
        self._last_gravity = time.monotonic()

        self._refill()
        self._refill()
        for _ in range(5):
            self.next.append(self._draw())
        self._spawn()

    # ── Bag ──────────────────────────────────────────────────────────────────

    def _refill(self) -> None:
        bag = list(range(7))
        random.shuffle(bag)
        self._bag.extend(bag)

    def _draw(self) -> int:
        if len(self._bag) < 7:
            self._refill()
        return self._bag.pop(0)

    # ── Cell helpers ─────────────────────────────────────────────────────────

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
            if cy >= 0 and self.board.cells[cy][cx]:
                return False
            if cy >= 0 and self.overlay.blocks(self.player_id, cx, cy):
                return False
        return True

    def _sync_overlay(self) -> None:
        """Push current piece position into the shared overlay."""
        if self.alive:
            self.overlay.update(self.player_id, self._cells(self.ptype, self.prot, self.px, self.py))
        else:
            self.overlay.remove(self.player_id)

    def _ghost_y(self) -> int:
        y = self.py
        while self._valid(self.ptype, self.prot, self.px, y + 1):
            y += 1
        return y

    # ── Spawn ────────────────────────────────────────────────────────────────

    def _spawn(self) -> None:
        self.next.append(self._draw())
        self.ptype = self.next.pop(0)
        self.prot = 0
        shape = PIECES[self.ptype][0]
        pw = len(shape[0])
        # Spread spawns across the wide board
        self.px = random.randint(0, max(0, W - pw))
        self.py = 0
        self.hold_used = False
        if not self._valid(self.ptype, 0, self.px, 0):
            self.alive = False
        self._sync_overlay()

    # ── Player actions ───────────────────────────────────────────────────────

    def move_left(self) -> None:
        if self.alive and self._valid(self.ptype, self.prot, self.px - 1, self.py):
            self.px -= 1
            self._sync_overlay()

    def move_right(self) -> None:
        if self.alive and self._valid(self.ptype, self.prot, self.px + 1, self.py):
            self.px += 1
            self._sync_overlay()

    def soft_drop(self) -> int:
        if not self.alive:
            return 0
        if self._valid(self.ptype, self.prot, self.px, self.py + 1):
            self.py += 1
            self.score += 1
            self._sync_overlay()
            return 0
        return self._lock()

    def hard_drop(self) -> int:
        if not self.alive:
            return 0
        gy = self._ghost_y()
        self.score += (gy - self.py) * 2
        self.py = gy
        self._sync_overlay()
        return self._lock()

    def rotate_cw(self) -> None:
        if not self.alive:
            return
        new_rot = (self.prot + 1) % 4
        for dx, dy in [(0,0),(-1,0),(1,0),(0,-1),(-2,0),(2,0),(0,-2)]:
            if self._valid(self.ptype, new_rot, self.px + dx, self.py + dy):
                self.prot, self.px, self.py = new_rot, self.px + dx, self.py + dy
                self._sync_overlay()
                return

    def rotate_ccw(self) -> None:
        if not self.alive:
            return
        new_rot = (self.prot - 1) % 4
        for dx, dy in [(0,0),(1,0),(-1,0),(0,-1),(2,0),(-2,0),(0,-2)]:
            if self._valid(self.ptype, new_rot, self.px + dx, self.py + dy):
                self.prot, self.px, self.py = new_rot, self.px + dx, self.py + dy
                self._sync_overlay()
                return

    def hold(self) -> None:
        if not self.alive or self.hold_used:
            return
        self.hold_used = True
        if self.held is None:
            self.held = self.ptype
            self._spawn()   # _spawn calls _sync_overlay
        else:
            self.ptype, self.held = self.held, self.ptype
            self.prot = 0
            shape = PIECES[self.ptype][0]
            pw = len(shape[0])
            if not self._valid(self.ptype, 0, self.px, 0):
                self.px = random.randint(0, max(0, W - pw))
            self.py = 0
            self._sync_overlay()

    def _lock(self) -> int:
        # Remove from overlay before writing to settled board so that
        # other players' _valid() checks don't double-count this piece.
        self.overlay.remove(self.player_id)
        cells = self._cells(self.ptype, self.prot, self.px, self.py)
        cleared = self.board.lock(cells, self.color)
        self.score += 10  # base placement bonus
        self._spawn()     # registers new piece in overlay (or marks dead)
        return cleared

    # ── Gravity ──────────────────────────────────────────────────────────────

    def gravity_tick(self) -> tuple[bool, int]:
        """Apply gravity. Returns (moved, lines_cleared).
        moved=False means the interval hasn't elapsed yet — skip state send."""
        if not self.alive:
            return False, 0
        now = time.monotonic()
        if now - self._last_gravity < _GRAVITY_INTERVAL:
            return False, 0
        self._last_gravity = now
        if self._valid(self.ptype, self.prot, self.px, self.py + 1):
            self.py += 1
            self._sync_overlay()
            return True, 0
        return True, self._lock()

    # ── State ────────────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        return {
            "piece": {
                "type": self.ptype,
                "rot": self.prot,
                "x": self.px,
                "y": self.py,
                "ghost_y": self._ghost_y() if self.alive else self.py,
            },
            "held": self.held,
            "next": self.next[:5],
            "score": self.score,
            "alive": self.alive,
            "color": self.color,
        }

    def as_piece_entry(self) -> list:
        """Compact [pid, px, py, ptype, prot, color] for world broadcast."""
        return [self.player_id, self.px, self.py, self.ptype, self.prot, self.color]


# ── GameServer ─────────────────────────────────────────────────────────────────

class GameServer:
    def __init__(self) -> None:
        self.board   = SharedBoard()
        self.overlay = ActivePiecesOverlay()
        self._players: dict[int, dict] = {}
        self._next_id = 1

    async def ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30, max_msg_size=64 * 1024)
        await ws.prepare(request)

        pid = self._next_id
        self._next_id += 1
        self._players[pid] = {
            "ws": ws,
            "piece": PlayerPiece(pid, self.board, self.overlay),
            "name": f"Player{pid}",
            "_move_times": [],
        }
        log.info("[+] player %d  total=%d", pid, len(self._players))

        try:
            # Send identity + current board snapshot
            await ws.send_str(_dumps({"type": "init", "player_id": pid}))
            await ws.send_str(_dumps({
                "type": "board",
                "b": self.board.encode(),
                "total_lines": self.board.total_lines,
            }))
            await self._send_state(pid)

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        await self._on_message(pid, _loads(msg.data))
                    except Exception as exc:
                        log.debug("msg error pid=%d: %s", pid, exc)
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                    break
        except Exception as exc:
            log.debug("ws error pid=%d: %s", pid, exc)
        finally:
            self._players.pop(pid, None)
            self.overlay.remove(pid)
            log.info("[-] player %d  total=%d", pid, len(self._players))

        return ws

    async def _on_message(self, pid: int, data: dict) -> None:
        p = self._players.get(pid)
        if not p:
            return
        piece: PlayerPiece = p["piece"]
        mtype = data.get("type")

        if mtype == "input":
            if not piece.alive:
                return
            # Token-bucket rate limit
            now_ts = time.monotonic()
            times: list = p["_move_times"]
            times.append(now_ts)
            cutoff = now_ts - 1.0
            while times and times[0] < cutoff:
                times.pop(0)
            if len(times) > _MAX_MOVES_PER_SEC:
                return

            action = data.get("action", "")
            cleared = 0
            if   action == "left":       piece.move_left()
            elif action == "right":      piece.move_right()
            elif action == "down":       cleared = piece.soft_drop()
            elif action == "hard_drop":  cleared = piece.hard_drop()
            elif action == "rotate_cw":  piece.rotate_cw()
            elif action == "rotate_ccw": piece.rotate_ccw()
            elif action == "hold":       piece.hold()

            if cleared:
                await self._award_cooperative_bonus(cleared)

            await self._send_state(pid)

        elif mtype == "restart":
            p["piece"] = PlayerPiece(pid, self.board, self.overlay)
            await self._send_state(pid)

        elif mtype == "name":
            raw = str(data.get("name", "")).strip()[:20]
            if raw:
                p["name"] = raw

    async def _award_cooperative_bonus(self, cleared: int) -> None:
        """Give all alive players a shared line-clear bonus."""
        bonus = LINE_SCORE[min(cleared, 4)]
        for p in self._players.values():
            if p["piece"].alive:
                p["piece"].score += bonus

    async def _send_state(self, pid: int) -> None:
        p = self._players.get(pid)
        if not p:
            return
        state = p["piece"].get_state()
        state["type"] = "state"
        try:
            await p["ws"].send_str(_dumps(state))
        except Exception:
            pass

    # ── Game loop ─────────────────────────────────────────────────────────────

    async def game_loop(self) -> None:
        last_world = 0.0

        while True:
            await asyncio.sleep(0.05)  # 20 Hz

            # Apply gravity — only queue a state send when piece actually moved
            updated: list[int] = []
            for pid, p in list(self._players.items()):
                piece: PlayerPiece = p["piece"]
                if piece.alive:
                    moved, cleared = piece.gravity_tick()
                    if moved:
                        if cleared:
                            await self._award_cooperative_bonus(cleared)
                        updated.append(pid)

            # Send personal state updates (chunked)
            for i in range(0, len(updated), _BROADCAST_CHUNK):
                chunk = updated[i : i + _BROADCAST_CHUNK]
                await asyncio.gather(
                    *[self._send_state(pid) for pid in chunk],
                    return_exceptions=True,
                )

            # World broadcast at 5 Hz
            now = time.monotonic()
            if now - last_world >= 0.2:
                last_world = now
                await self._broadcast_world()

    # ── World broadcast ───────────────────────────────────────────────────────

    async def _broadcast_world(self) -> None:
        if not self._players:
            return

        alive_count = sum(1 for p in self._players.values() if p["piece"].alive)

        # Active pieces (all alive players)
        pieces = [
            p["piece"].as_piece_entry()
            for p in self._players.values()
            if p["piece"].alive
        ]

        # Leaderboard (top 50 by score)
        ranked = sorted(
            self._players.items(),
            key=lambda kv: -kv[1]["piece"].score,
        )
        leaderboard = [
            {
                "id": pid,
                "name": p["name"],
                "score": p["piece"].score,
                "alive": p["piece"].alive,
            }
            for pid, p in ranked[:50]
        ]

        payload_obj: dict = {
            "type": "world",
            "total": len(self._players),
            "alive": alive_count,
            "total_lines": self.board.total_lines,
            "pieces": pieces,
            "leaderboard": leaderboard,
        }

        # Include board string only when it changed since last broadcast
        if self.board.dirty:
            payload_obj["board"] = self.board.encode()
            self.board.dirty = False

        payload = _dumps(payload_obj)

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


# ── App setup ──────────────────────────────────────────────────────────────────

async def build_app() -> web.Application:
    server = GameServer()
    app = web.Application(client_max_size=64 * 1024)
    app.router.add_get("/ws", server.ws_handler)
    app.router.add_get("/", lambda _: web.FileResponse(Path("static/index.html")))
    app.router.add_static("/", Path("static"))

    async def _start(app: web.Application) -> None:
        app["gl"] = asyncio.create_task(server.game_loop())

    async def _stop(app: web.Application) -> None:
        app["gl"].cancel()

    app.on_startup.append(_start)
    app.on_cleanup.append(_stop)
    return app


async def main() -> None:
    app = await build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8765)
    await site.start()
    log.info("Tetris × 1000 — Massive Board  http://0.0.0.0:8765")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
        log.info("uvloop active")
    except ImportError:
        pass
    asyncio.run(main())
