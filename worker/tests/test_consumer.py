import unittest
import uuid

from fulcrum_shared.models import ProvisioningTask, TaskType
from worker.consumer import PostgresOutboxConsumer
from worker.repository import ClaimedTask


class FakeRepository:
    def __init__(self, claimed=None) -> None:
        self.claimed = claimed
        self.completed = []
        self.failed = []

    async def claim_next(self):
        claimed = self.claimed
        self.claimed = None
        return claimed

    async def complete(self, task):
        self.completed.append(task)

    async def fail(self, task, error):
        self.failed.append((task, error))


def task(payload=None, task_type=TaskType.PROVISION):
    return ProvisioningTask(
        task_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        instance_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        task_type=task_type,
        payload=payload
        or {
            "instance": {
                "parameters": {
                    "domains": ["api.example.com"],
                    "upstream_host": "api.internal",
                    "upstream_port": 8080,
                }
            }
        },
    )


class PostgresOutboxConsumerTest(unittest.IsolatedAsyncioTestCase):
    async def test_process_once_completes_valid_task(self):
        claimed_task = task()
        repository = FakeRepository(ClaimedTask(task=claimed_task, status="processing"))
        consumer = PostgresOutboxConsumer(repository, poll_interval_seconds=0)

        processed = await consumer.process_once()

        self.assertTrue(processed)
        self.assertEqual(repository.completed, [claimed_task])
        self.assertEqual(repository.failed, [])

    async def test_process_once_fails_invalid_task(self):
        claimed_task = task(payload={"instance": {"parameters": {}}})
        repository = FakeRepository(ClaimedTask(task=claimed_task, status="processing"))
        consumer = PostgresOutboxConsumer(repository, poll_interval_seconds=0)

        processed = await consumer.process_once()

        self.assertTrue(processed)
        self.assertEqual(repository.completed, [])
        self.assertEqual(repository.failed[0][0], claimed_task)
        self.assertIn("domains", repository.failed[0][1])

    async def test_process_once_returns_false_without_task(self):
        repository = FakeRepository()
        consumer = PostgresOutboxConsumer(repository, poll_interval_seconds=0)

        processed = await consumer.process_once()

        self.assertFalse(processed)


if __name__ == "__main__":
    unittest.main()
