from fastapi import WebSocket
import json
import logging
from .base_handler import WebSocketHandler
from ..models.message import Message, MessageType

logger = logging.getLogger(__name__)


class EchoHandler(WebSocketHandler):
    """Handler for simple echo test"""

    async def handle_connect(self, websocket: WebSocket, user_id: int, username: str):
        await websocket.send_text(
            json.dumps(
                Message(
                    type=MessageType.SYSTEM,
                    message=f"Echo service: Connected as {username}",
                ).dict()
            )
        )
        logger.info(f"Echo service: User {username} (ID: {user_id}) connected")

    async def handle_message(
        self, websocket: WebSocket, user_id: int, username: str, data: str
    ):
        """Echo back the received message"""
        logger.info(f"Echo service: Message from {username} (ID: {user_id}): {data}")

        response = Message(
            type=MessageType.ECHO, user_id=user_id, username=username, message=data
        )

        await websocket.send_text(json.dumps(response.dict()))

    async def handle_disconnect(self, user_id: int, username: str):
        logger.info(f"Echo service: User {username} (ID: {user_id}) disconnected")
