import json
import logging
import asyncio
import docker
import os
from typing import Dict, Optional
from ..events import Event, EventType
from ..message import Message, MessageType
from ..connection_manager import ConnectionManager
from ..event_emitter import EventEmitter

logger = logging.getLogger(__name__)


class ContainerLogsHandler:
    def __init__(self):
        self.emitter = EventEmitter()
        self.connection_manager = ConnectionManager()
        self.running_streams = {}

        self.docker_client = docker.from_env()

        self.emitter.on(EventType.CONNECTION, self.handle_connect)
        self.emitter.on(EventType.MESSAGE, self.handle_message)
        self.emitter.on(EventType.DISCONNECT, self.handle_disconnect)

    async def handle_connect(self, event: Event) -> None:
        message = Message(
            type=MessageType.SYSTEM,
            message=f"Container logs service: Connected as {event.username}"
        )
        await event.websocket.send_text(json.dumps(message.dict()))
        logger.info(f"Container logs service: User {event.username} (ID: {event.user_id}) connected")

    async def handle_message(self, event: Event) -> None:
        try:
            # Check if user has admin or API key permissions
            if "groups" not in event.data or not any(group in event.data["groups"] for group in ["is_admin", "is_api_key"]):
                error_msg = Message(
                    type=MessageType.ERROR,
                    message="You don't have permission to access container logs"
                )
                await event.websocket.send_text(json.dumps(error_msg.dict()))
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
                await event.websocket.send_text(json.dumps(error_msg.dict()))

        except Exception as e:
            logger.error(f"Error processing logs message: {str(e)}", exc_info=True)
            error_msg = Message(
                type=MessageType.ERROR,
                message=f"Error processing your message: {str(e)}"
            )
            await event.websocket.send_text(json.dumps(error_msg.dict()))

    async def handle_disconnect(self, event: Event) -> None:
        user_id = event.user_id
        await self._stop_logs(user_id)
        logger.info(f"Container logs service: User {event.username} (ID: {user_id}) disconnected")

    async def _start_logs(self, user_id: int, container_name: str, websocket) -> None:
        await self._stop_logs(user_id)

        try:
            try:
                container = self.docker_client.containers.get(container_name)
            except docker.errors.NotFound:
                error_msg = Message(
                    type=MessageType.ERROR,
                    message=f"Container '{container_name}' not found"
                )
                await websocket.send_text(json.dumps(error_msg.dict()))
                return
            except docker.errors.APIError as e:
                error_msg = Message(
                    type=MessageType.ERROR,
                    message=f"Docker API error: {str(e)}"
                )
                await websocket.send_text(json.dumps(error_msg.dict()))
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
            await websocket.send_text(json.dumps(message.dict()))

            logger.info(f"Started log streaming for container {container_name} for user {user_id}")

        except Exception as e:
            logger.error(f"Error starting logs: {str(e)}", exc_info=True)
            error_msg = Message(
                type=MessageType.ERROR,
                message=f"Error starting logs: {str(e)}"
            )
            await websocket.send_text(json.dumps(error_msg.dict()))

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
            if user_id in self.running_streams:
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
            await websocket.send_text(json.dumps(log_message.dict()))
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
          await websocket.send_text(json.dumps(error_msg.dict()))
        except:
          pass
      finally:
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