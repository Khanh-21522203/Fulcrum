from fulcrum_shared.models import ProvisioningTask


async def handle(task: ProvisioningTask) -> None:
    # Steps:
    # 1. Validate payload (non-empty domains, reachable upstream)
    # 2. Create Azure DNS records for each domain in task.payload["domains"]
    # 3. Request or retrieve TLS certificate from Key Vault
    # 4. Write ServiceInstance (status=ready, last_op=succeeded) to Cosmos DB
    raise NotImplementedError
