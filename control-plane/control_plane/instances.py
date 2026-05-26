from __future__ import annotations

import asyncio
import os
from threading import RLock
from typing import Any
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


class PostgresInstanceSource(SnapshotInstanceSource):
    """Read-only ServiceInstance source for xDS snapshots."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    async def list_ready(
        self,
        node_group: str = DEFAULT_NODE_GROUP,
    ) -> list[ServiceInstance]:
        return await asyncio.to_thread(self._list_ready_sync, node_group)

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        database_url = self._database_url or os.environ["FULCRUM_DATABASE_URL"]
        return psycopg.connect(database_url, row_factory=dict_row)

    def _list_ready_sync(self, node_group: str) -> list[ServiceInstance]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    service_id,
                    plan_id,
                    organization_id,
                    space_id,
                    parameters,
                    status,
                    last_operation_type,
                    last_operation_state,
                    last_operation_description,
                    last_operation_updated_at,
                    created_at,
                    updated_at
                FROM service_instances
                WHERE status = 'ready'
                  AND COALESCE(parameters->>'node_group', %s) = %s
                ORDER BY id
                """,
                (DEFAULT_NODE_GROUP, node_group),
            ).fetchall()
        return [_row_to_instance(row) for row in rows]


def _row_to_instance(row: dict[str, Any]) -> ServiceInstance:
    last_operation = None
    if row["last_operation_type"] is not None:
        last_operation = LastOperation(
            type=LastOperationType(row["last_operation_type"]),
            state=LastOperationState(row["last_operation_state"]),
            description=row["last_operation_description"],
            updated_at=row["last_operation_updated_at"],
        )

    return ServiceInstance(
        id=row["id"],
        service_id=row["service_id"],
        plan_id=row["plan_id"],
        organization_id=row["organization_id"],
        space_id=row["space_id"],
        parameters=dict(row["parameters"] or {}),
        status=InstanceStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_operation=last_operation,
    )
