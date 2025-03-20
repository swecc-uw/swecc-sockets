from fastapi import WebSocket
from typing import Dict, List, Set
import logging
import json
from ..models.message import Message, MessageType

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):

        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        """Accept connection and store it"""
        await websocket.accept()

        if user_id not in self.active_connections:
            self.active_connections[user_id] = []

        self.active_connections[user_id].append(websocket)
        logger.info(
            f"User {user_id} connected. Active connections: {self._count_connections()}"
        )

    def disconnect(self, websocket: WebSocket, user_id: int):
        """Remove connection"""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)

            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

        logger.info(
            f"User {user_id} disconnected. Active connections: {self._count_connections()}"
        )

    async def send_message(self, message: str, user_id: int):
        """Send message to a specific user (all their connections)"""
        if user_id in self.active_connections:
            disconnected_websockets = []

            for websocket in self.active_connections[user_id]:
                try:
                    await websocket.send_text(message)
                except RuntimeError:

                    disconnected_websockets.append(websocket)

            for websocket in disconnected_websockets:
                self.disconnect(websocket, user_id)

    async def broadcast(self, message: str):
        """Send message to all connected clients"""
        for user_id in list(self.active_connections.keys()):
            await self.send_message(message, user_id)

    async def broadcast_to_users(self, message: str, user_ids: List[int]):
        """Send message to specific users"""
        for user_id in user_ids:
            await self.send_message(message, user_id)

    def get_active_user_ids(self) -> Set[int]:
        """Get all active user IDs"""
        return set(self.active_connections.keys())

    def _count_connections(self) -> int:
        """Count total number of active connections"""
        return sum(len(connections) for connections in self.active_connections.values())
