import tempfile
import unittest
from pathlib import Path

from fulcrum_provider_local.file_certificate_provider import FileCertificateProvider


class FileCertificateProviderTest(unittest.TestCase):
    def test_put_and_get_certificate_ref(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileCertificateProvider(tmpdir)

            ref = provider._put_certificate_sync(
                "api.example.com",
                b"certificate-chain",
                b"private-key",
            )
            fetched = provider._get_certificate_sync("api.example.com")

            self.assertEqual(fetched, ref)
            self.assertEqual(Path(ref.certificate_chain_path).read_bytes(), b"certificate-chain")
            self.assertEqual(Path(ref.private_key_path).read_bytes(), b"private-key")

    def test_get_missing_certificate_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileCertificateProvider(tmpdir)

            with self.assertRaises(FileNotFoundError):
                provider._get_certificate_sync("missing")

    def test_rejects_empty_certificate_name(self):
        provider = FileCertificateProvider("/tmp/unused")

        with self.assertRaises(ValueError):
            provider._put_certificate_sync("", b"chain", b"key")


if __name__ == "__main__":
    unittest.main()
