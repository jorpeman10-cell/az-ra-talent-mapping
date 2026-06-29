import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import docx
from fastapi.testclient import TestClient

from api.bridge import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def minimal_text_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    chunks = [b"%PDF-1.4\n"]
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref_offset = sum(len(chunk) for chunk in chunks)
    chunks.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        chunks.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    chunks.append(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return b"".join(chunks)


class ApiBridgeTests(unittest.TestCase):
    def test_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(config_dir=PROJECT_ROOT / "config", data_dir=Path(tmp), public_base_url="http://testserver")
            client = TestClient(app)
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "ok")

    def test_root_page_and_favicon_are_browser_friendly(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(config_dir=PROJECT_ROOT / "config", data_dir=Path(tmp), public_base_url="http://testserver")
            client = TestClient(app)

            root_response = client.get("/")
            self.assertEqual(root_response.status_code, 200)
            self.assertIn("Generic Report Tool", root_response.text)
            self.assertIn('name="candidate_name"', root_response.text)
            self.assertIn('name="position_title"', root_response.text)
            self.assertIn('name="resume_file"', root_response.text)
            self.assertIn('name="jd_file"', root_response.text)
            self.assertIn('type="file"', root_response.text)
            self.assertIn(".pdf", root_response.text)
            self.assertIn("api/v1/reports/draft-from-files", root_response.text)
            self.assertIn("生成报告卡片", root_response.text)

            favicon_response = client.get("/favicon.ico")
            self.assertEqual(favicon_response.status_code, 204)

    def test_draft_from_files_requires_resume_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(config_dir=PROJECT_ROOT / "config", data_dir=Path(tmp), public_base_url="http://testserver")
            client = TestClient(app)

            response = client.post("/api/v1/reports/draft-from-files", data={
                "candidate_name": "Alice",
                "position_title": "Medical Director",
            })

            self.assertEqual(response.status_code, 422)

    def test_draft_from_files_extracts_resume_and_jd(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(config_dir=PROJECT_ROOT / "config", data_dir=Path(tmp), public_base_url="http://testserver")
            client = TestClient(app)
            resume_file = BytesIO()
            resume_doc = docx.Document()
            resume_doc.add_paragraph("Alice led oncology medical affairs projects.")
            resume_doc.save(resume_file)
            resume_file.seek(0)

            response = client.post(
                "/api/v1/reports/draft-from-files",
                data={
                    "candidate_name": "Alice",
                    "position_title": "Medical Director",
                    "current_company": "Current Pharma",
                    "current_title": "Medical Lead",
                },
                files={
                    "resume_file": (
                        "alice.docx",
                        resume_file.getvalue(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                    "jd_file": (
                        "jd.txt",
                        "Client Company: AstraZeneca\nRole: Medical Director".encode("utf-8"),
                        "text/plain",
                    ),
                },
            )

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertTrue(payload["report_id"].startswith("report_"))
            self.assertEqual(payload["source_files"]["resume_file_name"], "alice.docx")
            self.assertEqual(payload["source_files"]["jd_file_name"], "jd.txt")
            self.assertEqual(payload["known_fields"]["client_company"], "AstraZeneca")

    def test_draft_from_files_extracts_pdf_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(config_dir=PROJECT_ROOT / "config", data_dir=Path(tmp), public_base_url="http://testserver")
            client = TestClient(app)
            resume_file = minimal_text_pdf("Alice has oncology launch experience.")

            response = client.post(
                "/api/v1/reports/draft-from-files",
                data={
                    "candidate_name": "Alice",
                    "position_title": "Medical Director",
                },
                files={
                    "resume_file": ("alice.pdf", resume_file, "application/pdf"),
                },
            )

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["source_files"]["resume_file_name"], "alice.pdf")
            self.assertIn("/cards/reports/", payload["card_url"])

    def test_draft_card_and_render_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(config_dir=PROJECT_ROOT / "config", data_dir=Path(tmp), public_base_url="http://testserver")
            client = TestClient(app)
            draft_response = client.post("/api/v1/reports/draft", json={
                "brand_id": "default",
                "candidate_name": "Alice",
                "position_title": "Medical Director",
            })
            self.assertEqual(draft_response.status_code, 200)
            report_id = draft_response.json()["report_id"]

            card_response = client.get(f"/cards/reports/{report_id}")
            self.assertEqual(card_response.status_code, 200)
            self.assertIn("Alice", card_response.text)
            self.assertIn(f'action="../../api/v1/reports/{report_id}/render"', card_response.text)

            comments_response = client.post(f"/api/v1/reports/{report_id}/comments", json={})
            self.assertEqual(comments_response.status_code, 200)

            render_response = client.post(f"/api/v1/reports/{report_id}/render")
            self.assertEqual(render_response.status_code, 200)
            self.assertTrue(render_response.json()["filename"].endswith(".docx"))


if __name__ == "__main__":
    unittest.main()
