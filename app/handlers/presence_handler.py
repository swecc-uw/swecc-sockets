import json
import logging
from typing import Dict, Set, Tuple
from ..events import Event, EventType
from ..message import Message, MessageType
from ..connection_manager import ConnectionManager
from ..event_emitter import EventEmitter

logger = logging.getLogger(__name__)


class PresenceHandler:
    def __init__(self):
        self.emitter = EventEmitter()
        self.connection_manager = ConnectionManager()
        self._rooms: Dict[str, Set[Tuple[int, str]]] = {}
        self._user_rooms: Dict[int, Set[str]] = {}

        self.emitter.on(EventType.CONNECTION, self.handle_connect)
        self.emitter.on(EventType.MESSAGE, self.handle_message)
        self.emitter.on(EventType.DISCONNECT, self.handle_disconnect)
        self.emitter.on(EventType.JOIN_ROOM, self.join_room)
        self.emitter.on(EventType.LEAVE_ROOM, self.leave_room)
        self.emitter.on(EventType.LIST_ROOMS, self.list_rooms)
        self.emitter.on(EventType.GET_ROOM_USERS, self.get_room_users)

    async def handle_connect(self, event: Event) -> None:
        message = Message(
            type=MessageType.SYSTEM,
            message=f"Presence service: Connected as {event.username}"
        )
        await event.websocket.send_text(json.dumps(message.dict()))
        logger.info(f"Presence service: User {event.username} (ID: {event.user_id}) connected")

    async def handle_message(self, event: Event) -> None:
        try:
            message_type = event.data.get("type")
            room_id = event.data.get("room_id")

            if message_type == "join_room" and room_id:
                await self.emitter.emit(Event(
                    type=EventType.JOIN_ROOM,
                    user_id=event.user_id,
                    username=event.username,
                    websocket=event.websocket,
                    room_id=room_id
                ))
            elif message_type == "leave_room" and room_id:
                await self.emitter.emit(Event(
                    type=EventType.LEAVE_ROOM,
                    user_id=event.user_id,
                    username=event.username,
                    websocket=event.websocket,
                    room_id=room_id
                ))
            elif message_type == "list_rooms":
                await self.emitter.emit(Event(
                    type=EventType.LIST_ROOMS,
                    user_id=event.user_id,
                    username=event.username,
                    websocket=event.websocket
                ))
            elif message_type == "get_room_users" and room_id:
                await self.emitter.emit(Event(
                    type=EventType.GET_ROOM_USERS,
                    user_id=event.user_id,
                    username=event.username,
                    websocket=event.websocket,
                    room_id=room_id
                ))
            else:
                error_msg = Message(
                    type=MessageType.ERROR,
                    message="Unknown presence command. Available commands: join_room, leave_room, list_rooms, get_room_users"
                )
                await event.websocket.send_text(json.dumps(error_msg.dict()))

        except Exception as e:
            logger.error(f"Error processing presence message: {str(e)}", exc_info=True)
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
                await self.leave_room(Event(
                    type=EventType.LEAVE_ROOM,
                    user_id=user_id,
                    username=username,
                    room_id=room_id
                ))

            if user_id in self._user_rooms:
                del self._user_rooms[user_id]

        logger.info(f"Presence service: User {username} (ID: {user_id}) disconnected")

    async def join_room(self, event: Event) -> None:
        user_id = event.user_id
        username = event.username
        room_id = event.room_id
        websocket = event.websocket

        user_info = (user_id, username)

        if room_id not in self._rooms:
            self._rooms[room_id] = set()

        self._rooms[room_id].add(user_info)

        if user_id not in self._user_rooms:
            self._user_rooms[user_id] = set()
        self._user_rooms[user_id].add(room_id)

        await websocket.send_text(
            json.dumps(
                Message(
                    type=MessageType.ROOM_JOINED,
                    room_id=room_id,
                    message=f"Joined room {room_id}"
                ).dict()
            )
        )

        await self._broadcast_presence(room_id)

        logger.info(f"User {username} (ID: {user_id}) joined room {room_id}")

    async def leave_room(self, event: Event) -> None:
        user_id = event.user_id
        username = event.username
        room_id = event.room_id

        if room_id in self._rooms:
            user_info = next((u for u in self._rooms[room_id] if u[0] == user_id), None)

            if user_info:
                self._rooms[room_id].remove(user_info)

                if user_id in self._user_rooms and room_id in self._user_rooms[user_id]:
                    self._user_rooms[user_id].remove(room_id)

                if not self._rooms[room_id]:
                    del self._rooms[room_id]

                await self._broadcast_presence(room_id)

                logger.info(f"User {username} (ID: {user_id}) left room {room_id}")

                message = Message(
                    type=MessageType.ROOM_LEFT,
                    room_id=room_id,
                    message=f"Left room {room_id}"
                )
                await self.connection_manager.send_to_user(
                    json.dumps(message.dict()), user_id
                )

    async def list_rooms(self, event: Event) -> None:
        room_data = {
            "rooms": [
                {"id": room_id, "user_count": len(users)}
                for room_id, users in self._rooms.items()
            ]
        }

        message = Message(type=MessageType.ROOM_LIST, data=room_data)
        await event.websocket.send_text(json.dumps(message.dict()))

    async def get_room_users(self, event: Event) -> None:
        room_id = event.room_id

        if room_id not in self._rooms:
            error_msg = Message(
                type=MessageType.ERROR, message=f"Room {room_id} does not exist"
            )
            await event.websocket.send_text(json.dumps(error_msg.dict()))
            return

        users = list(self._rooms[room_id])

        user_data = {
            "room_id": room_id,
            "users": [{"id": u[0], "username": u[1]} for u in users],
        }

        message = Message(type=MessageType.ROOM_USERS, data=user_data)
        await event.websocket.send_text(json.dumps(message.dict()))

    async def _broadcast_presence(self, room_id: str) -> None:
        if room_id not in self._rooms:
            return

        users = list(self._rooms[room_id])
        user_ids = [u[0] for u in users]

        presence_data = {
            "user_count": len(users),
            "users": [{"id": u[0], "username": u[1]} for u in users],
        }

        message = Message(
            type=MessageType.PRESENCE_UPDATE, room_id=room_id, data=presence_data
        )

        await self.connection_manager.broadcast_to_users(
            json.dumps(message.dict()), user_ids
        )