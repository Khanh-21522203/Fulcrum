from __future__ import annotations

from fulcrum_shared.ports import CertificateProvider, DnsProvider, SecretStore


def create_dns_provider() -> DnsProvider:
    from fulcrum_provider_local import create_dns_provider as create_local_dns_provider

    return create_local_dns_provider()


def create_certificate_provider() -> CertificateProvider:
    from fulcrum_provider_local import (
        create_certificate_provider as create_local_certificate_provider,
    )

    return create_local_certificate_provider()


def create_secret_store() -> SecretStore:
    from fulcrum_provider_local import create_secret_store as create_local_secret_store

    return create_local_secret_store()
