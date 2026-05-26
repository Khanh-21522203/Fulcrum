from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from broker.api.catalog import _CATALOG
from broker.app_state import instance_repository
from fulcrum_shared.models import (
    InstanceStatus,
    LastOperation,
    LastOperationState,
    LastOperationType,
    ProvisioningTask,
    ServiceInstance,
    TaskType,
    utc_now,
)

router = APIRouter()


class ProvisionRequest(BaseModel):
    service_id: str
    plan_id: str
    organization_id: str
    space_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class UpdateRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)


@router.put("/service_instances/{instance_id}", status_code=202)
async def provision(
    instance_id: uuid.UUID,
    body: ProvisionRequest,
    response: Response,
) -> dict:
    _validate_catalog_ids(body.service_id, body.plan_id)
    parameters = _validated_parameters(body.parameters)
    existing = await instance_repository.get(instance_id)
    if existing is not None:
        if existing.status == InstanceStatus.DELETED:
            raise HTTPException(410, "instance already deleted")
        if _same_provision_request(existing, body, parameters):
            response.status_code = 200
            return {}
        raise HTTPException(409, "service instance already exists")

    now = utc_now()
    instance = ServiceInstance(
        id=instance_id,
        service_id=body.service_id,
        plan_id=body.plan_id,
        organization_id=body.organization_id,
        space_id=body.space_id,
        parameters=parameters,
        status=InstanceStatus.PROVISIONING,
        created_at=now,
        updated_at=now,
        last_operation=LastOperation(
            type=LastOperationType.PROVISION,
            state=LastOperationState.IN_PROGRESS,
            description="Provisioning task enqueued.",
        ),
    )
    await instance_repository.put_with_task(
        instance,
        _task_for(instance, TaskType.PROVISION),
    )
    return {"operation": LastOperationType.PROVISION.value}


@router.patch("/service_instances/{instance_id}", status_code=202)
async def update(instance_id: uuid.UUID, body: UpdateRequest) -> dict:
    existing = await _get_existing_instance(instance_id)
    if existing.status == InstanceStatus.DELETED:
        raise HTTPException(410, "instance already deleted")

    parameters = _validated_parameters({**existing.parameters, **body.parameters})
    updated = existing.model_copy(
        deep=True,
        update={
            "parameters": parameters,
            "status": InstanceStatus.PROVISIONING,
            "updated_at": utc_now(),
            "last_operation": LastOperation(
                type=LastOperationType.UPDATE,
                state=LastOperationState.IN_PROGRESS,
                description="Update task enqueued.",
            ),
        },
    )
    await instance_repository.put_with_task(updated, _task_for(updated, TaskType.UPDATE))
    return {"operation": LastOperationType.UPDATE.value}


@router.delete("/service_instances/{instance_id}", status_code=202)
async def deprovision(
    instance_id: uuid.UUID,
    service_id: str,
    plan_id: str,
) -> dict:
    existing = await _get_existing_instance(instance_id)
    _validate_requested_instance(existing, service_id, plan_id)
    if existing.status == InstanceStatus.DELETED:
        raise HTTPException(410, "instance already deleted")

    deprovisioning = existing.model_copy(
        deep=True,
        update={
            "status": InstanceStatus.DEPROVISIONING,
            "updated_at": utc_now(),
            "last_operation": LastOperation(
                type=LastOperationType.DEPROVISION,
                state=LastOperationState.IN_PROGRESS,
                description="Deprovisioning task enqueued.",
            ),
        },
    )
    await instance_repository.put_with_task(
        deprovisioning,
        _task_for(deprovisioning, TaskType.DEPROVISION),
    )
    return {"operation": LastOperationType.DEPROVISION.value}


@router.get("/service_instances/{instance_id}/last_operation")
async def last_operation(
    instance_id: uuid.UUID,
    operation: str | None = None,
) -> dict:
    instance = await _get_existing_instance(instance_id)
    if instance.last_operation is None:
        raise HTTPException(404, "last operation not found")
    if operation is not None and operation != instance.last_operation.type.value:
        raise HTTPException(404, "operation not found")
    return {
        "state": instance.last_operation.state.value,
        "description": instance.last_operation.description,
    }


async def _get_existing_instance(instance_id: uuid.UUID) -> ServiceInstance:
    instance = await instance_repository.get(instance_id)
    if instance is None:
        raise HTTPException(404, "instance not found")
    return instance


def _validate_catalog_ids(service_id: str, plan_id: str) -> None:
    service = next(
        (
            catalog_service
            for catalog_service in _CATALOG["services"]
            if service_id in {catalog_service["id"], catalog_service["name"]}
        ),
        None,
    )
    if service is None:
        raise HTTPException(400, "unknown service_id")
    plan = next(
        (
            catalog_plan
            for catalog_plan in service["plans"]
            if plan_id in {catalog_plan["id"], catalog_plan["name"]}
        ),
        None,
    )
    if plan is None:
        raise HTTPException(400, "unknown plan_id")


def _validated_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    domains = parameters.get("domains")
    if not isinstance(domains, list) or not domains:
        raise HTTPException(400, "parameters.domains must be a non-empty list")
    normalized_domains = []
    for domain in domains:
        if not isinstance(domain, str) or not domain.strip():
            raise HTTPException(400, "parameters.domains must contain strings")
        normalized_domains.append(domain.strip().lower())

    upstream_host = parameters.get("upstream_host")
    if not isinstance(upstream_host, str) or not upstream_host.strip():
        raise HTTPException(400, "parameters.upstream_host is required")

    upstream_port = parameters.get("upstream_port")
    if not isinstance(upstream_port, int) or upstream_port <= 0:
        raise HTTPException(400, "parameters.upstream_port must be a positive integer")

    path_prefix = parameters.get("path_prefix", "/")
    if not isinstance(path_prefix, str) or not path_prefix.startswith("/"):
        raise HTTPException(400, "parameters.path_prefix must start with /")

    timeout_seconds = parameters.get("timeout_seconds", 30)
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise HTTPException(400, "parameters.timeout_seconds must be positive")

    tls = parameters.get("tls", False)
    if not isinstance(tls, bool):
        raise HTTPException(400, "parameters.tls must be a boolean")

    node_group = parameters.get("node_group", "default")
    if not isinstance(node_group, str) or not node_group.strip():
        raise HTTPException(400, "parameters.node_group must be a non-empty string")

    return {
        **parameters,
        "domains": normalized_domains,
        "upstream_host": upstream_host.strip(),
        "upstream_port": upstream_port,
        "path_prefix": path_prefix,
        "timeout_seconds": timeout_seconds,
        "tls": tls,
        "node_group": node_group.strip(),
    }


def _same_provision_request(
    instance: ServiceInstance,
    body: ProvisionRequest,
    parameters: dict[str, Any],
) -> bool:
    return (
        instance.service_id == body.service_id
        and instance.plan_id == body.plan_id
        and instance.organization_id == body.organization_id
        and instance.space_id == body.space_id
        and instance.parameters == parameters
    )


def _validate_requested_instance(
    instance: ServiceInstance,
    service_id: str,
    plan_id: str,
) -> None:
    if instance.service_id != service_id or instance.plan_id != plan_id:
        raise HTTPException(409, "service_id or plan_id does not match instance")


def _task_for(instance: ServiceInstance, task_type: TaskType) -> ProvisioningTask:
    return ProvisioningTask(
        instance_id=instance.id,
        task_type=task_type,
        payload={
            "instance": instance.model_dump(mode="json"),
        },
    )
