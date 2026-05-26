import json
import tempfile
import unittest
from pathlib import Path

from fulcrum_provider_local.json_dns_provider import JsonDnsProvider
from fulcrum_shared.ports import DnsRecord


class JsonDnsProviderTest(unittest.TestCase):
    def test_upsert_persists_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "records.json"
            provider = JsonDnsProvider(path)

            provider._upsert_sync(
                DnsRecord(
                    zone="example.com",
                    name="api",
                    record_type="a",
                    values=("203.0.113.10",),
                    ttl_seconds=60,
                )
            )

            data = json.loads(path.read_text())
            self.assertEqual(
                data["example.com|api|A"],
                {
                    "zone": "example.com",
                    "name": "api",
                    "record_type": "A",
                    "values": ["203.0.113.10"],
                    "ttl_seconds": 60,
                },
            )

    def test_delete_removes_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = JsonDnsProvider(Path(tmpdir) / "records.json")
            record = DnsRecord(
                zone="example.com",
                name="api",
                record_type="A",
                values=("203.0.113.10",),
            )

            provider._upsert_sync(record)
            provider._delete_sync(record)

            self.assertEqual(json.loads(provider._path.read_text()), {})

    def test_rejects_invalid_record(self):
        provider = JsonDnsProvider("/tmp/unused")

        with self.assertRaises(ValueError):
            provider._upsert_sync(
                DnsRecord(
                    zone="",
                    name="api",
                    record_type="A",
                    values=("203.0.113.10",),
                )
            )


if __name__ == "__main__":
    unittest.main()
