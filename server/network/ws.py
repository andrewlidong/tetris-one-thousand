"""WebSocket connection manager — tracks connected players and broadcasts state."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid

from fastapi import WebSocket

from ..config import BROADCAST_CHUNK


class ConnectionManager:
    def __init__(self) -> None:
        # ws -> player_id
        self.connections: dict[WebSocket, str] = {}
        # reconnect token -> player_id, so a returning browser keeps its identity
        self.sessions: dict[str, str] = {}

    async def connect(self, ws: WebSocket, token: str | None = None) -> str:
        await ws.accept()

        player_id: str | None = None
        if token:
            known = self.sessions.get(token)
            # Reuse the old identity unless it's already live (second tab
            # with the same token becomes a separate player)
            if known and known not in self.connections.values():
                player_id = known

        if player_id is None:
            player_id = uuid.uuid4().hex[:8]

        if token:
            self.sessions[token] = player_id

        self.connections[ws] = player_id
        return player_id

    def disconnect(self, ws: WebSocket) -> str | None:
        return self.connections.pop(ws, None)

    @property
    def player_count(self) -> int:
        return len(self.connections)

    async def broadcast(self, data: dict) -> None:
        """Send JSON data to all connected clients.

        The payload is serialized once, then sent concurrently in chunks so a
        single slow client only delays its own chunk, not every connection.
        Failed sends drop the connection silently.
        """
        message = json.dumps(data)
        conns = list(self.connections)
        stale: list[WebSocket] = []

        async def send(ws: WebSocket) -> None:
            try:
                await ws.send_text(message)
            except Exception:
                stale.append(ws)

        for i in range(0, len(conns), BROADCAST_CHUNK):
            await asyncio.gather(*(send(ws) for ws in conns[i : i + BROADCAST_CHUNK]))

        for ws in stale:
            self.connections.pop(ws, None)

    async def send_to(self, ws: WebSocket, data: dict) -> None:
        with contextlib.suppress(Exception):
            await ws.send_text(json.dumps(data))
