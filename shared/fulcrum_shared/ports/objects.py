from __future__ import annotations

from typing import Protocol


class ObjectStore(Protocol):
    async def get_object(self, key: str) -> bytes | None:
        ...

    async def put_object(self, key: str, value: bytes, *, content_type: str | None = None) -> None:
        ...

    async def delete_object(self, key: str) -> None:
        ...
