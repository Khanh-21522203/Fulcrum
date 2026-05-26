from fulcrum_shared.models import ProvisioningTask
from worker.handlers.provision import _validate_task_payload


async def handle(task: ProvisioningTask) -> None:
    _validate_task_payload(task)
