from __future__ import annotations

from fulcrum_shared.models import ProvisioningTask
from fulcrum_shared.ports import CertificateProvider, DnsProvider, DnsRecord, SecretStore


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


def _validate_task_payload(task: ProvisioningTask) -> dict:
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
    return parameters


async def _apply_side_effects(
    parameters: dict,
    dns_provider: DnsProvider,
    certificate_provider: CertificateProvider,
    secret_store: SecretStore,
) -> None:
    for domain in parameters["domains"]:
        await dns_provider.upsert(
            DnsRecord(
                zone=_dns_zone_for(domain),
                name=_dns_name_for(domain),
                record_type="CNAME",
                values=(str(parameters["upstream_host"]),),
                ttl_seconds=int(parameters.get("dns_ttl_seconds") or 300),
            )
        )

    if not parameters.get("tls"):
        return

    certificate_chain = parameters.get("certificate_chain")
    private_key = parameters.get("private_key")
    if not certificate_chain or not private_key:
        raise ValueError("tls enabled but certificate_chain or private_key is missing")

    for domain in parameters["domains"]:
        cert_name = _certificate_name_for(domain)
        await certificate_provider.put_certificate(
            cert_name,
            str(certificate_chain).encode(),
            str(private_key).encode(),
        )
        await secret_store.put_secret(
            f"tls/{domain}/private-key",
            str(private_key).encode(),
        )


def _dns_zone_for(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) < 2:
        return domain
    return ".".join(parts[-2:])


def _dns_name_for(domain: str) -> str:
    zone = _dns_zone_for(domain)
    if domain == zone:
        return "@"
    return domain[: -(len(zone) + 1)]


def _certificate_name_for(domain: str) -> str:
    return domain.replace("*", "wildcard")
