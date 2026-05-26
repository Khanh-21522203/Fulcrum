from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CertificateRef:
    name: str
    certificate_chain_path: str
    private_key_path: str


class CertificateProvider(Protocol):
    async def get_certificate(self, name: str) -> CertificateRef:
        ...

    async def put_certificate(
        self,
        name: str,
        certificate_chain: bytes,
        private_key: bytes,
    ) -> CertificateRef:
        ...
