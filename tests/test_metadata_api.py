import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("TAGGER_DB_PATH", os.path.join(tempfile.gettempdir(), f"photo-tagger-tests-{os.getpid()}.sqlite3"))
import app as tagger


class MetadataApiTests(unittest.TestCase):
    def setUp(self):
        self.client = tagger.app.test_client()
        self.path = "/api/v1/metadata/photos?date_from=2026-11-12&date_to=2026-11-19"
        self.headers = {"Authorization": "Bearer " + "a" * 48}
        self.env = patch.dict(os.environ, {"PHOTO_TAGGER_API_TOKEN": "a" * 48})
        self.env.start()
        self.addCleanup(self.env.stop)

    def get(self, path=None, headers=None):
        return self.client.get(path or self.path, base_url="https://test.example", headers=headers or {})

    def test_auth_and_validation(self):
        self.assertEqual(self.get().status_code, 401)
        self.assertEqual(self.client.get(self.path, headers=self.headers).status_code, 403)
        self.assertEqual(self.get("/api/v1/metadata/photos", self.headers).status_code, 400)
        with patch.dict(os.environ, {"PHOTO_TAGGER_API_TOKEN": ""}):
            self.assertEqual(self.get(headers=self.headers).status_code, 503)

    @patch.object(tagger, "post_synology")
    @patch.object(tagger, "api_endpoint", return_value=("https://nas.example/api", 2))
    @patch.object(tagger, "metadata_api_session")
    def test_read_only_pagination(self, session, endpoint, post):
        session.return_value = Mock()
        post.return_value = {"data": {"list": [
            {"id": 1, "filename": "a.jpg", "time": "2026-11-12T10:00:00",
             "additional": {"description": "Kyoto", "gps": {"latitude": 35.0},
                            "address": {"city": "Kyoto"}, "person": [{"name": "private"}]}},
            {"id": 2, "time": "2026-11-01T10:00:00"},
        ]}}
        result = self.get(self.path + "&limit=2", self.headers)
        self.assertEqual(result.status_code, 200)
        data = result.get_json()
        self.assertEqual(data["next_offset"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual(len(data["photos"]), 1)
        self.assertEqual(data["photos"][0]["description"], "Kyoto")
        self.assertNotIn("people", data["photos"][0])
        self.assertEqual(post.call_args.args[2]["method"], "list_with_filter")
        self.assertEqual(result.headers["Cache-Control"], "no-store")

    @patch.object(tagger, "metadata_api_session", return_value=None)
    def test_unavailable(self, session):
        self.assertEqual(self.get(headers=self.headers).status_code, 503)
