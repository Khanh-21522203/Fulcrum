import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from fulcrum_provider_local import create_object_store, create_snapshot_source
from fulcrum_provider_local.object_store import MinioObjectStore
from fulcrum_provider_local.postgres_snapshot_source import (
    PostgresSnapshotInstanceSource,
    _row_to_instance,
)
from fulcrum_shared.models import InstanceStatus, LastOperationState, LastOperationType


class LocalProviderFactoryTest(unittest.TestCase):
    def test_creates_snapshot_source(self):
        source = create_snapshot_source()

        self.assertIsInstance(source, PostgresSnapshotInstanceSource)

    def test_creates_object_store_from_environment(self):
        with patch.dict(
            "os.environ",
            {
                "FULCRUM_MINIO_ENDPOINT": "minio:9000",
                "FULCRUM_MINIO_ACCESS_KEY": "fulcrum",
                "FULCRUM_MINIO_SECRET_KEY": "secret",
                "FULCRUM_OBJECT_STORE_BUCKET": "fulcrum-artifacts",
            },
        ):
            store = create_object_store()

        self.assertIsInstance(store, MinioObjectStore)
        self.assertEqual(store.bucket, "fulcrum-artifacts")


class PostgresSnapshotSourceMappingTest(unittest.TestCase):
    def test_maps_row_to_service_instance(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        now = datetime.now(UTC)

        instance = _row_to_instance(
            {
                "id": instance_id,
                "service_id": "load-balancer",
                "plan_id": "standard",
                "organization_id": "org-001",
                "space_id": "space-001",
                "parameters": {
                    "domains": ["api.example.com"],
                    "upstream_host": "api.internal",
                    "upstream_port": 8080,
                },
                "status": "ready",
                "last_operation_type": "provision",
                "last_operation_state": "succeeded",
                "last_operation_description": "Instance ready.",
                "last_operation_updated_at": now,
                "created_at": now,
                "updated_at": now,
            }
        )

        self.assertEqual(instance.id, instance_id)
        self.assertEqual(instance.status, InstanceStatus.READY)
        self.assertEqual(instance.last_operation.type, LastOperationType.PROVISION)
        self.assertEqual(instance.last_operation.state, LastOperationState.SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
