from typing import Dict, List, Callable, Any
import logging
import asyncio
from .events import Event, EventType

logger = logging.getLogger(__name__)


class EventEmitter:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventEmitter, cls).__new__(cls)
            cls._instance.listeners = {}
        return cls._instance
    
    def on(self, event_type: EventType, listener: Callable) -> None:
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(listener)
    
    def off(self, event_type: EventType, listener: Callable) -> None:
        if event_type in self.listeners and listener in self.listeners[event_type]:
            self.listeners[event_type].remove(listener)
    
    async def emit(self, event: Event) -> None:
        if event.type not in self.listeners:
            return
            
        tasks = []
        for listener in self.listeners[event.type]:
            tasks.append(self._safe_execute(listener, event))
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_execute(self, listener: Callable, event: Event) -> None:
        try:
            await listener(event)
        except Exception as e:
            logger.error(f"Error in event listener: {str(e)}", exc_info=True)

