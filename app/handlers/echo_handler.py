import json
import logging
from ..events import Event, EventType
from ..message import Message, MessageType
from ..connection_manager import ConnectionManager
from ..event_emitter import EventEmitter

logger = logging.getLogger(__name__)


class EchoHandler:
    def __init__(self):
        self.emitter = EventEmitter()
        self.connection_manager = ConnectionManager()
        self.emitter.on(EventType.CONNECTION, self.handle_connect)
        self.emitter.on(EventType.MESSAGE, self.handle_message)
        self.emitter.on(EventType.DISCONNECT, self.handle_disconnect)

    async def handle_connect(self, event: Event) -> None:
        message = Message(
            type=MessageType.SYSTEM,
            message=f"Echo service: Connected as {event.username}"
        )
        await event.websocket.send_text(json.dumps(message.dict()))
        logger.info(f"Echo service: User {event.username} (ID: {event.user_id}) connected")

    async def handle_message(self, event: Event) -> None:
        logger.info(f"Echo service: Message from {event.username} (ID: {event.user_id}): {event.data.get('content', '')}")

        response = Message(
            type=MessageType.ECHO,
            user_id=event.user_id,
            username=event.username,
            message=event.data.get("content", "")
        )

        await event.websocket.send_text(json.dumps(response.dict()))

    async def handle_disconnect(self, event: Event) -> None:
        logger.info(f"Echo service: User {event.username} (ID: {event.user_id}) disconnected")
