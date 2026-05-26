from fulcrum_shared.models import ProvisioningTask


class TaskPublisher:
    """Publishes ProvisioningTask messages through the configured task provider."""

    async def publish(self, task: ProvisioningTask) -> None:
        raise NotImplementedError
