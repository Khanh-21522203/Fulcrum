from __future__ import annotations

import uuid
from typing import Protocol

from fulcrum_shared.models import ProvisioningTask, ServiceInstance


class InstanceStore(Protocol):
    """Cloud-neutral service-instance write port used by broker-like APIs."""

    async def get(self, instance_id: uuid.UUID) -> ServiceInstance | None:
        ...

    async def put_with_task(
        self,
        instance: ServiceInstance,
        task: ProvisioningTask,
    ) -> None:
        ...


class SnapshotInstanceSource(Protocol):
    """Read-only source of routable instances used by the control plane."""

    async def list_ready(self, node_group: str) -> list[ServiceInstance]:
        ...
