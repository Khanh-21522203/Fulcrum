import unittest

from fastapi import HTTPException

from control_plane.api import ops
from control_plane.app_state import snapshot_cache
from control_plane.snapshot import Snapshot


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
        self.original_builder = ops.snapshot_builder
        ops.snapshot_builder = StubSnapshotBuilder()

    def tearDown(self) -> None:
        snapshot_cache.clear()
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


if __name__ == "__main__":
    unittest.main()
