from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import json
from pathlib import Path
import asyncio

from .mq import initialize_rabbitmq
from .config import settings
from .auth import Auth
from .events import Event, EventType
from .connection_manager import ConnectionManager
from .event_emitter import EventEmitter
from .handlers.echo_handler import EchoHandler
from .handlers.logs_handler import ContainerLogsHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SWECC Sockets")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up static files
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_event_loop()
    loop.create_task(initialize_rabbitmq(loop))


# Basic endpoints
@app.get("/")
async def root():
    return {"status": "online", "message": "WebSocket server is running"}


@app.get("/ping")
async def ping():
    return Response(content="pong", media_type="text/plain")


# Echo endpoint
@app.websocket("/ws/echo/{token}")
async def echo_endpoint(websocket: WebSocket, token: str):
    # Create endpoint-specific instances
    connection_manager = ConnectionManager()
    event_emitter = EventEmitter()
    echo_handler = EchoHandler(event_emitter)

    user = None

    try:
        # Authenticate
        user = await Auth.authenticate_ws(websocket, token)
        if not user:
            logger.warning("Authentication failed for WebSocket connection")
            return

        user_id = user["user_id"]
        username = user["username"]

        # Connect and notify
        await connection_manager.connect(websocket, user_id)

        connection_event = Event(
            type=EventType.CONNECTION,
            user_id=user_id,
            username=username,
            websocket=websocket,
        )
        await event_emitter.emit(connection_event)

        # Message loop
        while True:
            try:
                data = await websocket.receive_text()
                try:
                    message_data = json.loads(data)

                    message_event = Event(
                        type=EventType.MESSAGE,
                        user_id=user_id,
                        username=username,
                        data=message_data,
                        websocket=websocket,
                    )
                    await event_emitter.emit(message_event)
                except json.JSONDecodeError:
                    if not connection_manager.is_connection_closing(websocket):
                        await echo_handler.safe_send(
                            websocket,
                            {"type": "error", "message": "Invalid JSON message format"},
                        )
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(
                    f"Error handling WebSocket message: {str(e)}", exc_info=True
                )
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Error handling WebSocket connection: {str(e)}", exc_info=True)
    finally:
        if user:
            try:
                connection_manager.disconnect(websocket, user["user_id"])
                disconnect_event = Event(
                    type=EventType.DISCONNECT,
                    user_id=user["user_id"],
                    username=user["username"],
                )
                await event_emitter.emit(disconnect_event)
                logger.info(
                    f"Echo client disconnected: {user['username']} (ID: {user['user_id']})"
                )
            except Exception as e:
                logger.error(f"Error during WebSocket cleanup: {str(e)}", exc_info=True)


# Logs endpoint
@app.websocket("/ws/logs/{token}")
async def logs_endpoint(websocket: WebSocket, token: str):
    # Create endpoint-specific instances
    connection_manager = ConnectionManager()
    event_emitter = EventEmitter()
    logs_handler = ContainerLogsHandler(event_emitter)

    user = None

    try:
        # Authenticate and check for admin rights
        user = await Auth.authenticate_ws(
            websocket, token, required_groups=["is_admin", "is_api_key"]
        )
        if not user:
            logger.warning("Authentication failed for logs WebSocket connection")
            return

        user_id = user["user_id"]
        username = user["username"]

        # Connect and notify
        await connection_manager.connect(websocket, user_id)

        connection_event = Event(
            type=EventType.CONNECTION,
            user_id=user_id,
            username=username,
            data={"groups": user.get("groups", [])},
            websocket=websocket,
        )
        await event_emitter.emit(connection_event)

        # Message loop
        while True:
            try:
                data = await websocket.receive_text()
                try:
                    message_data = json.loads(data)
                    message_data["groups"] = user.get("groups", [])

                    message_event = Event(
                        type=EventType.MESSAGE,
                        user_id=user_id,
                        username=username,
                        data=message_data,
                        websocket=websocket,
                    )
                    await event_emitter.emit(message_event)
                except json.JSONDecodeError:
                    if not connection_manager.is_connection_closing(websocket):
                        await logs_handler.safe_send(
                            websocket,
                            {"type": "error", "message": "Invalid JSON message format"},
                        )
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(
                    f"Error handling WebSocket message: {str(e)}", exc_info=True
                )
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Error handling WebSocket connection: {str(e)}", exc_info=True)
    finally:
        if user:
            try:
                connection_manager.disconnect(websocket, user["user_id"])
                disconnect_event = Event(
                    type=EventType.DISCONNECT,
                    user_id=user["user_id"],
                    username=user["username"],
                )
                await event_emitter.emit(disconnect_event)
                logger.info(
                    f"Logs client disconnected: {user['username']} (ID: {user['user_id']})"
                )
            except Exception as e:
                logger.error(f"Error during WebSocket cleanup: {str(e)}", exc_info=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
