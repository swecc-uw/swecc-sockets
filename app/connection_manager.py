from fastapi import WebSocket
from typing import Dict, Set
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
        self.user_connections = {}
        self.closing_connections = set()

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        await websocket.accept()

        connection_id = id(websocket)
        self.active_connections[connection_id] = websocket

        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(connection_id)

        logger.info(f"User {user_id} connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        connection_id = id(websocket)

        # Mark as closing first to prevent further sends
        self.closing_connections.add(connection_id)

        # Remove from active connections
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        if user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        logger.info(f"User {user_id} disconnected. Total connections: {len(self.active_connections)}")

    def is_connection_closing(self, websocket: WebSocket) -> bool:
        return id(websocket) in self.closing_connections

    def get_active_user_ids(self) -> Set[int]:
        return set(self.user_connections.keys())