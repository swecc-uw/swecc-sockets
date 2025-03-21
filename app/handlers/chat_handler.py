import json
import logging
from typing import Dict, Set, Tuple
from ..events import Event, EventType
from ..message import Message, MessageType
from ..connection_manager import ConnectionManager
from ..event_emitter import EventEmitter

logger = logging.getLogger(__name__)


class ChatRoomHandler:
    def __init__(self):
        self.emitter = EventEmitter()
        self.connection_manager = ConnectionManager()
        self._rooms: Dict[str, Set[Tuple[int, str]]] = {}
        self._user_rooms: Dict[int, Set[str]] = {}

        self.emitter.on(EventType.CONNECTION, self.handle_connect)
        self.emitter.on(EventType.MESSAGE, self.handle_message)
        self.emitter.on(EventType.DISCONNECT, self.handle_disconnect)

    async def handle_connect(self, event: Event) -> None:
        message = Message(
            type=MessageType.SYSTEM,
            message=f"Chat service: Connected as {event.username}"
        )
        await event.websocket.send_text(json.dumps(message.dict()))
        logger.info(f"Chat service: User {event.username} (ID: {event.user_id}) connected")

    async def handle_message(self, event: Event) -> None:
        try:
            message_type = event.data.get("type")
            room_id = event.data.get("room_id")
            content = event.data.get("content")

            if message_type == "join_room" and room_id:
                await self._join_room(event.user_id, event.username, room_id, event.websocket)
            elif message_type == "leave_room" and room_id:
                await self._leave_room(event.user_id, event.username, room_id)
            elif message_type == "chat_message" and room_id and content:
                await self._handle_chat_message(event.user_id, event.username, room_id, content)
            elif message_type == "list_rooms":
                await self._list_rooms(event.websocket)
            elif message_type == "get_room_users" and room_id:
                await self._get_room_users(event.websocket, room_id)
            else:
                error_msg = Message(
                    type=MessageType.ERROR,
                    message="Unknown chat command. Available commands: join_room, leave_room, chat_message, list_rooms, get_room_users"
                )
                await event.websocket.send_text(json.dumps(error_msg.dict()))

        except Exception as e:
            logger.error(f"Error processing chat message: {str(e)}", exc_info=True)
            error_msg = Message(
                type=MessageType.ERROR,
                message=f"Error processing your message: {str(e)}"
            )
            await event.websocket.send_text(json.dumps(error_msg.dict()))

    async def handle_disconnect(self, event: Event) -> None:
        user_id = event.user_id
        username = event.username

        if user_id in self._user_rooms:
            rooms_to_leave = list(self._user_rooms[user_id])
            for room_id in rooms_to_leave:
                await self._leave_room(user_id, username, room_id)

            if user_id in self._user_rooms:
                del self._user_rooms[user_id]

        logger.info(f"Chat service: User {username} (ID: {user_id}) disconnected")

    async def _join_room(self, user_id: int, username: str, room_id: str, websocket) -> None:
        user_info = (user_id, username)

        if room_id not in self._rooms:
            self._rooms[room_id] = set()

        self._rooms[room_id].add(user_info)

        if user_id not in self._user_rooms:
            self._user_rooms[user_id] = set()
        self._user_rooms[user_id].add(room_id)

        join_message = Message(
            type=MessageType.ROOM_JOINED,
            room_id=room_id,
            message=f"Joined chat room {room_id}"
        )
        await websocket.send_text(json.dumps(join_message.dict()))

        system_message = Message(
            type=MessageType.CHAT_MESSAGE,
            room_id=room_id,
            username="System",
            message=f"{username} has joined the room"
        )
        await self._broadcast_to_room(room_id, system_message, exclude_user_id=user_id)

        logger.info(f"User {username} (ID: {user_id}) joined chat room {room_id}")

    async def _leave_room(self, user_id: int, username: str, room_id: str) -> None:
        if room_id in self._rooms:
            user_info = next((u for u in self._rooms[room_id] if u[0] == user_id), None)

            if user_info:
                self._rooms[room_id].remove(user_info)

                if user_id in self._user_rooms and room_id in self._user_rooms[user_id]:
                    self._user_rooms[user_id].remove(room_id)

                if not self._rooms[room_id]:
                    del self._rooms[room_id]
                else:
                    system_message = Message(
                        type=MessageType.CHAT_MESSAGE,
                        room_id=room_id,
                        username="System",
                        message=f"{username} has left the room"
                    )
                    await self._broadcast_to_room(room_id, system_message)

                leave_message = Message(
                    type=MessageType.ROOM_LEFT,
                    room_id=room_id,
                    message=f"Left chat room {room_id}"
                )
                await self.connection_manager.send_to_user(
                    json.dumps(leave_message.dict()), user_id
                )

                logger.info(f"User {username} (ID: {user_id}) left chat room {room_id}")

    async def _handle_chat_message(self, user_id: int, username: str, room_id: str, content: str) -> None:
        if not content.strip():
            return

        if room_id not in self._rooms:
            error_msg = Message(
                type=MessageType.ERROR,
                message=f"You are not in chat room {room_id}"
            )
            await self.connection_manager.send_to_user(json.dumps(error_msg.dict()), user_id)
            return

        user_in_room = any(u[0] == user_id for u in self._rooms[room_id])
        if not user_in_room:
            error_msg = Message(
                type=MessageType.ERROR,
                message=f"You are not in chat room {room_id}"
            )
            await self.connection_manager.send_to_user(json.dumps(error_msg.dict()), user_id)
            return

        chat_message = Message(
            type=MessageType.CHAT_MESSAGE,
            room_id=room_id,
            user_id=user_id,
            username=username,
            message=content
        )

        await self._broadcast_to_room(room_id, chat_message)
        logger.debug(f"Chat message from {username} in room {room_id}: {content}")

    async def _list_rooms(self, websocket) -> None:
        room_data = {
            "rooms": [
                {"id": room_id, "user_count": len(users)}
                for room_id, users in self._rooms.items()
            ]
        }

        message = Message(type=MessageType.ROOM_LIST, data=room_data)
        await websocket.send_text(json.dumps(message.dict()))

    async def _get_room_users(self, websocket, room_id: str) -> None:
        if room_id not in self._rooms:
            error_msg = Message(
                type=MessageType.ERROR, message=f"Chat room {room_id} does not exist"
            )
            await websocket.send_text(json.dumps(error_msg.dict()))
            return

        users = list(self._rooms[room_id])
        user_data = {
            "room_id": room_id,
            "users": [{"id": u[0], "username": u[1]} for u in users],
        }

        message = Message(type=MessageType.ROOM_USERS, data=user_data)
        await websocket.send_text(json.dumps(message.dict()))

    async def _broadcast_to_room(self, room_id: str, message: Message, exclude_user_id: int = None) -> None:
        if room_id not in self._rooms:
            return

        user_ids = [u[0] for u in self._rooms[room_id] if u[0] != exclude_user_id]
        if not user_ids:
            return

        await self.connection_manager.broadcast_to_users(
            json.dumps(message.dict()), user_ids
        )