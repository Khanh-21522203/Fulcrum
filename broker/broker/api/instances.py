import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ProvisionRequest(BaseModel):
    service_id: str
    plan_id: str
    organization_id: str
    space_id: str
    parameters: dict[str, Any] = {}


class UpdateRequest(BaseModel):
    parameters: dict[str, Any] = {}


@router.put("/service_instances/{instance_id}", status_code=202)
async def provision(instance_id: uuid.UUID, body: ProvisionRequest) -> dict:
    raise HTTPException(501, "not implemented")


@router.patch("/service_instances/{instance_id}", status_code=202)
async def update(instance_id: uuid.UUID, body: UpdateRequest) -> dict:
    raise HTTPException(501, "not implemented")


@router.delete("/service_instances/{instance_id}", status_code=202)
async def deprovision(
    instance_id: uuid.UUID, service_id: str, plan_id: str
) -> dict:
    raise HTTPException(501, "not implemented")


@router.get("/service_instances/{instance_id}/last_operation")
async def last_operation(
    instance_id: uuid.UUID, operation: str | None = None
) -> dict:
    raise HTTPException(501, "not implemented")
