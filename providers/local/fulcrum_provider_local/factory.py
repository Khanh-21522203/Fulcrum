from __future__ import annotations

from fulcrum_shared.ports import (
    CertificateProvider,
    DnsProvider,
    ObjectStore,
    SecretStore,
    SnapshotInstanceSource,
)

from fulcrum_provider_local.file_certificate_provider import FileCertificateProvider
from fulcrum_provider_local.file_secret_store import FileSecretStore
from fulcrum_provider_local.json_dns_provider import JsonDnsProvider
from fulcrum_provider_local.object_store import MinioObjectStore
from fulcrum_provider_local.postgres_snapshot_source import (
    PostgresSnapshotInstanceSource,
)


def create_snapshot_source() -> SnapshotInstanceSource:
    return PostgresSnapshotInstanceSource()


def create_object_store() -> ObjectStore:
    return MinioObjectStore()


def create_dns_provider() -> DnsProvider:
    return JsonDnsProvider()


def create_certificate_provider() -> CertificateProvider:
    return FileCertificateProvider()


def create_secret_store() -> SecretStore:
    return FileSecretStore()
