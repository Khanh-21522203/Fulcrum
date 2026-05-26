import unittest
import uuid

from fastapi import HTTPException, Response

from broker.api import instances
from fulcrum_shared.models import InstanceStatus, LastOperationState, TaskType


class FakeRepository:
    def __init__(self) -> None:
        self.instances = {}
        self.tasks = []

    async def get(self, instance_id):
        return self.instances.get(instance_id)

    async def put_with_task(self, instance, task):
        self.instances[instance.id] = instance.model_copy(deep=True)
        self.tasks.append(task.model_copy(deep=True))


def provision_request(**overrides):
    body = {
        "service_id": "load-balancer",
        "plan_id": "standard",
        "organization_id": "org-001",
        "space_id": "space-001",
        "parameters": {
            "domains": ["api.example.com"],
            "upstream_host": "api.internal",
            "upstream_port": 8080,
            "tls": True,
            "timeout_seconds": 30,
            "path_prefix": "/",
            "node_group": "local",
        },
    }
    body.update(overrides)
    return instances.ProvisionRequest(**body)


class BrokerInstanceApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.repository = FakeRepository()
        self.original_repository = instances.instance_repository
        instances.instance_repository = self.repository

    def tearDown(self) -> None:
        instances.instance_repository = self.original_repository

    async def test_provision_creates_instance_and_task(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

        response = await instances.provision(
            instance_id,
            provision_request(),
            Response(),
        )

        stored = self.repository.instances[instance_id]
        self.assertEqual(response, {"operation": "provision"})
        self.assertEqual(stored.status, InstanceStatus.PROVISIONING)
        self.assertEqual(stored.last_operation.state, LastOperationState.IN_PROGRESS)
        self.assertEqual(stored.parameters["domains"], ["api.example.com"])
        self.assertEqual(len(self.repository.tasks), 1)
        self.assertEqual(self.repository.tasks[0].task_type, TaskType.PROVISION)

    async def test_provision_is_idempotent_for_same_request(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await instances.provision(instance_id, provision_request(), Response())

        fastapi_response = Response()
        response = await instances.provision(
            instance_id,
            provision_request(),
            fastapi_response,
        )

        self.assertEqual(response, {})
        self.assertEqual(fastapi_response.status_code, 200)
        self.assertEqual(len(self.repository.tasks), 1)

    async def test_provision_conflicts_for_different_request(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await instances.provision(instance_id, provision_request(), Response())

        with self.assertRaises(HTTPException) as raised:
            await instances.provision(
                instance_id,
                provision_request(
                    parameters={
                        "domains": ["other.example.com"],
                        "upstream_host": "api.internal",
                        "upstream_port": 8080,
                    }
                ),
                Response(),
            )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_provision_rejects_invalid_parameters(self):
        with self.assertRaises(HTTPException) as raised:
            await instances.provision(
                uuid.UUID("11111111-1111-1111-1111-111111111111"),
                provision_request(parameters={"domains": []}),
                Response(),
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(self.repository.tasks, [])

    async def test_update_merges_parameters_and_enqueues_task(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await instances.provision(instance_id, provision_request(), Response())

        response = await instances.update(
            instance_id,
            instances.UpdateRequest(parameters={"upstream_port": 9090}),
        )

        stored = self.repository.instances[instance_id]
        self.assertEqual(response, {"operation": "update"})
        self.assertEqual(stored.parameters["upstream_port"], 9090)
        self.assertEqual(stored.parameters["domains"], ["api.example.com"])
        self.assertEqual(self.repository.tasks[-1].task_type, TaskType.UPDATE)

    async def test_deprovision_marks_instance_and_enqueues_task(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await instances.provision(instance_id, provision_request(), Response())

        response = await instances.deprovision(
            instance_id,
            service_id="load-balancer",
            plan_id="standard",
        )

        stored = self.repository.instances[instance_id]
        self.assertEqual(response, {"operation": "deprovision"})
        self.assertEqual(stored.status, InstanceStatus.DEPROVISIONING)
        self.assertEqual(self.repository.tasks[-1].task_type, TaskType.DEPROVISION)

    async def test_deprovision_rejects_mismatched_service_or_plan(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await instances.provision(instance_id, provision_request(), Response())

        with self.assertRaises(HTTPException) as raised:
            await instances.deprovision(
                instance_id,
                service_id="wrong",
                plan_id="standard",
            )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_last_operation_returns_current_state(self):
        instance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        await instances.provision(instance_id, provision_request(), Response())

        response = await instances.last_operation(instance_id, operation="provision")

        self.assertEqual(response["state"], "in_progress")
        self.assertEqual(response["description"], "Provisioning task enqueued.")


if __name__ == "__main__":
    unittest.main()
