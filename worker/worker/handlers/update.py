from fulcrum_shared.models import ProvisioningTask
from fulcrum_shared.ports import CertificateProvider, DnsProvider, SecretStore
from worker.handlers.provision import _apply_side_effects, _validate_task_payload


async def handle(
    task: ProvisioningTask,
    dns_provider: DnsProvider,
    certificate_provider: CertificateProvider,
    secret_store: SecretStore,
) -> None:
    parameters = _validate_task_payload(task)
    await _apply_side_effects(
        parameters,
        dns_provider,
        certificate_provider,
        secret_store,
    )
