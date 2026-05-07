"""FastAPI application — serves the game client and WebSocket endpoint."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .config import BROADCAST_RATE, TICK_RATE
from .game.engine import GameEngine
from .game.types import Action
from .network.ws import ConnectionManager

engine = GameEngine()
manager = ConnectionManager()


async def gravity_loop() -> None:
    """Apply gravity to all active pieces at TICK_RATE."""
    while True:
        await asyncio.sleep(TICK_RATE)
        if not engine.game_over:
            engine.tick()


async def broadcast_loop() -> None:
    """Flush accumulated deltas at BROADCAST_RATE.

    Decoupled from gravity so player actions show up at ~15Hz regardless of
    gravity tick rate, and broadcast cost is bounded by recipients × rate
    rather than recipients × actions/sec.
    """
    interval = 1.0 / BROADCAST_RATE
    while True:
        await asyncio.sleep(interval)
        delta = engine.get_delta()
        if delta is not None:
            await manager.broadcast({"type": "delta", **delta})


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(gravity_loop()),
        asyncio.create_task(broadcast_loop()),
    ]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Tetris 1000", lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    player_id = await manager.connect(ws)
    engine.add_player(player_id)

    # New connection gets a full snapshot; the broadcast loop will send deltas thereafter.
    await manager.send_to(ws, {"type": "welcome", "player_id": player_id})
    await manager.send_to(ws, {"type": "state", **engine.get_state()})

    try:
        while True:
            data = await ws.receive_json()
            action_str = data.get("action")
            if action_str is None:
                continue
            try:
                action = Action(action_str)
            except ValueError:
                continue
            engine.process_action(player_id, action)

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
        engine.remove_player(player_id)
