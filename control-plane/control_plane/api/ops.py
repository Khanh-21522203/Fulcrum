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
from fulcrum_shared.models import (
    InstanceStatus,
    LastOperation,
    LastOperationState,
    LastOperationType,
    ServiceInstance,
    utc_now,
)

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


class InstancePatchRequest(BaseModel):
    service_id: str | None = None
    plan_id: str | None = None
    organization_id: str | None = None
    space_id: str | None = None
    status: InstanceStatus | None = None
    node_group: str | None = None
    domains: list[str] | None = Field(default=None, min_length=1)
    upstream_host: str | None = None
    upstream_port: int | None = Field(default=None, gt=0)
    timeout_seconds: int | None = Field(default=None, gt=0)
    path_prefix: str | None = None
    tls: bool | None = None
    parameters: dict[str, Any] | None = None


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
    old_node_group = instance_node_group(existing) if existing else None
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
        last_operation=LastOperation(
            type=LastOperationType.UPDATE if existing else LastOperationType.PROVISION,
            state=LastOperationState.SUCCEEDED,
            description="Instance stored in memory control-plane state.",
        ),
    )
    await _validate_snapshot_publish(instance)
    stored = await instance_repository.put(instance)
    snapshots = await _rebuild_affected_snapshots(
        old_node_group,
        instance_node_group(stored),
    )
    return {
        "status": "stored",
        "instance": instance_summary(stored),
        "snapshot": snapshot_summary(snapshots[-1]),
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


@router.patch("/instances/{instance_id}")
async def patch_instance(instance_id: UUID, body: InstancePatchRequest) -> dict:
    existing = await instance_repository.get(instance_id)
    if existing is None:
        raise HTTPException(404, "instance not found")

    old_node_group = instance_node_group(existing)
    parameters = dict(existing.parameters)
    if body.parameters is not None:
        parameters.update(body.parameters)
    parameter_updates = {
        "domains": body.domains,
        "upstream_host": body.upstream_host,
        "upstream_port": body.upstream_port,
        "timeout_seconds": body.timeout_seconds,
        "path_prefix": body.path_prefix,
        "node_group": body.node_group,
        "tls": body.tls,
    }
    for key, value in parameter_updates.items():
        if value is not None:
            parameters[key] = value

    updated = existing.model_copy(
        deep=True,
        update={
            "service_id": body.service_id or existing.service_id,
            "plan_id": body.plan_id or existing.plan_id,
            "organization_id": body.organization_id or existing.organization_id,
            "space_id": body.space_id or existing.space_id,
            "status": body.status or existing.status,
            "parameters": parameters,
            "updated_at": utc_now(),
            "last_operation": LastOperation(
                type=LastOperationType.UPDATE,
                state=LastOperationState.SUCCEEDED,
                description="Instance updated in memory control-plane state.",
            ),
        },
    )
    await _validate_snapshot_publish(updated)
    stored = await instance_repository.put(updated)
    snapshots = await _rebuild_affected_snapshots(
        old_node_group,
        instance_node_group(stored),
    )
    return {
        "status": "updated",
        "instance": instance_summary(stored),
        "snapshot": snapshot_summary(snapshots[-1]),
    }


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


async def _validate_snapshot_publish(candidate: ServiceInstance) -> None:
    if candidate.status != InstanceStatus.READY:
        return
    node_group = instance_node_group(candidate)
    ready_instances = [
        instance
        for instance in await instance_repository.list(node_group=node_group)
        if instance.status == InstanceStatus.READY and instance.id != candidate.id
    ]
    ready_instances.append(candidate)
    _validate_cross_instance_config(ready_instances)
    try:
        await SnapshotBuilder(StaticServiceInstanceSource(ready_instances)).build(node_group)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _validate_cross_instance_config(instances: list[ServiceInstance]) -> None:
    for instance in instances:
        domains = _instance_domains(instance)
        if not domains:
            raise HTTPException(400, f"Instance {instance.id} has no domains")
        if len(set(domains)) != len(domains):
            raise HTTPException(400, f"Instance {instance.id} has duplicate domains")

    for index, left in enumerate(instances):
        for right in instances[index + 1 :]:
            left_domains = set(_instance_domains(left))
            right_domains = set(_instance_domains(right))
            duplicate_domains = left_domains & right_domains
            if duplicate_domains:
                domain = sorted(duplicate_domains)[0]
                raise HTTPException(
                    409,
                    f"Domain {domain} is already used in node group "
                    f"{instance_node_group(left)}",
                )
            if _domains_overlap(left_domains, right_domains) and _prefixes_overlap(
                _route_prefix(left),
                _route_prefix(right),
            ):
                raise HTTPException(
                    409,
                    f"Route prefix {_route_prefix(left)} overlaps "
                    f"{_route_prefix(right)} for overlapping domains",
                )


def _instance_domains(instance: ServiceInstance) -> tuple[str, ...]:
    return tuple(
        str(domain).strip().lower()
        for domain in instance.parameters.get("domains") or ()
        if str(domain).strip()
    )


def _route_prefix(instance: ServiceInstance) -> str:
    return _normalize_prefix(str(instance.parameters.get("path_prefix") or "/"))


def _domains_overlap(left: set[str], right: set[str]) -> bool:
    return "*" in left or "*" in right or bool(left & right)


def _prefixes_overlap(left: str, right: str) -> bool:
    if left == right or left == "/" or right == "/":
        return True
    return _is_prefix_boundary(left, right) or _is_prefix_boundary(right, left)


def _is_prefix_boundary(prefix: str, path: str) -> bool:
    return path.startswith(f"{prefix.rstrip('/')}/")


def _normalize_prefix(prefix: str) -> str:
    if prefix == "/":
        return prefix
    return prefix.rstrip("/")


async def _rebuild_snapshot(node_group: str) -> Snapshot:
    snapshot = await snapshot_builder.build(node_group)
    snapshot_cache.set(snapshot)
    return snapshot


async def _rebuild_affected_snapshots(
    old_node_group: str | None,
    new_node_group: str,
) -> list[Snapshot]:
    node_groups = [
        node_group
        for node_group in (old_node_group, new_node_group)
        if node_group
    ]
    ordered_unique_node_groups = list(dict.fromkeys(node_groups))
    return [await _rebuild_snapshot(node_group) for node_group in ordered_unique_node_groups]
