from abc import ABC, abstractmethod


class CloudProvider(ABC):
    @abstractmethod
    async def create_instance(self, **kwargs) -> dict: ...

    @abstractmethod
    async def get_instance(self, instance_id: str) -> dict | None: ...

    @abstractmethod
    async def delete_instance(self, instance_id: str) -> bool: ...

    @abstractmethod
    async def list_instances(self) -> list[dict]: ...

    @abstractmethod
    async def start_instance(self, instance_id: str) -> bool: ...

    @abstractmethod
    async def stop_instance(self, instance_id: str) -> bool: ...
