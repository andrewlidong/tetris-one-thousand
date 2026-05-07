"""WebSocket connection manager — tracks connected players and broadcasts state."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # ws -> player_id
        self.connections: dict[WebSocket, str] = {}

    async def connect(self, ws: WebSocket) -> str:
        await ws.accept()
        player_id = uuid.uuid4().hex[:8]
        self.connections[ws] = player_id
        return player_id

    def disconnect(self, ws: WebSocket) -> str | None:
        return self.connections.pop(ws, None)

    @property
    def player_count(self) -> int:
        return len(self.connections)

    async def broadcast(self, data: dict) -> None:
        """Send JSON data to all connected clients in parallel.

        Sends are dispatched concurrently with asyncio.gather so one slow
        client doesn't block the rest. Failed sockets are dropped.
        """
        if not self.connections:
            return
        message = json.dumps(data)
        sockets = list(self.connections.keys())

        async def send_one(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_text(message)
                return None
            except Exception:
                return ws

        results = await asyncio.gather(*(send_one(ws) for ws in sockets))
        for ws in results:
            if ws is not None:
                self.connections.pop(ws, None)

    async def send_to(self, ws: WebSocket, data: dict) -> None:
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            pass
