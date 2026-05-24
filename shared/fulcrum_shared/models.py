from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class InstanceStatus(str, Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    READY = "ready"
    FAILED = "failed"
    DEPROVISIONING = "deprovisioning"
    DELETED = "deleted"


class LastOperationType(str, Enum):
    PROVISION = "provision"
    DEPROVISION = "deprovision"
    UPDATE = "update"


class LastOperationState(str, Enum):
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LastOperation(BaseModel):
    type: LastOperationType
    state: LastOperationState
    description: str = ""
    updated_at: datetime = Field(default_factory=utc_now)


class ServiceInstance(BaseModel):
    id: uuid.UUID
    service_id: str
    plan_id: str
    organization_id: str
    space_id: str
    parameters: dict[str, Any] = {}
    status: InstanceStatus = InstanceStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_operation: LastOperation | None = None


class TaskType(str, Enum):
    PROVISION = "provision"
    DEPROVISION = "deprovision"
    UPDATE = "update"


class TaskStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProvisioningTask(BaseModel):
    task_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    instance_id: uuid.UUID
    task_type: TaskType
    payload: dict[str, Any] = {}
    attempt: int = 0
    enqueued_at: datetime = Field(default_factory=utc_now)


class TaskResult(BaseModel):
    task_id: uuid.UUID
    instance_id: uuid.UUID
    status: TaskStatus
    error: str | None = None
    completed_at: datetime = Field(default_factory=utc_now)
