"""Base provider interface."""
from abc import ABC, abstractmethod
from typing import Any


class CloudProvider(ABC):
    """Abstract interface for cloud providers (Vultr, Runpod, etc.)."""

    @abstractmethod
    async def create_instance(self, **kwargs) -> dict:
        """Create a compute instance. Returns provider-specific instance data."""
        ...

    @abstractmethod
    async def get_instance(self, instance_id: str) -> dict | None:
        """Get instance details by provider ID."""
        ...

    @abstractmethod
    async def delete_instance(self, instance_id: str) -> bool:
        """Delete/destroy an instance."""
        ...

    @abstractmethod
    async def list_instances(self) -> list[dict]:
        """List all instances."""
        ...

    @abstractmethod
    async def start_instance(self, instance_id: str) -> bool:
        ...

    @abstractmethod
    async def stop_instance(self, instance_id: str) -> bool:
        ...
