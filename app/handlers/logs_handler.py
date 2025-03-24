import json
import logging
import asyncio
import docker
from typing import Dict
from ..events import Event, EventType
from ..message import Message, MessageType

logger = logging.getLogger(__name__)


class ContainerLogsHandler:
    def __init__(self, event_emitter):
        self.event_emitter = event_emitter
        self.running_streams = {}

        # Initialize Docker client
        self.docker_client = docker.from_env()

        # Register event listeners
        self.event_emitter.on(EventType.CONNECTION, self.handle_connect)
        self.event_emitter.on(EventType.MESSAGE, self.handle_message)
        self.event_emitter.on(EventType.DISCONNECT, self.handle_disconnect)

    async def handle_connect(self, event: Event) -> None:
        try:
            message = Message(
                type=MessageType.SYSTEM,
                message=f"Logs service: Connected as {event.username}"
            )
            await self.safe_send(event.websocket, message.dict())
            logger.info(f"Logs service: User {event.username} (ID: {event.user_id}) connected")
        except Exception as e:
            logger.error(f"Error in handle_connect: {str(e)}", exc_info=True)

    async def handle_message(self, event: Event) -> None:
        try:
            # Check if user has proper permissions
            if "groups" not in event.data or not any(group in event.data["groups"] for group in ["is_admin", "is_api_key"]):
                error_msg = Message(
                    type=MessageType.ERROR,
                    message="You don't have permission to access container logs"
                )
                await self.safe_send(event.websocket, error_msg.dict())
                return

            message_type = event.data.get("type")
            container_name = event.data.get("container_name")

            if message_type == "start_logs" and container_name:
                await self._start_logs(event.user_id, container_name, event.websocket)
            elif message_type == "stop_logs":
                await self._stop_logs(event.user_id)
            else:
                error_msg = Message(
                    type=MessageType.ERROR,
                    message="Unknown logs command. Available commands: start_logs, stop_logs"
                )
                await self.safe_send(event.websocket, error_msg.dict())

        except Exception as e:
            logger.error(f"Error processing logs message: {str(e)}", exc_info=True)
            error_msg = Message(
                type=MessageType.ERROR,
                message=f"Error processing your message: {str(e)}"
            )
            await self.safe_send(event.websocket, error_msg.dict())

    async def handle_disconnect(self, event: Event) -> None:
        try:
            user_id = event.user_id
            await self._stop_logs(user_id)
            logger.info(f"Logs service: User {event.username} (ID: {user_id}) disconnected")
        except Exception as e:
            logger.error(f"Error in handle_disconnect: {str(e)}", exc_info=True)

    async def _start_logs(self, user_id: int, container_name: str, websocket) -> None:
        # First stop any existing log streams
        await self._stop_logs(user_id)

        try:
            try:
                container = self.docker_client.containers.get(container_name)
            except docker.errors.NotFound:
                error_msg = Message(
                    type=MessageType.ERROR,
                    message=f"Container '{container_name}' not found"
                )
                await self.safe_send(websocket, error_msg.dict())
                return
            except docker.errors.APIError as e:
                error_msg = Message(
                    type=MessageType.ERROR,
                    message=f"Docker API error: {str(e)}"
                )
                await self.safe_send(websocket, error_msg.dict())
                return

            # Create a new task for streaming
            stream_task = asyncio.create_task(
                self._stream_logs(user_id, container, websocket)
            )

            self.running_streams[user_id] = {
                "task": stream_task,
                "container_name": container_name
            }

            # Send confirmation message
            message = Message(
                type=MessageType.LOGS_STARTED,
                message=f"Started streaming logs for container: {container_name}"
            )
            await self.safe_send(websocket, message.dict())

            logger.info(f"Started log streaming for container {container_name} for user {user_id}")

        except Exception as e:
            logger.error(f"Error starting logs: {str(e)}", exc_info=True)
            error_msg = Message(
                type=MessageType.ERROR,
                message=f"Error starting logs: {str(e)}"
            )
            await self.safe_send(websocket, error_msg.dict())

    async def _stop_logs(self, user_id: int) -> None:
        if user_id in self.running_streams:
            stream_info = self.running_streams[user_id]
            
            # Cancel the streaming task
            if "task" in stream_info and not stream_info["task"].done():
                stream_info["task"].cancel()
                
                try:
                    await stream_info["task"]
                except asyncio.CancelledError:
                    pass

            # Remove from tracking
            del self.running_streams[user_id]
            logger.info(f"Stopped log streaming for user {user_id}")

    async def _stream_logs(self, user_id: int, container, websocket) -> None:
        try:
            logs_generator = container.logs(stream=True, follow=True, timestamps=True, tail=100)

            async for log_chunk in self._async_log_generator(logs_generator):
                if asyncio.current_task().cancelled():
                    break

                try:
                    log_message = Message(
                        type=MessageType.LOG_LINE,
                        message=log_chunk.strip()
                    )
                    await self.safe_send(websocket, log_message.dict())
                except Exception as e:
                    logger.error(f"Error sending log line: {str(e)}")
                    break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in log streaming: {str(e)}", exc_info=True)
            try:
                error_msg = Message(
                    type=MessageType.ERROR,
                    message=f"Error in log streaming: {str(e)}"
                )
                await self.safe_send(websocket, error_msg.dict())
            except:
                pass
        finally:
            # Ensure we clean up
            if user_id in self.running_streams:
                await self._stop_logs(user_id)

    async def _async_log_generator(self, logs_generator):
        loop = asyncio.get_event_loop()
        line_buffer = ""

        for log_chunk in iter(lambda: loop.run_in_executor(None, next, logs_generator, None), None):
            if asyncio.current_task().cancelled():
                break

            chunk = await log_chunk
            if chunk is None:
                break

            line_buffer += chunk.decode('utf-8', errors='replace')

            while '\n' in line_buffer:
                line, line_buffer = line_buffer.split('\n', 1)
                yield line

        if line_buffer:
            yield line_buffer

    async def safe_send(self, websocket, data):
        """Safely send a message, handling potential disconnection gracefully"""
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            # Just log the error
            logger.debug(f"Could not send message, websocket may be closed: {str(e)}")