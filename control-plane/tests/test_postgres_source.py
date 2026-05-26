import unittest
import uuid
from datetime import UTC, datetime

from fulcrum_shared.models import InstanceStatus, LastOperationState, LastOperationType

from control_plane.instances import _row_to_instance


class PostgresInstanceSourceMappingTest(unittest.TestCase):
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
