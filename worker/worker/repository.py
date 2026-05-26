from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fulcrum_shared.models import (
    InstanceStatus,
    LastOperationState,
    ProvisioningTask,
    TaskType,
)


@dataclass(frozen=True)
class ClaimedTask:
    task: ProvisioningTask
    status: str


class PostgresTaskRepository:
    def __init__(self, database_url: str | None = None, *, worker_id: str | None = None) -> None:
        self._database_url = database_url
        self._worker_id = worker_id or f"worker-{uuid.uuid4()}"

    async def claim_next(self) -> ClaimedTask | None:
        return await asyncio.to_thread(self._claim_next_sync)

    async def complete(self, task: ProvisioningTask) -> None:
        await asyncio.to_thread(self._complete_sync, task)

    async def fail(self, task: ProvisioningTask, error: str) -> None:
        await asyncio.to_thread(self._fail_sync, task, error)

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        database_url = self._database_url or os.environ["FULCRUM_DATABASE_URL"]
        return psycopg.connect(database_url, row_factory=dict_row)

    def _claim_next_sync(self) -> ClaimedTask | None:
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    SELECT
                        task_id,
                        instance_id,
                        task_type,
                        payload,
                        attempt,
                        enqueued_at,
                        status
                    FROM provisioning_tasks
                    WHERE status = 'pending'
                      AND available_at <= now()
                    ORDER BY enqueued_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    return None
                conn.execute(
                    """
                    UPDATE provisioning_tasks
                    SET status = 'processing',
                        locked_at = now(),
                        locked_by = %s,
                        attempt = attempt + 1
                    WHERE task_id = %s
                    """,
                    (self._worker_id, row["task_id"]),
                )
        return ClaimedTask(task=_row_to_task(row), status="processing")

    def _complete_sync(self, task: ProvisioningTask) -> None:
        instance_status = (
            InstanceStatus.DELETED
            if task.task_type == TaskType.DEPROVISION
            else InstanceStatus.READY
        )
        description = (
            "Instance deprovisioned."
            if task.task_type == TaskType.DEPROVISION
            else "Instance ready."
        )
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    UPDATE service_instances
                    SET status = %s,
                        last_operation_state = %s,
                        last_operation_description = %s,
                        last_operation_updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        instance_status.value,
                        LastOperationState.SUCCEEDED.value,
                        description,
                        task.instance_id,
                    ),
                )
                conn.execute(
                    """
                    UPDATE provisioning_tasks
                    SET status = 'succeeded',
                        completed_at = now(),
                        locked_at = NULL,
                        locked_by = NULL
                    WHERE task_id = %s
                    """,
                    (task.task_id,),
                )

    def _fail_sync(self, task: ProvisioningTask, error: str) -> None:
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    UPDATE service_instances
                    SET status = 'failed',
                        last_operation_state = 'failed',
                        last_operation_description = %s,
                        last_operation_updated_at = now()
                    WHERE id = %s
                    """,
                    (error, task.instance_id),
                )
                conn.execute(
                    """
                    UPDATE provisioning_tasks
                    SET status = 'failed',
                        completed_at = now(),
                        locked_at = NULL,
                        locked_by = NULL,
                        last_error = %s
                    WHERE task_id = %s
                    """,
                    (error, task.task_id),
                )


def _row_to_task(row: dict[str, Any]) -> ProvisioningTask:
    return ProvisioningTask(
        task_id=row["task_id"],
        instance_id=row["instance_id"],
        task_type=TaskType(row["task_type"]),
        payload=dict(row["payload"] or {}),
        attempt=int(row["attempt"]),
        enqueued_at=_as_datetime(row["enqueued_at"]),
    )


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)
