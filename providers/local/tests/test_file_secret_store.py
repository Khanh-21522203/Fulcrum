import tempfile
import unittest
from pathlib import Path

from fulcrum_provider_local.file_secret_store import FileSecretStore


class FileSecretStoreTest(unittest.TestCase):
    def test_put_get_and_delete_secret(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileSecretStore(tmpdir)

            store._put_secret_sync("tls/api.example.com", b"secret-value")
            value = store._get_secret_sync("tls/api.example.com")
            store._delete_secret_sync("tls/api.example.com")

            self.assertEqual(value, b"secret-value")
            self.assertIsNone(store._get_secret_sync("tls/api.example.com"))

    def test_secret_name_is_encoded_as_single_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileSecretStore(tmpdir)

            store._put_secret_sync("../bad/name", b"value")

            files = list(Path(tmpdir).iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_bytes(), b"value")

    def test_rejects_empty_secret_name(self):
        store = FileSecretStore("/tmp/unused")

        with self.assertRaises(ValueError):
            store._put_secret_sync("", b"value")


if __name__ == "__main__":
    unittest.main()
