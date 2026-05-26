from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

from fulcrum_shared.models import (
    InstanceStatus,
    LastOperation,
    LastOperationState,
    LastOperationType,
    ServiceInstance,
)
from fulcrum_shared.ports import SnapshotInstanceSource

DEFAULT_NODE_GROUP = "default"


class PostgresSnapshotInstanceSource(SnapshotInstanceSource):
    """Read-only local Postgres source for control-plane xDS snapshots."""

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
