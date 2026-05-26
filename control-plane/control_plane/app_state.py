from __future__ import annotations

import os
import uuid

from fulcrum_shared.models import InstanceStatus, ServiceInstance
from fulcrum_shared.ports import ObjectStore, SnapshotInstanceSource

from control_plane.instances import InMemoryInstanceRepository
from control_plane.snapshot import SnapshotBuilder, SnapshotCache


def _create_local_snapshot_source() -> SnapshotInstanceSource:
    from fulcrum_provider_local import create_snapshot_source

    return create_snapshot_source()


def _create_local_object_store() -> ObjectStore:
    from fulcrum_provider_local import create_object_store

    return create_object_store()


snapshot_cache = SnapshotCache()
instance_repository = InMemoryInstanceRepository()
snapshot_source: SnapshotInstanceSource = (
    instance_repository
    if os.getenv("FULCRUM_CP_INSTANCE_SOURCE", "postgres") == "memory"
    or "FULCRUM_DATABASE_URL" not in os.environ
    else _create_local_snapshot_source()
)
object_store: ObjectStore | None = (
    _create_local_object_store()
    if os.getenv("FULCRUM_OBJECT_STORE_PROVIDER") == "minio"
    else None
)


async def seed_dev_instance() -> None:
    if os.getenv("FULCRUM_DEV_SEED_INSTANCE") != "1":
        return

    node_group = os.getenv("FULCRUM_DEV_NODE_GROUP", "local")
    instance = ServiceInstance(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        service_id="load-balancer",
        plan_id="standard",
        organization_id="dev-org",
        space_id="dev-space",
        status=InstanceStatus.READY,
        parameters={
            "domains": ["*"],
            "upstream_host": os.getenv("FULCRUM_DEV_UPSTREAM_HOST", "example.com"),
            "upstream_port": int(os.getenv("FULCRUM_DEV_UPSTREAM_PORT", "80")),
            "timeout_seconds": 15,
            "node_group": node_group,
            "tls": False,
        },
    )
    await instance_repository.put(instance)


snapshot_builder = SnapshotBuilder(snapshot_source)
