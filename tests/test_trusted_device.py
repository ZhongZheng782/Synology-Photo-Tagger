import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet

os.environ.setdefault(
    "TAGGER_DB_PATH",
    str(Path(tempfile.gettempdir()) / f"photo-tagger-tests-{os.getpid()}.sqlite3"),
)

import app as photo_tagger


class TrustedDeviceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.key_path = Path(self.directory.name) / "schedule-key"
        self.credential_path = Path(self.directory.name) / "credentials.enc"
        self.key_path.write_bytes(Fernet.generate_key())
        self.key_path.chmod(0o600)
        self.key_patch = patch.object(photo_tagger, "NAS_SCHEDULE_KEY_FILE", str(self.key_path))
        self.credential_patch = patch.object(
            photo_tagger, "NAS_SCHEDULE_CREDENTIALS_PATH", str(self.credential_path)
        )
        self.key_patch.start()
        self.credential_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.addCleanup(self.credential_patch.stop)

    def test_credentials_are_encrypted_and_private(self):
        credentials = {
            "base_url": "https://nas.example:5001",
            "username": "photo-user",
            "password": "private-nas-password",
            "device_id": "trusted-device-id",
        }

        self.assertTrue(photo_tagger.save_schedule_credentials(credentials))
        encrypted = self.credential_path.read_bytes()
        self.assertNotIn(b"private-nas-password", encrypted)
        self.assertEqual(self.credential_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(photo_tagger.encrypted_schedule_credentials(), credentials)

    def test_missing_key_disables_credential_storage(self):
        self.key_path.unlink()

        self.assertIsNone(photo_tagger.schedule_credential_cipher())
        self.assertFalse(photo_tagger.save_schedule_credentials({"password": "secret"}))
        self.assertFalse(self.credential_path.exists())

    @patch.object(photo_tagger, "post_synology")
    @patch.object(photo_tagger, "discover_catalog")
    def test_initial_login_registers_trusted_device(self, discover, post):
        client = Mock()
        discover.return_value = (
            client,
            "/webapi",
            {"SYNO.API.Auth": {"path": "entry.cgi", "maxVersion": 7}},
        )
        post.return_value = {"success": True, "data": {"sid": "session-id", "did": "device-id"}}

        result = photo_tagger.login_to_synology(
            "https://nas.example:5001", "photo-user", "password", "123456", register_device=True
        )

        self.assertEqual(result[3:], ("session-id", "device-id"))
        auth_url, params = post.call_args.args
        self.assertEqual(auth_url, "https://nas.example:5001/webapi/entry.cgi")
        self.assertEqual(params["version"], 6)
        self.assertEqual(params["enable_device_token"], "yes")
        self.assertEqual(params["device_name"], "Synology-Photo-Tagger")
        self.assertEqual(params["otp_code"], "123456")

    @patch.object(photo_tagger, "post_synology")
    @patch.object(photo_tagger, "discover_catalog")
    def test_device_login_uses_device_id_without_otp(self, discover, post):
        client = Mock()
        discover.return_value = (
            client,
            "/webapi",
            {"SYNO.API.Auth": {"path": "auth.cgi", "maxVersion": 7}},
        )
        post.return_value = {"success": True, "data": {"sid": "session-id"}}

        photo_tagger.login_to_synology(
            "https://nas.example:5001", "photo-user", "password", device_id="device-id"
        )

        params = post.call_args.args[1]
        self.assertEqual(params["version"], 6)
        self.assertEqual(params["device_name"], "Synology-Photo-Tagger")
        self.assertEqual(params["device_id"], "device-id")
        self.assertNotIn("otp_code", params)

    def test_schedule_uses_taipei_wall_clock(self):
        after = datetime(2026, 11, 5, 1, 59, tzinfo=photo_tagger.TAIPEI_TZ)
        run_at = datetime.fromtimestamp(
            photo_tagger.next_daily_schedule_epoch("02:00", after), photo_tagger.TAIPEI_TZ
        )

        self.assertEqual(run_at, datetime(2026, 11, 5, 2, 0, tzinfo=photo_tagger.TAIPEI_TZ))


if __name__ == "__main__":
    unittest.main()
