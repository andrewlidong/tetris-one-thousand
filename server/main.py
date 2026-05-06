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
    """Tick the engine at a fixed rate and broadcast state to all players."""
    while True:
        await asyncio.sleep(TICK_RATE)
        if engine.game_over:
            continue
        engine.tick()
        state = engine.get_state()
        await manager.broadcast({"type": "state", **state})


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

    # Send the player their ID and initial state
    await manager.send_to(ws, {
        "type": "welcome",
        "player_id": player_id,
    })

    # Broadcast updated state to everyone
    state = engine.get_state()
    await manager.broadcast({"type": "state", **state})

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

            # Broadcast state after action
            state = engine.get_state()
            await manager.broadcast({"type": "state", **state})

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
        engine.remove_player(player_id)
        # Broadcast updated state
        state = engine.get_state()
        await manager.broadcast({"type": "state", **state})
