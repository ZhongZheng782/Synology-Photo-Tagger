import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("TAGGER_DB_PATH", os.path.join(tempfile.gettempdir(), f"photo-tagger-tests-{os.getpid()}.sqlite3"))
import app as tagger


class ExternalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.client = tagger.app.test_client()
        self.job = "e" * 32
        self.criteria = {"work_type": "travel_stay", "country": "日本", "date_from": "2026-11-12", "date_to": "2026-11-19"}
        with tagger.tag_job_db() as db:
            db.execute("DELETE FROM tag_jobs WHERE id=?", (self.job,))
            db.execute("INSERT INTO tag_jobs(id,owner_key,space,task,criteria_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                       (self.job, "owner", "personal", "travel_stay", json.dumps(self.criteria), "ready", time.time(), time.time()))
        self.body = dict(source="gmail", evidence_type="booking_confirmation", booking_status="booked",
                         hotel_name="Example Hotel", country="Japan", city="Kyoto",
                         check_in="2026-11-12", check_out="2026-11-16", source_reference="message-123",
                         verification_status="verified")
        self.headers = {"Authorization": "Bearer " + "e" * 48}
        for p in (patch.object(tagger, "PHOTO_TAGGER_JOB_API_TOKEN", "e" * 48),
                  patch.object(tagger, "PHOTO_TAGGER_JOB_API_SCOPES", {"travel:analyze", "travel:evidence_write"}),
                  patch.object(tagger, "metadata_api_owner_context", return_value=("owner", "user"))):
            p.start()
            self.addCleanup(p.stop)

    def call(self, method, body=None):
        return self.client.open(f"/api/v1/jobs/{self.job}/external-evidence", method=method,
                                base_url="https://test.example", headers=self.headers, json=body)

    def test_append_replay_cancel_and_isolation(self):
        self.assertEqual(self.call("POST", self.body).status_code, 201)
        self.assertEqual(self.call("POST", self.body).status_code, 200)
        cancelled = {**self.body, "source_reference": "message-124", "evidence_type": "cancellation", "booking_status": "cancelled"}
        self.assertEqual(self.call("POST", cancelled).status_code, 201)
        rows = self.call("GET").get_json()["external_evidence"]
        self.assertEqual([r["booking_status"] for r in rows], ["booked", "cancelled"])
        self.assertTrue(all(r["review_status"] == "needs_review" for r in rows))
        with patch.object(tagger, "metadata_api_owner_context", return_value=("other", "user")):
            self.assertEqual(self.call("GET").status_code, 404)

    def test_scope_and_validation(self):
        for bad in ({"raw_email": "private"}, {"check_in": "2025-11-12", "check_out": "2025-11-16"}, {"booking_status": "cancelled"}, {"country": "Korea"}):
            self.assertEqual(self.call("POST", {**self.body, **bad}).status_code, 400)
        with patch.object(tagger, "PHOTO_TAGGER_JOB_API_SCOPES", {"travel:analyze"}):
            self.assertEqual(self.call("POST", self.body).status_code, 403)
        self.assertEqual(self.call("GET").get_json()["external_evidence"], [])

    def test_report_includes_evidence_without_photo_candidates(self):
        self.assertEqual(self.call("POST", self.body).status_code, 201)
        for fmt in ("json", "markdown"):
            response = self.client.get(f"/api/v1/jobs/{self.job}/report?format={fmt}",
                                       base_url="https://test.example", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Example Hotel", response.get_data(as_text=True))
        detail = self.client.get(f"/api/v1/jobs/{self.job}", base_url="https://test.example", headers=self.headers)
        self.assertEqual(detail.get_json()["external_evidence"][0]["hotel_name"], "Example Hotel")
