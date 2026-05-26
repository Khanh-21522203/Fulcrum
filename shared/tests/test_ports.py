import unittest
import uuid

from fulcrum_shared.models import ProvisioningTask, TaskType
from fulcrum_shared.ports import (
    CertificateRef,
    ClaimedProvisioningTask,
    DnsRecord,
    InstanceStore,
    ProvisioningTaskQueue,
    SnapshotInstanceSource,
)


class FakeInstanceStore:
    async def get(self, instance_id):
        return None

    async def put_with_task(self, instance, task):
        self.instance = instance
        self.task = task


class FakeSnapshotSource:
    async def list_ready(self, node_group):
        return []


class FakeTaskQueue:
    async def claim_next(self):
        return None

    async def complete(self, task):
        self.completed = task

    async def fail(self, task, error):
        self.failed = (task, error)


class PortsTest(unittest.IsolatedAsyncioTestCase):
    async def test_instance_store_port_accepts_existing_shape(self):
        store: InstanceStore = FakeInstanceStore()
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

        result = await store.get(instance_id)

        self.assertIsNone(result)

    async def test_snapshot_source_port_accepts_existing_shape(self):
        source: SnapshotInstanceSource = FakeSnapshotSource()

        instances = await source.list_ready("local")

        self.assertEqual(instances, [])

    async def test_task_queue_port_accepts_existing_shape(self):
        queue: ProvisioningTaskQueue = FakeTaskQueue()
        task = ProvisioningTask(
            instance_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            task_type=TaskType.PROVISION,
        )

        claimed = await queue.claim_next()
        await queue.complete(task)

        self.assertIsNone(claimed)
        self.assertEqual(queue.completed, task)

    def test_shared_value_objects_are_cloud_neutral(self):
        task = ProvisioningTask(
            instance_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            task_type=TaskType.PROVISION,
        )
        claimed = ClaimedProvisioningTask(task=task, status="processing")
        dns_record = DnsRecord(
            zone="example.com",
            name="api",
            record_type="A",
            values=("203.0.113.10",),
        )
        certificate = CertificateRef(
            name="api-example-com",
            certificate_chain_path="/certs/api.crt",
            private_key_path="/certs/api.key",
        )

        self.assertEqual(claimed.task, task)
        self.assertEqual(dns_record.ttl_seconds, 300)
        self.assertEqual(certificate.name, "api-example-com")


if __name__ == "__main__":
    unittest.main()
