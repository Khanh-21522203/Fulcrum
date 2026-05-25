import unittest
import uuid

from fastapi import HTTPException

from control_plane.api import ops
from control_plane.app_state import instance_repository, snapshot_cache
from control_plane.snapshot import Snapshot, SnapshotBuilder
from fulcrum_shared.models import InstanceStatus, LastOperationType


class StubSnapshotBuilder:
    def __init__(self) -> None:
        self.version = 0

    async def build(self, node_group: str = "default") -> Snapshot:
        self.version += 1
        return Snapshot(
            node_group=node_group,
            version=f"v{self.version}",
        )


class ControlPlaneOpsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        snapshot_cache.clear()
        instance_repository.clear()
        self.original_builder = ops.snapshot_builder
        ops.snapshot_builder = StubSnapshotBuilder()

    def tearDown(self) -> None:
        snapshot_cache.clear()
        instance_repository.clear()
        ops.snapshot_builder = self.original_builder

    async def test_readyz_reports_unready_without_snapshots(self):
        with self.assertRaises(HTTPException) as raised:
            await ops.readyz()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "no snapshots loaded")

    async def test_invalidate_rebuilds_snapshot(self):
        body = await ops.invalidate_snapshots(
            ops.SnapshotInvalidateRequest(node_group="region-eastus")
        )

        self.assertEqual(body["status"], "rebuilt")
        self.assertEqual(body["snapshot"]["node_group"], "region-eastus")
        self.assertEqual(body["snapshot"]["version"], "v1")

    async def test_lists_current_snapshots(self):
        await ops.invalidate_snapshots(
            ops.SnapshotInvalidateRequest(node_group="region-eastus")
        )

        response = await ops.list_snapshots()

        self.assertEqual(len(response["snapshots"]), 1)
        self.assertEqual(
            response["snapshots"][0]["resources"]["listeners"],
            0,
        )

    async def test_diff_shows_previous_and_current_versions(self):
        await ops.invalidate_snapshots(
            ops.SnapshotInvalidateRequest(node_group="region-eastus")
        )
        await ops.invalidate_snapshots(
            ops.SnapshotInvalidateRequest(node_group="region-eastus")
        )

        response = await ops.snapshot_diff("region-eastus")

        self.assertEqual(response["previous"]["version"], "v1")
        self.assertEqual(response["current"]["version"], "v2")

    async def test_readyz_reports_ready_after_snapshot_exists(self):
        await ops.invalidate_snapshots(
            ops.SnapshotInvalidateRequest(node_group="region-eastus")
        )

        response = await ops.readyz()

        self.assertEqual(response, {"status": "ready", "snapshots": 1})


class ControlPlaneInstanceOpsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        snapshot_cache.clear()
        instance_repository.clear()
        self.original_builder = ops.snapshot_builder
        ops.snapshot_builder = SnapshotBuilder(instance_repository)

    def tearDown(self) -> None:
        snapshot_cache.clear()
        instance_repository.clear()
        ops.snapshot_builder = self.original_builder

    async def test_upsert_stores_instance_and_rebuilds_snapshot(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

        response = await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=instance_id,
                node_group="region-eastus",
                domains=["api.example.com"],
                upstream_host="api.internal",
                upstream_port=8080,
            )
        )

        self.assertEqual(response["status"], "stored")
        self.assertEqual(response["instance"]["id"], str(instance_id))
        self.assertEqual(
            response["instance"]["parameters"]["node_group"],
            "region-eastus",
        )
        self.assertEqual(response["snapshot"]["node_group"], "region-eastus")
        self.assertEqual(response["snapshot"]["resources"]["clusters"], 1)
        self.assertIsNotNone(snapshot_cache.get("region-eastus"))

    async def test_lists_and_reads_instances(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=instance_id,
                node_group="region-eastus",
                domains=["api.example.com"],
                upstream_host="api.internal",
                upstream_port=8080,
            )
        )

        listed = await ops.list_instances(node_group="region-eastus")
        fetched = await ops.get_instance(instance_id)

        self.assertEqual(
            [item["id"] for item in listed["instances"]],
            [str(instance_id)],
        )
        self.assertEqual(
            fetched["instance"]["parameters"]["upstream_host"],
            "api.internal",
        )

    async def test_patch_updates_instance_and_rebuilds_snapshot(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=instance_id,
                node_group="region-eastus",
                domains=["api.example.com"],
                upstream_host="api.internal",
                upstream_port=8080,
            )
        )

        response = await ops.patch_instance(
            instance_id,
            ops.InstancePatchRequest(
                domains=["api2.example.com"],
                upstream_port=9090,
            ),
        )

        self.assertEqual(response["status"], "updated")
        self.assertEqual(
            response["instance"]["parameters"]["domains"],
            ["api2.example.com"],
        )
        self.assertEqual(response["instance"]["parameters"]["upstream_port"], 9090)
        self.assertEqual(
            response["instance"]["last_operation"]["type"],
            LastOperationType.UPDATE.value,
        )
        self.assertEqual(response["snapshot"]["resources"]["clusters"], 1)

    async def test_patch_rebuilds_old_and_new_node_groups_when_instance_moves(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=instance_id,
                node_group="region-eastus",
                domains=["api.example.com"],
                upstream_host="api.internal",
                upstream_port=8080,
            )
        )

        await ops.patch_instance(
            instance_id,
            ops.InstancePatchRequest(node_group="region-westus"),
        )

        self.assertEqual(
            snapshot_cache.get("region-eastus").resource_counts()["clusters"],
            0,
        )
        self.assertEqual(
            snapshot_cache.get("region-westus").resource_counts()["clusters"],
            1,
        )

    async def test_delete_marks_instance_deleted_and_rebuilds_empty_snapshot(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=instance_id,
                node_group="region-eastus",
                domains=["api.example.com"],
                upstream_host="api.internal",
                upstream_port=8080,
            )
        )

        response = await ops.delete_instance(instance_id)

        self.assertEqual(response["status"], "deleted")
        self.assertEqual(response["instance"]["status"], InstanceStatus.DELETED.value)
        self.assertEqual(
            response["instance"]["last_operation"]["type"],
            LastOperationType.DEPROVISION.value,
        )
        self.assertEqual(response["snapshot"]["resources"]["clusters"], 0)
        fetched = await ops.get_instance(instance_id)
        self.assertEqual(fetched["instance"]["status"], InstanceStatus.DELETED.value)
        listed = await ops.list_instances(node_group="region-eastus")
        self.assertEqual(listed["instances"], [])
        listed_deleted = await ops.list_instances(
            node_group="region-eastus",
            include_deleted=True,
        )
        self.assertEqual(
            [item["id"] for item in listed_deleted["instances"]],
            [str(instance_id)],
        )

    async def test_rejects_invalid_ready_instance_before_storing(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

        with self.assertRaises(HTTPException) as raised:
            await ops.upsert_instance(
                ops.InstanceUpsertRequest(
                    id=instance_id,
                    node_group="region-eastus",
                    domains=["api.example.com"],
                    upstream_host="api.internal",
                    upstream_port=8080,
                    path_prefix="not-a-prefix",
                )
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIsNone(await instance_repository.get(instance_id))

    async def test_rejects_duplicate_domain_in_node_group(self):
        await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                node_group="region-eastus",
                domains=["api.example.com"],
                upstream_host="api.internal",
                upstream_port=8080,
            )
        )

        with self.assertRaises(HTTPException) as raised:
            await ops.upsert_instance(
                ops.InstanceUpsertRequest(
                    id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                    node_group="region-eastus",
                    domains=["api.example.com"],
                    upstream_host="api2.internal",
                    upstream_port=8080,
                )
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("Domain api.example.com", raised.exception.detail)

    async def test_allows_same_domain_in_different_node_group(self):
        await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                node_group="region-eastus",
                domains=["api.example.com"],
                upstream_host="api.internal",
                upstream_port=8080,
            )
        )

        response = await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                node_group="region-westus",
                domains=["api.example.com"],
                upstream_host="api2.internal",
                upstream_port=8080,
            )
        )

        self.assertEqual(response["status"], "stored")

    async def test_rejects_route_overlap_for_overlapping_domains(self):
        await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                node_group="region-eastus",
                domains=["*"],
                upstream_host="api.internal",
                upstream_port=8080,
                path_prefix="/api",
            )
        )

        with self.assertRaises(HTTPException) as raised:
            await ops.upsert_instance(
                ops.InstanceUpsertRequest(
                    id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                    node_group="region-eastus",
                    domains=["api.example.com"],
                    upstream_host="api2.internal",
                    upstream_port=8080,
                    path_prefix="/api/v1",
                )
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("Route prefix", raised.exception.detail)

    async def test_allows_non_overlapping_route_prefix_for_overlapping_domains(self):
        await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                node_group="region-eastus",
                domains=["*"],
                upstream_host="api.internal",
                upstream_port=8080,
                path_prefix="/api",
            )
        )

        response = await ops.upsert_instance(
            ops.InstanceUpsertRequest(
                id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                node_group="region-eastus",
                domains=["api.example.com"],
                upstream_host="api2.internal",
                upstream_port=8080,
                path_prefix="/admin",
            )
        )

        self.assertEqual(response["status"], "stored")


if __name__ == "__main__":
    unittest.main()
