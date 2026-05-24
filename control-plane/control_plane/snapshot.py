from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Snapshot:
    node_group: str
    version: str
    listeners: list[dict[str, Any]] = field(default_factory=list)
    routes: list[dict[str, Any]] = field(default_factory=list)
    clusters: list[dict[str, Any]] = field(default_factory=list)
    endpoints: list[dict[str, Any]] = field(default_factory=list)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class SnapshotCache:
    """In-memory versioned snapshot store, keyed by node_group."""

    def __init__(self) -> None:
        self._store: dict[str, Snapshot] = {}

    def get(self, node_group: str) -> Snapshot | None:
        return self._store.get(node_group)

    def set(self, snapshot: Snapshot) -> None:
        self._store[snapshot.node_group] = snapshot

    def all(self) -> dict[str, Snapshot]:
        return dict(self._store)


class SnapshotBuilder:
    """Reads active ServiceInstances + Jinja2 templates; renders Envoy resources."""

    async def build(self, node_group: str) -> Snapshot:
        # TODO: fetch active ServiceInstances from Cosmos DB
        # TODO: fetch Jinja2 templates from Blob Storage
        # TODO: render Listener / RouteConfiguration / Cluster / Endpoint resources
        raise NotImplementedError
