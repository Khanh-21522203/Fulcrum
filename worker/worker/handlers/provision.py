from fulcrum_shared.models import ProvisioningTask


async def handle(task: ProvisioningTask) -> None:
    _validate_task_payload(task)


def _validate_task_payload(task: ProvisioningTask) -> None:
    instance = task.payload.get("instance")
    if not isinstance(instance, dict):
        raise ValueError("task payload missing instance")
    parameters = instance.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("task payload missing instance parameters")
    if not parameters.get("domains"):
        raise ValueError("task payload missing domains")
    if not parameters.get("upstream_host"):
        raise ValueError("task payload missing upstream_host")
    if int(parameters.get("upstream_port") or 0) <= 0:
        raise ValueError("task payload has invalid upstream_port")
