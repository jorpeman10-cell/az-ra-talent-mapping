import base64
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.bridge import create_app
from tests.test_api_bridge import minimal_text_pdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AppendixModesApiTests(unittest.TestCase):
    def _client(self, tmp: str) -> TestClient:
        app = create_app(
            config_dir=PROJECT_ROOT / "config",
            data_dir=Path(tmp),
            public_base_url="http://testserver",
        )
        return TestClient(app)

    def test_upload_defaults_to_structured_only_and_preserves_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            source_pdf = minimal_text_pdf("Alice led an oncology launch from 2022 to 2025.")

            response = client.post(
                "/api/v1/reports/draft-from-files",
                data={"candidate_name": "Alice", "position_title": "KAM"},
                files={"resume_file": ("alice.pdf", source_pdf, "application/pdf")},
            )

            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()["data"]
            self.assertEqual(data["resume_appendix_mode"], "structured_only")
            self.assertRegex(data["resume_source_file_id"], r"^rf_[a-f0-9]{32}$")
            stored = list((Path(tmp) / "source_files").glob("*.pdf"))
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0].read_bytes(), source_pdf)

    def test_upload_accepts_structured_with_source_appendix(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)

            response = client.post(
                "/api/v1/reports/draft-from-files",
                data={
                    "candidate_name": "Alice",
                    "position_title": "KAM",
                    "resume_appendix_mode": "structured_with_source_appendix",
                },
                files={
                    "resume_file": (
                        "alice.txt",
                        b"Name: Alice\n\nWork Experience\n2022-2025 Company A KAM",
                        "text/plain",
                    )
                },
            )

            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()["data"]
            self.assertEqual(data["resume_appendix_mode"], "structured_with_source_appendix")
            self.assertEqual(data["resume_source_file_name"], "alice.txt")
            self.assertEqual(data["resume_source_mime_type"], "text/plain")
            self.assertTrue(data["resume_source_content_hash"])

    def test_json_appendix_mode_rejects_parsed_text_without_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)

            response = client.post(
                "/api/v1/reports/draft",
                json={
                    "brand_id": "tstar",
                    "candidate_name": "Alice",
                    "position_title": "KAM",
                    "resume_text": "Complete resume text but no original file bytes.",
                    "resume_appendix_mode": "structured_with_source_appendix",
                },
            )

            self.assertEqual(response.status_code, 422)
            self.assertIn("source_file_required", response.text)

    def test_json_draft_can_materialize_source_file_from_base64(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            content = b"Name: Alice\nWork Experience\n2022-2025 Company A KAM"

            response = client.post(
                "/api/v1/reports/draft",
                json={
                    "brand_id": "tstar",
                    "candidate_name": "Alice",
                    "position_title": "KAM",
                    "resume_text": content.decode("utf-8"),
                    "resume_appendix_mode": "structured_with_source_appendix",
                    "resume_file_name": "alice.txt",
                    "resume_file_mime_type": "text/plain",
                    "resume_file_base64": base64.b64encode(content).decode("ascii"),
                },
            )

            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()["data"]
            self.assertRegex(data["resume_source_file_id"], r"^rf_[a-f0-9]{32}$")
            self.assertNotIn("resume_file_base64", data)

    def test_rejects_unknown_appendix_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            response = client.post(
                "/api/v1/reports/draft-from-files",
                data={
                    "candidate_name": "Alice",
                    "position_title": "KAM",
                    "resume_appendix_mode": "guess_for_me",
                },
                files={"resume_file": ("alice.txt", b"Alice resume", "text/plain")},
            )
            self.assertEqual(response.status_code, 422)
            self.assertIn("invalid_resume_appendix_mode", response.text)

    def test_update_cannot_enable_source_appendix_without_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            draft = client.post(
                "/api/v1/reports/draft",
                json={
                    "brand_id": "tstar",
                    "candidate_name": "Alice",
                    "position_title": "KAM",
                    "resume_text": "Alice resume text",
                },
            )
            self.assertEqual(draft.status_code, 200, draft.text)

            response = client.post(
                f"/api/v1/reports/{draft.json()['report_id']}/update",
                json={
                    "known_fields": {
                        "resume_appendix_mode": "structured_with_source_appendix"
                    }
                },
            )

            self.assertEqual(response.status_code, 422, response.text)
            self.assertIn("source_file_required", response.text)


if __name__ == "__main__":
    unittest.main()
