from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DnsRecord:
    zone: str
    name: str
    record_type: str
    values: tuple[str, ...]
    ttl_seconds: int = 300


class DnsProvider(Protocol):
    async def upsert(self, record: DnsRecord) -> None:
        ...

    async def delete(self, record: DnsRecord) -> None:
        ...
