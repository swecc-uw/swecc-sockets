from jose import jwt, JWTError
from fastapi import WebSocket, status
from pydantic import ValidationError, BaseModel
from datetime import datetime, timezone
from typing import Optional, List
from .config import settings


class TokenPayload(BaseModel):
    user_id: int
    username: str
    groups: List[str] = []
    exp: datetime


class Auth:
    @staticmethod
    async def validate_token(token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(
                token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )
            token_data = TokenPayload(**payload)

            if token_data.exp < datetime.now(timezone.utc):
                return None

            return {
                "user_id": token_data.user_id,
                "username": token_data.username,
                "groups": token_data.groups,
            }
        except (JWTError, ValidationError) as e:
            print("Token validation failed", e)
            return None

    @staticmethod
    async def authenticate_ws(
        websocket: WebSocket, token: str, required_groups: List[str] = ["is_authenticated"]
    ) -> Optional[dict]:
        user = await Auth.validate_token(token)
        if not user or not all(group in user["groups"] for group in required_groups):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None
        return user

    @staticmethod
    async def check_permission(user: dict, required_groups: List[str]) -> bool:
        if "groups" not in user:
            return False
        return any(group in user["groups"] for group in required_groups)