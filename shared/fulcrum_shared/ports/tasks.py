from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fulcrum_shared.models import ProvisioningTask


@dataclass(frozen=True)
class ClaimedProvisioningTask:
    task: ProvisioningTask
    status: str


class ProvisioningTaskQueue(Protocol):
    """Cloud-neutral worker queue port.

    The local MVP implements this with a Postgres outbox. Cloud providers can
    implement the same contract with Service Bus, SQS, Pub/Sub, or another
    durable queue without changing worker orchestration.
    """

    async def claim_next(self) -> ClaimedProvisioningTask | None:
        ...

    async def complete(self, task: ProvisioningTask) -> None:
        ...

    async def fail(self, task: ProvisioningTask, error: str) -> None:
        ...
