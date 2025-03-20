from fastapi import WebSocket
import json
import logging
from typing import Dict, Set, List
from .base_handler import WebSocketHandler
from ..models.message import Message, MessageType
from ..managers.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

class PresenceHandler(WebSocketHandler):
    
    def __init__(self, connection_manager: ConnectionManager):

        self._rooms: Dict[str, Set[tuple]] = {}

        self._user_rooms: Dict[int, Set[str]] = {}
        self.connection_manager = connection_manager
        
    async def handle_connect(self, websocket: WebSocket, user_id: int, username: str):
        await websocket.send_text(
            json.dumps(
                Message(
                    type=MessageType.SYSTEM,
                    message=f"Presence service: Connected as {username}"
                ).dict()
            )
        )
        logger.info(f"Presence service: User {username} (ID: {user_id}) connected")

    async def handle_message(self, websocket: WebSocket, user_id: int, username: str, data: str):
        try:
            message_data = json.loads(data)

            if isinstance(message_data, dict) and "type" in message_data:
                message_type = message_data.get("type")

                if message_type == "join_room":
                    room_id = message_data.get("room_id")
                    if room_id:
                        await self._join_room(websocket, user_id, username, room_id)
                        return

                elif message_type == "leave_room":
                    room_id = message_data.get("room_id")
                    if room_id:
                        await self._leave_room(user_id, username, room_id)
                        return

                elif message_type == "list_rooms":
                    await self._send_room_list(websocket, user_id)
                    return

                elif message_type == "get_room_users":
                    room_id = message_data.get("room_id")
                    if room_id:
                        await self._send_room_users(websocket, room_id)
                        return


            error_msg = Message(
                type=MessageType.ERROR,
                message=f"Unknown presence command. Available commands: join_room, leave_room, list_rooms, get_room_users"
            )
            await websocket.send_text(json.dumps(error_msg.dict()))

        except json.JSONDecodeError:
            error_msg = Message(
                type=MessageType.ERROR,
                message=f"Invalid message format. Expected JSON with 'type' field"
            )
            await websocket.send_text(json.dumps(error_msg.dict()))

        except Exception as e:
            logger.error(f"Error processing presence message: {str(e)}", exc_info=True)
            error_msg = Message(
                type=MessageType.ERROR,
                message=f"Error processing your message: {str(e)}"
            )
            await websocket.send_text(json.dumps(error_msg.dict()))

    async def handle_disconnect(self, user_id: int, username: str):
        if user_id in self._user_rooms:
            rooms_to_leave = list(self._user_rooms[user_id])
            for room_id in rooms_to_leave:
                await self._leave_room(user_id, username, room_id)

            if user_id in self._user_rooms:
                del self._user_rooms[user_id]

        logger.info(f"Presence service: User {username} (ID: {user_id}) disconnected")

    async def _join_room(self, websocket: WebSocket, user_id: int, username: str, room_id: str):
        """Add a user to a room and notify all users in the room"""
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
    
    async def _leave_room(self, user_id: int, username: str, room_id: str):
        """Remove a user from a room and notify all users in the room"""
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
                await self.connection_manager.send_message(json.dumps(message.dict()), user_id)
    
    async def _broadcast_presence(self, room_id: str):
        """Broadcast the current presence state to all users in a room"""
        if room_id not in self._rooms:
            return
        

        users = list(self._rooms[room_id])
        user_ids = [u[0] for u in users]
        

        presence_data = {
            "user_count": len(users),
            "users": [{"id": u[0], "username": u[1]} for u in users]
        }

        message = Message(
            type=MessageType.PRESENCE_UPDATE,
            room_id=room_id,
            data=presence_data
        )
        

        for user_id in user_ids:
            await self.connection_manager.send_message(json.dumps(message.dict()), user_id)

    async def _send_room_list(self, websocket: WebSocket, user_id: int):
        """Send list of all available rooms"""
        room_data = {
            "rooms": [
                {
                    "id": room_id,
                    "user_count": len(users)
                }
                for room_id, users in self._rooms.items()
            ]
        }
        
        message = Message(
            type=MessageType.ROOM_LIST,
            data=room_data
        )

        await websocket.send_text(json.dumps(message.dict()))

    async def _send_room_users(self, websocket: WebSocket, room_id: str):
        """Send list of users in a specific room"""
        if room_id not in self._rooms:
            error_msg = Message(
                type=MessageType.ERROR,
                message=f"Room {room_id} does not exist"
            )
            await websocket.send_text(json.dumps(error_msg.dict()))
            return

        users = list(self._rooms[room_id])

        user_data = {
            "room_id": room_id,
            "users": [{"id": u[0], "username": u[1]} for u in users]
        }

        message = Message(
            type=MessageType.ROOM_USERS,
            data=user_data
        )

        await websocket.send_text(json.dumps(message.dict()))