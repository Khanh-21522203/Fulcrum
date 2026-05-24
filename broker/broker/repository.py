import uuid

from fulcrum_shared.models import InstanceStatus, ServiceInstance


class InstanceRepository:
    """Abstracts Cosmos DB reads and writes for ServiceInstance documents."""

    async def get(self, instance_id: uuid.UUID) -> ServiceInstance:
        raise NotImplementedError

    async def put(self, instance: ServiceInstance) -> None:
        raise NotImplementedError

    async def update_status(
        self, instance_id: uuid.UUID, status: InstanceStatus
    ) -> None:
        raise NotImplementedError
