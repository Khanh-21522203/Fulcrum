from __future__ import annotations

import os
import uuid

from fulcrum_shared.models import InstanceStatus, ServiceInstance

from control_plane.snapshot import (
    SnapshotBuilder,
    SnapshotCache,
    StaticServiceInstanceSource,
)

snapshot_cache = SnapshotCache()


def _snapshot_builder() -> SnapshotBuilder:
    if os.getenv("FULCRUM_DEV_SEED_INSTANCE") != "1":
        return SnapshotBuilder()

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
    return SnapshotBuilder(StaticServiceInstanceSource([instance]))


snapshot_builder = _snapshot_builder()
