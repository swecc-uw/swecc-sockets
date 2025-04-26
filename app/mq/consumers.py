import mq
import logging
import json
from ..connection_manager import ConnectionManager
from ..handlers import HandlerKind
from ..message import Message, MessageType

logger = logging.getLogger(__name__)

# Declare consumers here

@mq.consumer(queue="sockets.reviewed-resume", exchange="ai", routing_key="reviewed")
async def reviewed_resume_consumer(ch, method, properties, body):
    """
    Consumer for the reviewed resume queue.
    """
    # Process the message
    body = body.decode("utf-8")
    logger.info(f"Received reviewed resume message: {body}")
    try:
        body = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON: {e}")
        return
    feedback = body.get("feedback", None)
    key = body.get("key", None)

    if feedback is None or key is None:
        logger.error("Feedback or key not found in message")
        return

    user_id, resume_id, file_name = key.split("-")

    ws_connection_manager = ConnectionManager()
    websocket = ws_connection_manager.get_websocket_connection(HandlerKind.Resume, int(user_id))

    if websocket is None:
        logger.warning(f"No active WebSocket connection for user {user_id}")
        return
    
    message = Message(
        type=MessageType.RESUME_REVIEWED,
        user_id=int(user_id),
        username=None,
        message=f"Resume reviewed for user {user_id} with feedback: {feedback}",
        data={
            "resume_id": resume_id,
            "file_name": file_name,
            "feedback": feedback,
        },
    )

    try:
        await websocket.send_text(json.dumps(message.model_dump()))
        logger.info(f"Sent reviewed resume message to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send message to WebSocket: {e}")
        return
