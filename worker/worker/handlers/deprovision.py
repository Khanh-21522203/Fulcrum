from __future__ import annotations

from fulcrum_shared.models import ProvisioningTask
from fulcrum_shared.ports import CertificateProvider, DnsProvider, DnsRecord, SecretStore
from worker.handlers.provision import _dns_name_for, _dns_zone_for


async def handle(
    task: ProvisioningTask,
    dns_provider: DnsProvider,
    _certificate_provider: CertificateProvider,
    secret_store: SecretStore,
) -> None:
    instance = task.payload.get("instance")
    if not isinstance(instance, dict):
        raise ValueError("task payload missing instance")
    parameters = instance.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("task payload missing instance parameters")

    for domain in parameters.get("domains") or ():
        await dns_provider.delete(
            DnsRecord(
                zone=_dns_zone_for(domain),
                name=_dns_name_for(domain),
                record_type="CNAME",
                values=(str(parameters.get("upstream_host") or ""),),
            )
        )
        if parameters.get("tls"):
            await secret_store.delete_secret(f"tls/{domain}/private-key")
            # Local certificate provider has no delete port; deprovision removes
            # secret material and leaves certificate files as historical artifacts.
