from __future__ import annotations

from threading import RLock
from uuid import UUID

from fulcrum_shared.models import (
    InstanceStatus,
    LastOperation,
    LastOperationState,
    LastOperationType,
    ServiceInstance,
    utc_now,
)
from fulcrum_shared.ports import SnapshotInstanceSource

from control_plane.snapshot import DEFAULT_NODE_GROUP, instance_node_group


class InMemoryInstanceRepository(SnapshotInstanceSource):
    """Process-local ServiceInstance store used for local development and tests."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._instances: dict[UUID, ServiceInstance] = {}

    async def put(self, instance: ServiceInstance) -> ServiceInstance:
        with self._lock:
            self._instances[instance.id] = instance.model_copy(deep=True)
            return self._instances[instance.id].model_copy(deep=True)

    async def get(self, instance_id: UUID) -> ServiceInstance | None:
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return None
            return instance.model_copy(deep=True)

    async def delete(self, instance_id: UUID) -> ServiceInstance | None:
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return None
            deleted = instance.model_copy(
                deep=True,
                update={
                    "status": InstanceStatus.DELETED,
                    "updated_at": utc_now(),
                    "last_operation": LastOperation(
                        type=LastOperationType.DEPROVISION,
                        state=LastOperationState.SUCCEEDED,
                        description="Instance deprovisioned from memory store.",
                    ),
                },
            )
            self._instances[instance_id] = deleted
            return deleted.model_copy(deep=True)

    async def list(
        self,
        *,
        node_group: str | None = None,
        include_deleted: bool = False,
    ) -> list[ServiceInstance]:
        with self._lock:
            instances = [
                instance.model_copy(deep=True)
                for instance in self._instances.values()
                if (include_deleted or instance.status != InstanceStatus.DELETED)
                and (node_group is None or instance_node_group(instance) == node_group)
            ]
        return sorted(instances, key=lambda instance: str(instance.id))

    async def list_ready(
        self,
        node_group: str = DEFAULT_NODE_GROUP,
    ) -> list[ServiceInstance]:
        return [
            instance
            for instance in await self.list(node_group=node_group)
            if instance.status == InstanceStatus.READY
        ]

    def clear(self) -> None:
        with self._lock:
            self._instances.clear()
