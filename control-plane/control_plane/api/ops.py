from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from control_plane.app_state import (
    instance_repository,
    snapshot_builder,
    snapshot_cache,
)
from control_plane.snapshot import (
    DEFAULT_NODE_GROUP,
    DEFAULT_TIMEOUT_SECONDS,
    Snapshot,
    SnapshotBuilder,
    StaticServiceInstanceSource,
    instance_node_group,
)
from fulcrum_shared.models import InstanceStatus, ServiceInstance, utc_now

router = APIRouter()


class SnapshotInvalidateRequest(BaseModel):
    node_group: str = "default"


class InstanceUpsertRequest(BaseModel):
    id: UUID | None = None
    service_id: str = "load-balancer"
    plan_id: str = "standard"
    organization_id: str = "dev-org"
    space_id: str = "dev-space"
    status: InstanceStatus = InstanceStatus.READY
    node_group: str = DEFAULT_NODE_GROUP
    domains: list[str] = Field(default_factory=lambda: ["*"], min_length=1)
    upstream_host: str
    upstream_port: int = Field(gt=0)
    timeout_seconds: int = Field(default=DEFAULT_TIMEOUT_SECONDS, gt=0)
    path_prefix: str = "/"
    tls: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)


def snapshot_summary(snapshot: Snapshot) -> dict:
    return {
        "node_group": snapshot.node_group,
        "version": snapshot.version,
        "updated_at": snapshot.updated_at.isoformat(),
        "resources": snapshot.resource_counts(),
    }


def instance_summary(instance: ServiceInstance) -> dict:
    return instance.model_dump(mode="json")


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict:
    snapshots = snapshot_cache.all()
    if not snapshots:
        raise HTTPException(503, "no snapshots loaded")
    return {
        "status": "ready",
        "snapshots": len(snapshots),
    }


@router.get("/snapshots")
async def list_snapshots() -> dict:
    return {
        "snapshots": [
            snapshot_summary(snapshot)
            for snapshot in snapshot_cache.all().values()
        ]
    }


@router.post("/snapshots/invalidate", status_code=202)
async def invalidate_snapshots(body: SnapshotInvalidateRequest) -> dict:
    snapshot = await _rebuild_snapshot(body.node_group)
    return {
        "status": "rebuilt",
        "snapshot": snapshot_summary(snapshot),
    }


@router.get("/snapshots/{node_group}/diff")
async def snapshot_diff(node_group: str) -> dict:
    current = snapshot_cache.get(node_group)
    if current is None:
        raise HTTPException(404, "snapshot not found")

    previous = snapshot_cache.previous(node_group)
    return {
        "node_group": node_group,
        "previous": snapshot_summary(previous) if previous else None,
        "current": snapshot_summary(current),
    }


@router.post("/instances", status_code=201)
async def upsert_instance(body: InstanceUpsertRequest) -> dict:
    instance_id = body.id or uuid4()
    existing = await instance_repository.get(instance_id)
    now = utc_now()
    parameters = {
        **body.parameters,
        "domains": body.domains,
        "upstream_host": body.upstream_host,
        "upstream_port": body.upstream_port,
        "timeout_seconds": body.timeout_seconds,
        "path_prefix": body.path_prefix,
        "node_group": body.node_group,
        "tls": body.tls,
    }
    instance = ServiceInstance(
        id=instance_id,
        service_id=body.service_id,
        plan_id=body.plan_id,
        organization_id=body.organization_id,
        space_id=body.space_id,
        status=body.status,
        parameters=parameters,
        created_at=existing.created_at if existing else now,
        updated_at=now,
        last_operation=existing.last_operation if existing else None,
    )
    await _validate_ready_instance(instance)
    stored = await instance_repository.put(instance)
    snapshot = await _rebuild_snapshot(instance_node_group(stored))
    return {
        "status": "stored",
        "instance": instance_summary(stored),
        "snapshot": snapshot_summary(snapshot),
    }


@router.get("/instances")
async def list_instances(
    node_group: str | None = None,
    include_deleted: bool = False,
) -> dict:
    instances = await instance_repository.list(
        node_group=node_group,
        include_deleted=include_deleted,
    )
    return {
        "instances": [instance_summary(instance) for instance in instances],
    }


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: UUID) -> dict:
    instance = await instance_repository.get(instance_id)
    if instance is None:
        raise HTTPException(404, "instance not found")
    return {"instance": instance_summary(instance)}


@router.delete("/instances/{instance_id}", status_code=202)
async def delete_instance(instance_id: UUID) -> dict:
    instance = await instance_repository.delete(instance_id)
    if instance is None:
        raise HTTPException(404, "instance not found")
    snapshot = await _rebuild_snapshot(instance_node_group(instance))
    return {
        "status": "deleted",
        "instance": instance_summary(instance),
        "snapshot": snapshot_summary(snapshot),
    }


async def _validate_ready_instance(instance: ServiceInstance) -> None:
    if instance.status != InstanceStatus.READY:
        return
    try:
        await SnapshotBuilder(StaticServiceInstanceSource([instance])).build(
            instance_node_group(instance)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


async def _rebuild_snapshot(node_group: str) -> Snapshot:
    snapshot = await snapshot_builder.build(node_group)
    snapshot_cache.set(snapshot)
    return snapshot
