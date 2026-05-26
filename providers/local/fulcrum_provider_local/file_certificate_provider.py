from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import quote

from fulcrum_shared.ports import CertificateProvider, CertificateRef

from fulcrum_provider_local.paths import local_state_dir


class FileCertificateProvider(CertificateProvider):
    def __init__(self, base_dir: str | os.PathLike[str] | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else local_state_dir() / "certificates"

    async def get_certificate(self, name: str) -> CertificateRef:
        return await asyncio.to_thread(self._get_certificate_sync, name)

    async def put_certificate(
        self,
        name: str,
        certificate_chain: bytes,
        private_key: bytes,
    ) -> CertificateRef:
        return await asyncio.to_thread(
            self._put_certificate_sync,
            name,
            certificate_chain,
            private_key,
        )

    def _get_certificate_sync(self, name: str) -> CertificateRef:
        ref = self._ref_for(name)
        if not Path(ref.certificate_chain_path).exists() or not Path(ref.private_key_path).exists():
            raise FileNotFoundError(f"certificate {name!r} not found")
        return ref

    def _put_certificate_sync(
        self,
        name: str,
        certificate_chain: bytes,
        private_key: bytes,
    ) -> CertificateRef:
        ref = self._ref_for(name)
        chain_path = Path(ref.certificate_chain_path)
        key_path = Path(ref.private_key_path)
        chain_path.parent.mkdir(parents=True, exist_ok=True)
        chain_path.write_bytes(certificate_chain)
        key_path.write_bytes(private_key)
        chain_path.chmod(0o644)
        key_path.chmod(0o600)
        return ref

    def _ref_for(self, name: str) -> CertificateRef:
        if not name:
            raise ValueError("certificate name is required")
        safe_name = quote(name, safe="")
        cert_dir = self._base_dir / safe_name
        return CertificateRef(
            name=name,
            certificate_chain_path=str(cert_dir / "chain.pem"),
            private_key_path=str(cert_dir / "private-key.pem"),
        )
