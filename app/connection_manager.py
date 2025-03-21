from fastapi import WebSocket
from typing import Dict, List, Set, Optional
import logging
import json
import asyncio
from .message import Message

logger = logging.getLogger(__name__)


class ConnectionManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConnectionManager, cls).__new__(cls)
            cls._instance.active_connections = {}
            cls._instance.user_connections = {}
        return cls._instance

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        await websocket.accept()
        total_num_connections = len(self.active_connections)

        connection_id = id(websocket)
        self.active_connections[connection_id] = websocket

        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(connection_id)

        logger.info(f"User {user_id} connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        connection_id = id(websocket)
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        if user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        logger.info(f"User {user_id} disconnected. Total connections: {len(self.active_connections)}")

    async def send_to_user(self, message: str, user_id: int) -> None:
        if user_id not in self.user_connections:
            return

        connection_ids = list(self.user_connections[user_id])
        send_tasks = []

        for conn_id in connection_ids:
            websocket = self.active_connections.get(conn_id)
            if websocket:
                send_tasks.append(self._safe_send(websocket, message, conn_id, user_id))

        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)

    async def broadcast(self, message: str, exclude_user_id: Optional[int] = None) -> None:
        send_tasks = []

        for user_id, connection_ids in self.user_connections.items():
            if exclude_user_id and user_id == exclude_user_id:
                continue

            for conn_id in connection_ids:
                websocket = self.active_connections.get(conn_id)
                if websocket:
                    send_tasks.append(self._safe_send(websocket, message, conn_id, user_id))

        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)

    async def broadcast_to_users(self, message: str, user_ids: List[int]) -> None:
        send_tasks = []

        for user_id in user_ids:
            if user_id in self.user_connections:
                for conn_id in self.user_connections[user_id]:
                    websocket = self.active_connections.get(conn_id)
                    if websocket:
                        send_tasks.append(self._safe_send(websocket, message, conn_id, user_id))

        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)

    async def _safe_send(self, websocket: WebSocket, message: str, conn_id: int, user_id: int) -> None:
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {str(e)}")
            if conn_id in self.active_connections:
                del self.active_connections[conn_id]
            if user_id in self.user_connections:
                self.user_connections[user_id].discard(conn_id)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]

    def get_active_user_ids(self) -> Set[int]:
        return set(self.user_connections.keys())