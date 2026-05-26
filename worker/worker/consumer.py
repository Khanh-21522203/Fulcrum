from __future__ import annotations

import asyncio
import logging

from fulcrum_shared.models import TaskType
from worker.handlers import deprovision, provision, update
from worker.repository import PostgresTaskRepository

logger = logging.getLogger(__name__)

_HANDLERS = {
    TaskType.PROVISION: provision.handle,
    TaskType.UPDATE: update.handle,
    TaskType.DEPROVISION: deprovision.handle,
}


class PostgresOutboxConsumer:
    def __init__(
        self,
        repository: PostgresTaskRepository | None = None,
        *,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        self._repository = repository or PostgresTaskRepository()
        self._poll_interval_seconds = poll_interval_seconds

    async def start(self) -> None:
        while True:
            processed = await self.process_once()
            if not processed:
                await asyncio.sleep(self._poll_interval_seconds)

    async def process_once(self) -> bool:
        claimed = await self._repository.claim_next()
        if claimed is None:
            return False

        task = claimed.task
        logger.info("Processing %s task %s", task.task_type.value, task.task_id)
        try:
            await _HANDLERS[task.task_type](task)
        except Exception as exc:
            logger.error("Task %s failed: %s", task.task_id, exc)
            await self._repository.fail(task, str(exc))
            return True

        await self._repository.complete(task)
        logger.info("Task %s completed", task.task_id)
        return True


ServiceBusConsumer = PostgresOutboxConsumer
