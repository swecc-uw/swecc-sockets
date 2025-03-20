sfrom fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import json
from pathlib import Path
from .config import settings
from .auth import authenticate_ws
from .managers.connection_manager import ConnectionManager
from .managers.routing_manager import RoutingManager
from .handlers.echo_handler import EchoHandler
from .handlers.presence_handler import PresenceHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SWECC Sockets")


connection_manager = ConnectionManager()
handler_manager = RoutingManager()


echo_handler = EchoHandler()
presence_handler = PresenceHandler(connection_manager)

handler_manager.register_handler("echo", echo_handler)
handler_manager.register_handler("presence", presence_handler)

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
    """Health check"""
    return {"status": "online", "message": "WebSocket server is running"}


@app.get("/ping")
async def ping():
    """Simple ping"""
    return Response(content="pong", media_type="text/plain")


@app.websocket("/ws/{service}/{token}")
async def websocket_endpoint(websocket: WebSocket, service: str, token: str):
    """
    WebSocket endpoint with JWT authentication and service routing

    Args:
        websocket: WebSocket connection
        service: Service name (echo or presence)
        token: JWT token for authentication
    """
    user = await authenticate_ws(websocket, token)
    if not user:
        logger.warning(f"Authentication failed for WebSocket connection")
        return
        
    user_id = user["user_id"]
    username = user["username"]

    try:
        handler = handler_manager.get_handler(service)
    except KeyError:
        logger.warning(f"Unknown service requested: {service}")
        await websocket.accept()
        await websocket.send_text(
            json.dumps({
                "type": "error",
                "message": f"Unknown service: {service}. Available services: echo, presence"
            })
        )
        await websocket.close(code=4004)
        return
    
    await connection_manager.connect(websocket, user_id)
    await handler.handle_connect(websocket, user_id, username)

    try:
        while True:
            data = await websocket.receive_text()
            await handler.handle_message(websocket, user_id, username, data)
            
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket, user_id)
        await handler.handle_disconnect(user_id, username)
        logger.info(f"Client disconnected: {username} (ID: {user_id})")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )