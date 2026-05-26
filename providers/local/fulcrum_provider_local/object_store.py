from __future__ import annotations

import asyncio
import os
from io import BytesIO

from fulcrum_shared.ports import ObjectStore


class MinioObjectStore(ObjectStore):
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        secure: bool | None = None,
        client=None,
    ) -> None:
        self._endpoint = endpoint or os.environ["FULCRUM_MINIO_ENDPOINT"]
        self._access_key = access_key or os.environ["FULCRUM_MINIO_ACCESS_KEY"]
        self._secret_key = secret_key or os.environ["FULCRUM_MINIO_SECRET_KEY"]
        self._bucket = bucket or os.environ.get(
            "FULCRUM_OBJECT_STORE_BUCKET",
            "fulcrum-artifacts",
        )
        self._secure = (
            secure
            if secure is not None
            else os.environ.get("FULCRUM_MINIO_SECURE", "false").lower()
            in {"1", "true", "yes"}
        )
        self._client = client

    async def get_object(self, key: str) -> bytes | None:
        return await asyncio.to_thread(self._get_object_sync, key)

    async def put_object(
        self,
        key: str,
        value: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        await asyncio.to_thread(self._put_object_sync, key, value, content_type)

    async def delete_object(self, key: str) -> None:
        await asyncio.to_thread(self._delete_object_sync, key)

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    @property
    def bucket(self) -> str:
        return self._bucket

    def _get_object_sync(self, key: str) -> bytes | None:
        response = None
        try:
            response = self._minio().get_object(self._bucket, key)
            return response.read()
        except Exception as exc:
            if getattr(exc, "code", None) == "NoSuchKey":
                return None
            raise
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def _put_object_sync(
        self,
        key: str,
        value: bytes,
        content_type: str | None,
    ) -> None:
        self._ensure_bucket_sync()
        self._minio().put_object(
            self._bucket,
            key,
            BytesIO(value),
            length=len(value),
            content_type=content_type or "application/octet-stream",
        )

    def _delete_object_sync(self, key: str) -> None:
        self._minio().remove_object(self._bucket, key)

    def _ensure_bucket_sync(self) -> None:
        client = self._minio()
        if not client.bucket_exists(self._bucket):
            client.make_bucket(self._bucket)

    def _minio(self):
        if self._client is None:
            from minio import Minio

            self._client = Minio(
                self._endpoint,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )
        return self._client
