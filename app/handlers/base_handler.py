from fastapi import WebSocket
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class WebSocketHandler(ABC):
    """Base class for WebSocket handlers"""

    @abstractmethod
    async def handle_message(
        self, websocket: WebSocket, user_id: int, username: str, data: str
    ):
        """Handle an incoming WebSocket message"""
        pass

    @abstractmethod
    async def handle_connect(self, websocket: WebSocket, user_id: int, username: str):
        """Handle a new WebSocket connection"""
        pass

    @abstractmethod
    async def handle_disconnect(self, user_id: int, username: str):
        """Handle a WebSocket disconnection"""
        pass
