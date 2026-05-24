from fulcrum_shared.models import ProvisioningTask


class TaskPublisher:
    """Serialises and publishes ProvisioningTask messages to Azure Service Bus."""

    async def publish(self, task: ProvisioningTask) -> None:
        raise NotImplementedError
