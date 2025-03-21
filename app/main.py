from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import json
from pathlib import Path
import asyncio
from .config import settings
from .auth import Auth
from .events import Event, EventType
from .connection_manager import ConnectionManager
from .event_emitter import EventEmitter
from .service_registry import ServiceRegistry
from .handlers.echo_handler import EchoHandler
from .handlers.presence_handler import PresenceHandler
from .handlers.chat_handler import ChatRoomHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SWECC Sockets")

connection_manager = ConnectionManager()
event_emitter = EventEmitter()
service_registry = ServiceRegistry()

service_registry.register("echo", EchoHandler)
service_registry.register("presence", PresenceHandler)
service_registry.register("chat", ChatRoomHandler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.get("/")
async def root():
    return {"status": "online", "message": "WebSocket server is running"}


@app.get("/ping")
async def ping():
    return Response(content="pong", media_type="text/plain")


@app.websocket("/ws/{service}/{token}")
async def websocket_endpoint(websocket: WebSocket, service: str, token: str):
    user = await Auth.authenticate_ws(websocket, token)
    if not user:
        logger.warning("Authentication failed for WebSocket connection")
        return

    user_id = user["user_id"]
    username = user["username"]

    service_handler = service_registry.get_service(service)
    if not service_handler:
        logger.warning(f"Unknown service requested: {service}")
        await websocket.accept()
        await websocket.send_text(
            json.dumps({
                "type": "error",
                "message": f"Unknown service: {service}. Available services: echo, presence, chat"
            })
        )
        await websocket.close(code=4004)
        return

    await connection_manager.connect(websocket, user_id)

    connection_event = Event(
        type=EventType.CONNECTION,
        user_id=user_id,
        username=username,
        websocket=websocket
    )
    await event_emitter.emit(connection_event)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                message_event = Event(
                    type=EventType.MESSAGE,
                    user_id=user_id,
                    username=username,
                    data=message_data,
                    websocket=websocket
                )
                await event_emitter.emit(message_event)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({
                        "type": "error",
                        "message": "Invalid JSON message format"
                    })
                )

    except WebSocketDisconnect:
        connection_manager.disconnect(websocket, user_id)
        disconnect_event = Event(
            type=EventType.DISCONNECT,
            user_id=user_id,
            username=username
        )
        await event_emitter.emit(disconnect_event)
        logger.info(f"Client disconnected: {username} (ID: {user_id})")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)