from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import quote

from fulcrum_shared.ports import SecretStore

from fulcrum_provider_local.paths import local_state_dir


class FileSecretStore(SecretStore):
    def __init__(self, base_dir: str | os.PathLike[str] | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else local_state_dir() / "secrets"

    async def get_secret(self, name: str) -> bytes | None:
        return await asyncio.to_thread(self._get_secret_sync, name)

    async def put_secret(self, name: str, value: bytes) -> None:
        await asyncio.to_thread(self._put_secret_sync, name, value)

    async def delete_secret(self, name: str) -> None:
        await asyncio.to_thread(self._delete_secret_sync, name)

    def _get_secret_sync(self, name: str) -> bytes | None:
        path = self._path_for(name)
        if not path.exists():
            return None
        return path.read_bytes()

    def _put_secret_sync(self, name: str, value: bytes) -> None:
        path = self._path_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        path.chmod(0o600)

    def _delete_secret_sync(self, name: str) -> None:
        self._path_for(name).unlink(missing_ok=True)

    def _path_for(self, name: str) -> Path:
        if not name:
            raise ValueError("secret name is required")
        return self._base_dir / quote(name, safe="")
