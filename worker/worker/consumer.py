# Service Bus message processing strategy:
#   - Receive with peek-lock (message not consumed until explicitly completed)
#   - Transient error  → abandon message; Service Bus re-delivers with backoff
#   - Permanent error  → dead-letter the message after MaxDeliveryCount reached
#   - Idempotency      → check ServiceInstance.status before writing to Cosmos DB

from fulcrum_shared.models import TaskType
from worker.handlers import deprovision, provision, update

_HANDLERS = {
    TaskType.PROVISION: provision.handle,
    TaskType.UPDATE: update.handle,
    TaskType.DEPROVISION: deprovision.handle,
}


class ServiceBusConsumer:
    """Consumes ProvisioningTask messages from Azure Service Bus."""

    async def start(self) -> None:
        # TODO: create ServiceBusClient from connection string / managed identity
        # TODO: open a receiver on the provisioning topic subscription
        # TODO: loop: receive message → deserialise ProvisioningTask
        #             → dispatch to _HANDLERS[task.task_type]
        #             → complete on success, abandon on transient error,
        #               dead-letter on permanent error
        raise NotImplementedError
