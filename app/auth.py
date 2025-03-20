from jose import jwt, JWTError
from fastapi import WebSocket, status
from pydantic import ValidationError, BaseModel
from datetime import datetime, timezone
from .config import settings

class TokenPayload(BaseModel):
    user_id: int
    username: str
    exp: datetime

async def decode_token(token: str) -> TokenPayload | None:
    try:
        payload = jwt.decode(
            token, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        token_data = TokenPayload(**payload)
        
        if token_data.exp < datetime.now(timezone.utc):
            return None
            
        return token_data
    except (JWTError, ValidationError):
        return None

async def get_current_user_from_token(token: str) -> dict | None:
    token_data = await decode_token(token)
    if token_data is None:
        return None
        
    return {
        "user_id": token_data.user_id,
        "username": token_data.username
    }

async def authenticate_ws(websocket: WebSocket, token: str) -> dict | None:
    user = await get_current_user_from_token(token)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    return user