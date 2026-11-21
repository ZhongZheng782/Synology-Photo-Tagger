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
