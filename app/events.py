from enum import Enum, auto
from typing import Dict, Any, Optional


class EventType(str, Enum):
    CONNECTION = "connection"
    MESSAGE = "message"
    DISCONNECT = "disconnect"
    JOIN_ROOM = "join_room"
    LEAVE_ROOM = "leave_room"
    LIST_ROOMS = "list_rooms"
    GET_ROOM_USERS = "get_room_users"
    ECHO = "echo"


class Event:
    def __init__(
        self,
        type: EventType,
        user_id: int,
        username: str,
        data: Optional[Dict[str, Any]] = None,
        websocket=None,
        room_id: Optional[str] = None,
    ):
        self.type = type
        self.user_id = user_id
        self.username = username
        self.data = data or {}
        self.websocket = websocket
        self.room_id = room_id
