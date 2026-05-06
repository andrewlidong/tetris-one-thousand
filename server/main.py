"""FastAPI application — serves the game client and WebSocket endpoint."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .config import TICK_RATE
from .game.engine import GameEngine
from .game.types import Action
from .network.ws import ConnectionManager

engine = GameEngine()
manager = ConnectionManager()


async def game_loop() -> None:
    """Tick the engine at a fixed rate and broadcast deltas to all players."""
    while True:
        await asyncio.sleep(TICK_RATE)
        if engine.game_over:
            continue
        engine.tick()
        delta = engine.get_delta()
        await manager.broadcast({"type": "delta", **delta})


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(game_loop())
    yield
    task.cancel()


app = FastAPI(title="Tetris 1000", lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    player_id = await manager.connect(ws)

    # Add the player to the game engine
    piece = engine.add_player(player_id)

    # Send welcome + full state to the new player
    await manager.send_to(ws, {
        "type": "welcome",
        "player_id": player_id,
    })
    await manager.send_to(ws, {"type": "state", **engine.get_state()})

    # Send delta to everyone else so they see the new piece
    delta = engine.get_delta()
    await manager.broadcast({"type": "delta", **delta})

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

            # Broadcast delta after action
            delta = engine.get_delta()
            await manager.broadcast({"type": "delta", **delta})

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
        engine.remove_player(player_id)
        delta = engine.get_delta()
        await manager.broadcast({"type": "delta", **delta})
