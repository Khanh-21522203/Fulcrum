from __future__ import annotations

import os
import uuid

from fulcrum_shared.models import InstanceStatus, ServiceInstance

from control_plane.instances import InMemoryInstanceRepository
from control_plane.snapshot import SnapshotBuilder, SnapshotCache

snapshot_cache = SnapshotCache()
instance_repository = InMemoryInstanceRepository()


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


snapshot_builder = SnapshotBuilder(instance_repository)
