from fulcrum_shared.models import ProvisioningTask


async def handle(task: ProvisioningTask) -> None:
    instance = task.payload.get("instance")
    if not isinstance(instance, dict):
        raise ValueError("task payload missing instance")
