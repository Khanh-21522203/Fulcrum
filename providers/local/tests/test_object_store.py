import unittest

from fulcrum_provider_local.object_store import MinioObjectStore


class FakeS3Error(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FakeResponse:
    def __init__(self, value: bytes) -> None:
        self._value = value
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self._value

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class FakeMinio:
    def __init__(self) -> None:
        self.buckets = set()
        self.objects = {}
        self.last_content_type = None

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket):
        self.buckets.add(bucket)

    def put_object(self, bucket, key, stream, *, length, content_type):
        self.objects[(bucket, key)] = stream.read(length)
        self.last_content_type = content_type

    def get_object(self, bucket, key):
        try:
            return FakeResponse(self.objects[(bucket, key)])
        except KeyError as exc:
            raise FakeS3Error("NoSuchKey") from exc

    def remove_object(self, bucket, key):
        self.objects.pop((bucket, key), None)


class MinioObjectStoreTest(unittest.TestCase):
    def test_put_creates_bucket_and_writes_object(self):
        client = FakeMinio()
        store = MinioObjectStore(
            endpoint="minio:9000",
            access_key="fulcrum",
            secret_key="secret",
            bucket="fulcrum-artifacts",
            client=client,
        )

        store._put_object_sync(
            "templates/envoy.yaml",
            b"template",
            "text/yaml",
        )

        self.assertIn("fulcrum-artifacts", client.buckets)
        self.assertEqual(
            client.objects[("fulcrum-artifacts", "templates/envoy.yaml")],
            b"template",
        )
        self.assertEqual(client.last_content_type, "text/yaml")

    def test_get_returns_object_bytes(self):
        client = FakeMinio()
        client.buckets.add("fulcrum-artifacts")
        client.objects[("fulcrum-artifacts", "templates/envoy.yaml")] = b"template"
        store = MinioObjectStore(
            endpoint="minio:9000",
            access_key="fulcrum",
            secret_key="secret",
            bucket="fulcrum-artifacts",
            client=client,
        )

        value = store._get_object_sync("templates/envoy.yaml")

        self.assertEqual(value, b"template")

    def test_get_returns_none_for_missing_key(self):
        store = MinioObjectStore(
            endpoint="minio:9000",
            access_key="fulcrum",
            secret_key="secret",
            bucket="fulcrum-artifacts",
            client=FakeMinio(),
        )

        value = store._get_object_sync("missing")

        self.assertIsNone(value)

    def test_delete_removes_object(self):
        client = FakeMinio()
        client.objects[("fulcrum-artifacts", "templates/envoy.yaml")] = b"template"
        store = MinioObjectStore(
            endpoint="minio:9000",
            access_key="fulcrum",
            secret_key="secret",
            bucket="fulcrum-artifacts",
            client=client,
        )

        store._delete_object_sync("templates/envoy.yaml")

        self.assertEqual(client.objects, {})


if __name__ == "__main__":
    unittest.main()
