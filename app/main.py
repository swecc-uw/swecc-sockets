from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
import json
from .config import settings
from .auth import authenticate_ws
from .socket_service import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SWECC Sockets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ws/")
async def root():
    """Health check endpoint"""
    return {"status": "online", "message": "WebSocket server is running"}

@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    """
    WebSocket endpoint with JWT authentication
    
    Args:
        websocket: WebSocket connection
        token: JWT token for authentication
    """

    user = await authenticate_ws(websocket, token)
    if not user:
        # connection closed in authenticate_ws if token is invalid
        logger.warning(f"Authentication failed for WebSocket connection")
        return
        
    user_id = user["user_id"]
    username = user["username"]
    
    # accept connection
    await manager.connect(websocket, user_id)
    await websocket.send_text(
        json.dumps({
            "type": "system",
            "message": f"Connected as {username}"
        })
    )
    
    try:
        # just return messages back to sender
        while True:
            data = await websocket.receive_text()
            
            logger.info(f"Message from {username} (ID: {user_id}): {data}")
            
            response = {
                "type": "echo",
                "user_id": user_id,
                "username": username,
                "message": data
            }
            
            await websocket.send_text(json.dumps(response))
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        logger.info(f"Client disconnected: {username} (ID: {user_id})")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )