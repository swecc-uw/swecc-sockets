from typing import Dict, Type, Optional
import logging
from .events import EventType

logger = logging.getLogger(__name__)


class ServiceRegistry:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceRegistry, cls).__new__(cls)
            cls._instance.services = {}
        return cls._instance
    
    def register(self, service_name: str, handler_class: Type) -> None:
        self.services[service_name] = handler_class()
        logger.info(f"Registered service: {service_name}")
    
    def get_service(self, service_name: str) -> Optional[object]:
        return self.services.get(service_name)