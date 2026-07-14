"""FastAPI application — serves the game client and WebSocket endpoint."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .config import MAX_MESSAGES_PER_SEC
from .game.engine import GameEngine
from .game.types import Action
from .highscores import HighScores
from .network.ws import ConnectionManager

engine = GameEngine()
manager = ConnectionManager()
highscores = HighScores()

# Ticks between periodic high-score sweeps of all connected players
_HIGHSCORE_SWEEP_TICKS = 20


async def game_loop() -> None:
    """Tick the engine and broadcast deltas. The interval shrinks as the
    team clears lines (gravity ramp), resetting each round."""
    ticks = 0
    while True:
        await asyncio.sleep(engine.tick_interval)
        engine.tick()
        delta = engine.get_delta()
        await manager.broadcast({"type": "delta", **delta})

        ticks += 1
        if ticks % _HIGHSCORE_SWEEP_TICKS == 0:
            for pid, score in engine.scores.items():
                highscores.submit(engine.names.get(pid, ""), score)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(game_loop())
    yield
    task.cancel()


app = FastAPI(title="Tetris 1000", lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/highscores")
async def get_highscores() -> list[dict]:
    return highscores.top()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    # Optional reconnect token: a returning browser keeps its identity
    # (name + score) across disconnects and refreshes
    token = ws.query_params.get("token") or None
    player_id = await manager.connect(ws, token)

    # Add the player to the game engine
    engine.add_player(player_id)

    # Send welcome + full state to the new player
    await manager.send_to(
        ws,
        {
            "type": "welcome",
            "player_id": player_id,
        },
    )
    await manager.send_to(ws, {"type": "state", **engine.get_state()})

    # Send delta to everyone else so they see the new piece
    delta = engine.get_delta()
    await manager.broadcast({"type": "delta", **delta})

    # Sliding-window rate limit: timestamps of this connection's recent messages
    recent: deque[float] = deque()

    try:
        while True:
            data = await ws.receive_json()

            # Drop messages beyond the per-second budget (protects the shared
            # engine and broadcast fan-out from spammy/malicious clients)
            now = time.monotonic()
            while recent and now - recent[0] > 1.0:
                recent.popleft()
            if len(recent) >= MAX_MESSAGES_PER_SEC:
                continue
            recent.append(now)

            # Players can (re)name themselves at any time
            name = data.get("name")
            if isinstance(name, str):
                engine.set_name(player_id, name)
                delta = engine.get_delta()
                await manager.broadcast({"type": "delta", **delta})
                continue

            action_str = data.get("action")
            if action_str is None:
                continue

            try:
                action = Action(action_str)
            except ValueError:
                continue

            changed = engine.process_action(player_id, action)

            # Only fan out when the action actually changed something —
            # a piece pinned against a wall shouldn't trigger broadcasts
            if changed:
                delta = engine.get_delta()
                await manager.broadcast({"type": "delta", **delta})

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
        # Capture their final score before the identity goes dormant
        highscores.submit(engine.names.get(player_id, ""), engine.scores.get(player_id, 0))
        engine.remove_player(player_id)
        delta = engine.get_delta()
        await manager.broadcast({"type": "delta", **delta})
