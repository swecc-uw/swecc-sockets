import asyncio
import logging
import pika
from pika.adapters.asyncio_connection import AsyncioConnection
from typing import Any, Dict, Optional, Union
from .connection_manager import ConnectionManager

LOGGER = logging.getLogger(__name__)

MAX_RETRIES = 3


class AsyncRabbitProducer:

    def __init__(self, amqp_url, exchange, exchange_type, routing_key=None, loop=None):
        # config
        self._url = amqp_url
        self._exchange = exchange
        self._exchange_type = exchange_type
        self._default_routing_key = routing_key

        # connection state
        self._connection = None
        self._channel = None
        self._connected = False
        self._ready = asyncio.Event(loop=loop)

    async def connect(self, loop=None):

        if self._connected:
            return self._connection

        self._ready.clear()

        self._connection = await ConnectionManager(loop=loop).connect()

        LOGGER.info(f"Producer connecting to {self._url} for exchange {self._exchange}")
        if not self._connection:
            LOGGER.error(f"Failed to create connection for producer {self._exchange}")
            return False
        self._connected = True
        self.open_channel()

        await self._ready.wait()

        return self._connection

    def open_channel(self):
        LOGGER.info(f"Creating a new channel for producer {self._exchange}")
        if self._connection:
            self._connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel):
        LOGGER.info(f"Channel opened for producer {self._exchange}")
        self._channel = channel
        self._channel.add_on_close_callback(self.on_channel_closed)
        self.setup_exchange()

    def on_channel_closed(self, channel, reason):
        LOGGER.warning(f"Channel was closed for producer {self._exchange}: {reason}")
        self._channel = None

    def setup_exchange(self):
        LOGGER.info(f"Declaring exchange: {self._exchange}")
        if self._channel:
            self._channel.exchange_declare(
                exchange=self._exchange,
                exchange_type=self._exchange_type,
                callback=self.on_exchange_declareok,
            )
        else:
            LOGGER.warning(
                f"Channel is not open for exchange declaration: {self._exchange}"
            )

    def on_exchange_declareok(self, _unused_frame):
        LOGGER.info(f"Exchange declared: {self._exchange}")
        # signal ready to publish
        self._ready.set()

    async def publish(
        self, message, routing_key=None, properties=None, mandatory=False
    ):
        retry_count = 0

        while not self._connected and retry_count < MAX_RETRIES:
            try:
                connected = await self.connect()
                if not connected:
                    LOGGER.warning(
                        f"Failed to connect to RabbitMQ for publishing to {self._exchange}, attempt {retry_count+1}/{MAX_RETRIES}"
                    )
                    retry_count += 1
                    await asyncio.sleep(1)
                else:
                    break
            except Exception as e:
                LOGGER.error(f"Error connecting to RabbitMQ: {str(e)}")
                retry_count += 1
                await asyncio.sleep(1)

        if not self._connected or not self._channel:
            LOGGER.error(
                f"No connection or channel available for publishing to {self._exchange}"
            )
            return False

        await self._ready.wait()

        actual_routing_key = routing_key or self._default_routing_key
        if not actual_routing_key:
            LOGGER.error("No routing key specified for publishing")
            return False

        if isinstance(message, str):
            # convert to bytes
            message = message.encode("utf-8")

        try:
            self._channel.basic_publish(
                exchange=self._exchange,
                routing_key=actual_routing_key,
                body=message,
                properties=properties,
                mandatory=mandatory,
            )
            LOGGER.debug(
                f"Published message to {self._exchange} with routing key {actual_routing_key}"
            )
            return True
        except Exception as e:
            LOGGER.error(f"Failed to publish message: {str(e)}")
            # mark as disconnected so the health monitor will reconnect it
            # debatable whether this is the right approach, will have
            # to see how common failures are and whether they are naturally
            # recovered
            self._connected = False
            return False

    async def close(self):
        LOGGER.info(f"Closing producer for {self._exchange}")
        if self._channel and self._channel.is_open:
            self._channel.close()
        self._channel = None
