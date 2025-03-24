import json
import logging
from ..events import Event, EventType
from ..message import Message, MessageType

logger = logging.getLogger(__name__)


class EchoHandler:
    def __init__(self, event_emitter):
        self.event_emitter = event_emitter
        self.event_emitter.on(EventType.CONNECTION, self.handle_connect)
        self.event_emitter.on(EventType.MESSAGE, self.handle_message)
        self.event_emitter.on(EventType.DISCONNECT, self.handle_disconnect)

    async def handle_connect(self, event: Event) -> None:
        try:
            message = Message(
                type=MessageType.SYSTEM,
                message=f"Echo service: Connected as {event.username}"
            )
            await self.safe_send(event.websocket, message.dict())
            logger.info(f"Echo service: User {event.username} (ID: {event.user_id}) connected")
        except Exception as e:
            logger.error(f"Error in handle_connect: {str(e)}", exc_info=True)

    async def handle_message(self, event: Event) -> None:
        try:
            content = event.data.get("content", "")
            logger.info(f"Echo service: Message from {event.username} (ID: {event.user_id}): {content}")

            response = Message(
                type=MessageType.ECHO,
                user_id=event.user_id,
                username=event.username,
                message=content
            )

            await self.safe_send(event.websocket, response.dict())
        except Exception as e:
            logger.error(f"Error in handle_message: {str(e)}", exc_info=True)

    async def handle_disconnect(self, event: Event) -> None:
        logger.info(f"Echo service: User {event.username} (ID: {event.user_id}) disconnected")

    async def safe_send(self, websocket, data):
        """Safely send a message, handling potential disconnection gracefully"""
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            # Just log the error
            logger.debug(f"Could not send message, websocket may be closed: {str(e)}")