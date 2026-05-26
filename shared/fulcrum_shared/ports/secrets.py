from __future__ import annotations

from typing import Protocol


class SecretStore(Protocol):
    async def get_secret(self, name: str) -> bytes | None:
        ...

    async def put_secret(self, name: str, value: bytes) -> None:
        ...

    async def delete_secret(self, name: str) -> None:
        ...
