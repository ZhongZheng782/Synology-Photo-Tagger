import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("TAGGER_DB_PATH", os.path.join(tempfile.gettempdir(), f"photo-tagger-tests-{os.getpid()}.sqlite3"))
import app as tagger


class HotelTagApiTests(unittest.TestCase):
    def setUp(self):
        self.client = tagger.app.test_client()
        self.env = patch.dict(os.environ, {"PHOTO_TAGGER_HOTEL_TAG_API_TOKEN": "h" * 48,
                                          "PHOTO_TAGGER_HOTEL_TAG_WRITE_ENABLED": "true",
                                          "PHOTO_TAGGER_API_TOKEN": "m" * 48})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.body = dict(confirmed=True, hotel_name="Hotel Daiheigen",
                         check_in="2018-06-21", check_out="2018-06-22",
                         latitude=42.931119, longitude=143.302963,
                         photo_ids=[13560, 13554, 9, 10, 11, 12])
        self.headers = {"Authorization": "Bearer " + "h" * 48}

    def post(self, action, body=None, headers=None):
        return self.client.post("/api/v1/hotel-tags/" + action, json=body or self.body,
                                base_url="https://test.example", headers=headers or self.headers)

    def test_disabled_and_token_isolation(self):
        with patch.dict(os.environ, {"PHOTO_TAGGER_HOTEL_TAG_WRITE_ENABLED": "false"}):
            self.assertEqual(self.post("preview").status_code, 403)
        self.assertEqual(self.post("preview", headers={"Authorization": "Bearer " + "m" * 48}).status_code, 401)
        with patch.object(tagger, "PHOTO_TAGGER_JOB_API_TOKEN", "h" * 48):
            self.assertEqual(self.post("preview").status_code, 503)
        self.assertEqual(self.client.post("/api/v1/hotel-tags/preview", json=self.body,
                                          headers=self.headers).status_code, 403)

    @patch.object(tagger, "metadata_api_owner_context", return_value=("owner", "user"))
    @patch.object(tagger, "metadata_api_session_context", return_value=("owner", "session", Mock()))
    @patch.object(tagger, "api_endpoint", return_value=("https://nas.example/api", 2))
    @patch.object(tagger, "post_synology")
    @patch.object(tagger, "call_job_write_route")
    def test_preview_apply_and_retry(self, write, post, endpoint, context, owner):
        points = {13560: (42.9313888889, 143.3029777778),
                  13554: (42.9314194444, 143.3029638889),
                  9: (42.93323, 143.302534), 10: (None, None),
                  11: (42.931119, 143.302963), 12: (42.931119, 143.302963)}
        def get_item(client, url, payload):
            self.assertEqual(payload["method"], "get")
            import json
            i = json.loads(payload["id"])[0]
            lat, lon = points[i]
            return {"data": {"list": [{"id": i, "filename": str(i)+".jpg",
                "time": "2018-06-23T10:00:00" if i == 11 else "2018-06-22T10:00:00",
                "additional": {"gps": {"latitude": lat, "longitude": lon},
                               "tag": [{"name": "Hotel: Other"}] if i == 12 else [{"name": "existing"}]}}]}}
        post.side_effect = get_item
        write.return_value = {"ok": True, "tags_verified": True, "tags_added": ["Hotel: Hotel Daiheigen"]}
        preview = self.post("preview").get_json()
        self.assertTrue(preview["ok"])
        self.assertEqual({r["photo_id"] for r in preview["rows"] if r["eligible"]}, {13560, 13554})
        write.assert_not_called()
        self.assertEqual(self.post("apply").status_code, 409)
        body = dict(self.body, expires=preview["expires"], preview_token=preview["preview_token"])
        self.assertEqual(self.post("apply", dict(body, hotel_name="Other")).status_code, 409)
        original_point = points[13560]
        points[13560] = (42.94, 143.30)
        self.assertEqual(self.post("apply", body).status_code, 409)
        write.assert_not_called()
        points[13560] = original_point
        self.assertEqual(self.post("apply", body).status_code, 200)
        self.assertEqual(write.call_count, 2)
        self.assertEqual({c.args[2] for c in write.call_args_list}, {13560, 13554})
        write.return_value = {"ok": True, "tags_verified": True, "tags_added": []}
        result = self.post("apply", body).get_json()
        self.assertEqual(sum(r["status"] == "already_present" for r in result["results"]), 2)


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
