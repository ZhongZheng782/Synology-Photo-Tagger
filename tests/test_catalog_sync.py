import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("TAGGER_DB_PATH", os.path.join(tempfile.gettempdir(), f"photo-tagger-tests-{os.getpid()}.sqlite3"))
import app as tagger


class CatalogSyncTests(unittest.TestCase):
    @patch.object(tagger, "post_synology")
    def test_split_rejected_bulk_read(self, post):
        def reply(client, url, params):
            ids = json.loads(params["id"])
            self.assertNotIn("orientation_original", json.loads(params["additional"]))
            if len(ids) > 1:
                raise tagger.SynologyApiError("NAS API 請求失敗", 101)
            return {"data": {"list": [{"id": ids[0]}]}}
        post.side_effect = reply
        result = tagger.catalog_detail_batch(Mock(), "https://nas.example", 2, "test", [1, 2])
        self.assertEqual(set(result), {"1", "2"})
        self.assertEqual(post.call_count, 3)

    @patch.object(tagger, "post_synology")
    def test_auth_error_does_not_split(self, post):
        post.side_effect = tagger.SynologyApiError("expired", 119)
        with self.assertRaises(tagger.SynologyApiError):
            tagger.catalog_detail_batch(Mock(), "https://nas.example", 2, "test", [1, 2])
        self.assertEqual(post.call_count, 1)

class ExternalCatalogTests(unittest.TestCase):
    def setUp(self):
        self.client = tagger.app.test_client()
        self.headers = {"Authorization": "Bearer " + "b" * 48}
        for p in (patch.object(tagger, "PHOTO_TAGGER_JOB_API_TOKEN", "b" * 48),
                  patch.object(tagger, "PHOTO_TAGGER_JOB_API_SCOPES", {"catalog:read", "catalog:sync"}),
                  patch.object(tagger, "metadata_api_owner_context", return_value=("owner", "user"))):
            p.start()
            self.addCleanup(p.stop)

    def call(self, method, suffix, **kwargs):
        return self.client.open("/api/v1/catalog/" + suffix, method=method,
                                base_url="https://test.example", headers=self.headers, **kwargs)

    @patch.object(tagger.photo_catalog, "sync_status", return_value={"status": "running", "run_id": "run"})
    def test_status_and_run_isolation(self, status):
        self.assertEqual(self.call("GET", "status").status_code, 200)
        status.assert_called_with("owner", "personal")
        self.assertEqual(self.call("GET", "sync/run").status_code, 200)
        self.assertEqual(self.call("GET", "sync/other").status_code, 404)
        self.assertEqual(self.call("GET", "status?space=shared").status_code, 400)
        with patch.object(tagger, "PHOTO_TAGGER_JOB_API_SCOPES", {"catalog:sync"}):
            self.assertEqual(self.call("GET", "status").status_code, 403)

    @patch.object(tagger, "queue_photo_catalog_sync")
    @patch.object(tagger, "metadata_api_session_context")
    def test_sync_authorization(self, context, queue):
        context.return_value = ("other", "token", Mock())
        self.assertEqual(self.call("POST", "sync", json={}).status_code, 403)
        self.assertEqual(self.call("POST", "sync", json={"space": "shared"}).status_code, 400)
        context.return_value = ("owner", "token", Mock())
        with patch.object(tagger, "PHOTO_TAGGER_JOB_API_SCOPES", {"catalog:read"}):
            self.assertEqual(self.call("POST", "sync", json={}).status_code, 403)
        queue.assert_not_called()
        queue.return_value = ({"ok": True}, 202)
        self.assertEqual(self.call("POST", "sync", json={}).status_code, 202)
        queue.assert_called_once_with("owner", "personal", "token")
