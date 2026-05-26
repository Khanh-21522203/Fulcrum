from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any

from fulcrum_shared.ports import DnsProvider, DnsRecord

from fulcrum_provider_local.paths import local_state_dir


class JsonDnsProvider(DnsProvider):
    """Local DNS registry provider.

    This persists intended DNS records for local development. It does not run a
    real DNS server; a later CoreDNS adapter can read from the same shape or
    replace this provider behind the same port.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self._path = Path(path) if path is not None else local_state_dir() / "dns" / "records.json"
        self._lock = threading.RLock()

    async def upsert(self, record: DnsRecord) -> None:
        await asyncio.to_thread(self._upsert_sync, record)

    async def delete(self, record: DnsRecord) -> None:
        await asyncio.to_thread(self._delete_sync, record)

    def _upsert_sync(self, record: DnsRecord) -> None:
        _validate_record(record)
        with self._lock:
            data = self._read()
            data[_record_key(record)] = {
                "zone": record.zone,
                "name": record.name,
                "record_type": record.record_type.upper(),
                "values": list(record.values),
                "ttl_seconds": record.ttl_seconds,
            }
            self._write(data)

    def _delete_sync(self, record: DnsRecord) -> None:
        _validate_record(record)
        with self._lock:
            data = self._read()
            data.pop(_record_key(record), None)
            self._write(data)

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _record_key(record: DnsRecord) -> str:
    return f"{record.zone.lower()}|{record.name.lower()}|{record.record_type.upper()}"


def _validate_record(record: DnsRecord) -> None:
    if not record.zone:
        raise ValueError("dns zone is required")
    if not record.name:
        raise ValueError("dns record name is required")
    if not record.record_type:
        raise ValueError("dns record_type is required")
    if not record.values:
        raise ValueError("dns record values are required")
    if record.ttl_seconds <= 0:
        raise ValueError("dns ttl_seconds must be positive")
