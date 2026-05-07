"""WebSocket connection manager — tracks connected players and broadcasts state."""

from __future__ import annotations

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
        """Send JSON data to all connected clients. Silently drop failed sends."""
        message = json.dumps(data)
        stale: list[WebSocket] = []
        for ws in self.connections:
            try:
                await ws.send_text(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.connections.pop(ws, None)

    async def send_to(self, ws: WebSocket, data: dict) -> None:
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            pass
