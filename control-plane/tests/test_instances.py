import unittest
import uuid

from fulcrum_shared.models import InstanceStatus, ServiceInstance

from control_plane.instances import InMemoryInstanceRepository


def instance(
    *,
    instance_id: uuid.UUID,
    node_group: str = "region-eastus",
    status: InstanceStatus = InstanceStatus.READY,
) -> ServiceInstance:
    return ServiceInstance(
        id=instance_id,
        service_id="load-balancer",
        plan_id="standard",
        organization_id="org-001",
        space_id="space-001",
        status=status,
        parameters={
            "domains": ["api.example.com"],
            "upstream_host": "api.internal",
            "upstream_port": 8080,
            "node_group": node_group,
        },
    )


class InMemoryInstanceRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_lists_ready_instances_by_node_group(self):
        repository = InMemoryInstanceRepository()
        east = instance(
            instance_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            node_group="region-eastus",
        )
        west = instance(
            instance_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            node_group="region-westus",
        )
        pending = instance(
            instance_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            node_group="region-eastus",
            status=InstanceStatus.PENDING,
        )

        await repository.put(west)
        await repository.put(pending)
        await repository.put(east)

        ready = await repository.list_ready("region-eastus")

        self.assertEqual([item.id for item in ready], [east.id])

    async def test_returns_copies_so_callers_cannot_mutate_store(self):
        repository = InMemoryInstanceRepository()
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await repository.put(instance(instance_id=instance_id))

        fetched = await repository.get(instance_id)
        fetched.parameters["upstream_host"] = "changed.internal"

        stored = await repository.get(instance_id)
        self.assertEqual(stored.parameters["upstream_host"], "api.internal")

    async def test_delete_removes_instance(self):
        repository = InMemoryInstanceRepository()
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await repository.put(instance(instance_id=instance_id))

        deleted = await repository.delete(instance_id)

        self.assertEqual(deleted.id, instance_id)
        self.assertIsNone(await repository.get(instance_id))


if __name__ == "__main__":
    unittest.main()
