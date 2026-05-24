from fulcrum_shared.models import ProvisioningTask


async def handle(task: ProvisioningTask) -> None:
    # Steps:
    # 1. Read current ServiceInstance from Cosmos DB
    # 2. Diff DNS records; delete stale ones, upsert new ones
    # 3. Update TLS cert in Key Vault if domains changed
    # 4. Write ServiceInstance (updated params, status=ready) to Cosmos DB
    raise NotImplementedError
