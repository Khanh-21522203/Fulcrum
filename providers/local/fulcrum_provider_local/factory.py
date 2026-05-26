from __future__ import annotations

from fulcrum_shared.ports import ObjectStore, SnapshotInstanceSource

from fulcrum_provider_local.object_store import MinioObjectStore
from fulcrum_provider_local.postgres_snapshot_source import (
    PostgresSnapshotInstanceSource,
)


def create_snapshot_source() -> SnapshotInstanceSource:
    return PostgresSnapshotInstanceSource()


def create_object_store() -> ObjectStore:
    return MinioObjectStore()
