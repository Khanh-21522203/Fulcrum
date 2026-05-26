import unittest
import uuid

from fulcrum_shared.models import ProvisioningTask, TaskType
from worker.consumer import PostgresOutboxConsumer
from worker.repository import ClaimedTask


class FakeDnsProvider:
    def __init__(self) -> None:
        self.upserted = []
        self.deleted = []

    async def upsert(self, record):
        self.upserted.append(record)

    async def delete(self, record):
        self.deleted.append(record)


class FakeCertificateProvider:
    def __init__(self) -> None:
        self.certificates = []

    async def get_certificate(self, name):
        raise FileNotFoundError(name)

    async def put_certificate(self, name, certificate_chain, private_key):
        self.certificates.append((name, certificate_chain, private_key))
        return None


class FakeSecretStore:
    def __init__(self) -> None:
        self.secrets = []
        self.deleted = []

    async def get_secret(self, name):
        return None

    async def put_secret(self, name, value):
        self.secrets.append((name, value))

    async def delete_secret(self, name):
        self.deleted.append(name)


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
        dns_provider = FakeDnsProvider()
        certificate_provider = FakeCertificateProvider()
        secret_store = FakeSecretStore()
        consumer = PostgresOutboxConsumer(
            repository,
            dns_provider,
            certificate_provider,
            secret_store,
            poll_interval_seconds=0,
        )

        processed = await consumer.process_once()

        self.assertTrue(processed)
        self.assertEqual(repository.completed, [claimed_task])
        self.assertEqual(repository.failed, [])
        self.assertEqual(len(dns_provider.upserted), 1)
        self.assertEqual(dns_provider.upserted[0].zone, "example.com")
        self.assertEqual(dns_provider.upserted[0].name, "api")
        self.assertEqual(dns_provider.upserted[0].values, ("api.internal",))

    async def test_process_once_writes_tls_artifacts(self):
        claimed_task = task(
            payload={
                "instance": {
                    "parameters": {
                        "domains": ["api.example.com"],
                        "upstream_host": "api.internal",
                        "upstream_port": 8080,
                        "tls": True,
                        "certificate_chain": "chain",
                        "private_key": "key",
                    }
                }
            }
        )
        repository = FakeRepository(ClaimedTask(task=claimed_task, status="processing"))
        dns_provider = FakeDnsProvider()
        certificate_provider = FakeCertificateProvider()
        secret_store = FakeSecretStore()
        consumer = PostgresOutboxConsumer(
            repository,
            dns_provider,
            certificate_provider,
            secret_store,
            poll_interval_seconds=0,
        )

        processed = await consumer.process_once()

        self.assertTrue(processed)
        self.assertEqual(repository.completed, [claimed_task])
        self.assertEqual(
            certificate_provider.certificates,
            [("api.example.com", b"chain", b"key")],
        )
        self.assertEqual(
            secret_store.secrets,
            [("tls/api.example.com/private-key", b"key")],
        )

    async def test_process_once_deletes_local_side_effects_on_deprovision(self):
        claimed_task = task(task_type=TaskType.DEPROVISION)
        repository = FakeRepository(ClaimedTask(task=claimed_task, status="processing"))
        dns_provider = FakeDnsProvider()
        consumer = PostgresOutboxConsumer(
            repository,
            dns_provider,
            FakeCertificateProvider(),
            FakeSecretStore(),
            poll_interval_seconds=0,
        )

        processed = await consumer.process_once()

        self.assertTrue(processed)
        self.assertEqual(repository.completed, [claimed_task])
        self.assertEqual(len(dns_provider.deleted), 1)

    async def test_process_once_fails_invalid_task(self):
        claimed_task = task(payload={"instance": {"parameters": {}}})
        repository = FakeRepository(ClaimedTask(task=claimed_task, status="processing"))
        consumer = PostgresOutboxConsumer(
            repository,
            FakeDnsProvider(),
            FakeCertificateProvider(),
            FakeSecretStore(),
            poll_interval_seconds=0,
        )

        processed = await consumer.process_once()

        self.assertTrue(processed)
        self.assertEqual(repository.completed, [])
        self.assertEqual(repository.failed[0][0], claimed_task)
        self.assertIn("domains", repository.failed[0][1])

    async def test_process_once_returns_false_without_task(self):
        repository = FakeRepository()
        consumer = PostgresOutboxConsumer(
            repository,
            FakeDnsProvider(),
            FakeCertificateProvider(),
            FakeSecretStore(),
            poll_interval_seconds=0,
        )

        processed = await consumer.process_once()

        self.assertFalse(processed)


if __name__ == "__main__":
    unittest.main()
