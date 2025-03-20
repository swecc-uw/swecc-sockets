from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel


class MessageType(str, Enum):

    SYSTEM = "system"
    ERROR = "error"

    ECHO = "echo"

    ROOM_JOINED = "room_joined"
    ROOM_LEFT = "room_left"
    PRESENCE_UPDATE = "presence_update"
    ROOM_LIST = "room_list"
    ROOM_USERS = "room_users"


class Message(BaseModel):
    type: MessageType
    message: Optional[str] = None
    user_id: Optional[int] = None
    username: Optional[str] = None
    room_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
