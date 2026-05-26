from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Any, Protocol

from fulcrum_shared.models import (
    InstanceStatus,
    LastOperation,
    LastOperationState,
    LastOperationType,
    ProvisioningTask,
    ServiceInstance,
)


class InstanceRepository(Protocol):
    async def get(self, instance_id: uuid.UUID) -> ServiceInstance | None:
        ...

    async def put_with_task(
        self,
        instance: ServiceInstance,
        task: ProvisioningTask,
    ) -> None:
        ...


class PostgresInstanceRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    async def get(self, instance_id: uuid.UUID) -> ServiceInstance | None:
        return await asyncio.to_thread(self._get_sync, instance_id)

    async def put_with_task(
        self,
        instance: ServiceInstance,
        task: ProvisioningTask,
    ) -> None:
        await asyncio.to_thread(self._put_with_task_sync, instance, task)

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        database_url = self._database_url or os.environ["FULCRUM_DATABASE_URL"]
        return psycopg.connect(database_url, row_factory=dict_row)

    def _get_sync(self, instance_id: uuid.UUID) -> ServiceInstance | None:
        with self._connect() as conn:
            row = conn.execute(
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
                WHERE id = %s
                """,
                (instance_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_instance(row)

    def _put_with_task_sync(
        self,
        instance: ServiceInstance,
        task: ProvisioningTask,
    ) -> None:
        operation = instance.last_operation
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO service_instances (
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
                    )
                    VALUES (
                        %(id)s,
                        %(service_id)s,
                        %(plan_id)s,
                        %(organization_id)s,
                        %(space_id)s,
                        %(parameters)s::jsonb,
                        %(status)s,
                        %(last_operation_type)s,
                        %(last_operation_state)s,
                        %(last_operation_description)s,
                        %(last_operation_updated_at)s,
                        %(created_at)s,
                        %(updated_at)s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        service_id = EXCLUDED.service_id,
                        plan_id = EXCLUDED.plan_id,
                        organization_id = EXCLUDED.organization_id,
                        space_id = EXCLUDED.space_id,
                        parameters = EXCLUDED.parameters,
                        status = EXCLUDED.status,
                        last_operation_type = EXCLUDED.last_operation_type,
                        last_operation_state = EXCLUDED.last_operation_state,
                        last_operation_description = EXCLUDED.last_operation_description,
                        last_operation_updated_at = EXCLUDED.last_operation_updated_at
                    """,
                    {
                        "id": instance.id,
                        "service_id": instance.service_id,
                        "plan_id": instance.plan_id,
                        "organization_id": instance.organization_id,
                        "space_id": instance.space_id,
                        "parameters": json.dumps(instance.parameters),
                        "status": instance.status.value,
                        "last_operation_type": operation.type.value if operation else None,
                        "last_operation_state": operation.state.value if operation else None,
                        "last_operation_description": operation.description
                        if operation
                        else "",
                        "last_operation_updated_at": operation.updated_at
                        if operation
                        else None,
                        "created_at": instance.created_at,
                        "updated_at": instance.updated_at,
                    },
                )
                conn.execute(
                    """
                    INSERT INTO provisioning_tasks (
                        task_id,
                        instance_id,
                        task_type,
                        payload,
                        attempt,
                        enqueued_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                    """,
                    (
                        task.task_id,
                        task.instance_id,
                        task.task_type.value,
                        json.dumps(task.payload),
                        task.attempt,
                        task.enqueued_at,
                    ),
                )


def _row_to_instance(row: dict[str, Any]) -> ServiceInstance:
    last_operation = None
    if row["last_operation_type"] is not None:
        last_operation = LastOperation(
            type=LastOperationType(row["last_operation_type"]),
            state=LastOperationState(row["last_operation_state"]),
            description=row["last_operation_description"],
            updated_at=_as_datetime(row["last_operation_updated_at"]),
        )

    return ServiceInstance(
        id=row["id"],
        service_id=row["service_id"],
        plan_id=row["plan_id"],
        organization_id=row["organization_id"],
        space_id=row["space_id"],
        parameters=dict(row["parameters"] or {}),
        status=InstanceStatus(row["status"]),
        created_at=_as_datetime(row["created_at"]),
        updated_at=_as_datetime(row["updated_at"]),
        last_operation=last_operation,
    )


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
