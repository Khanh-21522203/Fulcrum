from fulcrum_shared.models import ProvisioningTask


async def handle(task: ProvisioningTask) -> None:
    # Steps:
    # 1. Delete all Azure DNS records associated with the instance
    # 2. Archive / revoke TLS certificate in Key Vault
    # 3. Write ServiceInstance (status=deleted, last_op=succeeded) to Cosmos DB
    raise NotImplementedError
