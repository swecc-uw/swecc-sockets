from fastapi import WebSocket
import logging
from typing import Dict, Type
from ..handlers.base_handler import WebSocketHandler

logger = logging.getLogger(__name__)


class RoutingManager:
    """Routes WebSocket connections to the appropriate handler based on path"""

    def __init__(self):
        self.handlers: Dict[str, WebSocketHandler] = {}

    def register_handler(self, path: str, handler: WebSocketHandler):
        """Register a handler for a specific path"""
        self.handlers[path] = handler
        logger.info(f"Registered handler for path: {path}")

    def get_handler(self, path: str) -> WebSocketHandler:
        """Get the handler for a specific path"""
        if path not in self.handlers:
            raise KeyError(f"No handler registered for path: {path}")
        return self.handlers[path]
