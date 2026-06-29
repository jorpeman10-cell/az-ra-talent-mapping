import tempfile
import unittest
from pathlib import Path

from core.config_loader import ConfigValidator, get_loader


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigAndServiceTests(unittest.TestCase):
    def test_default_brand_loads_and_validates(self):
        loader = get_loader(PROJECT_ROOT / "config")
        brand = loader.load_brand("default")
        self.assertEqual(brand["brand_id"], "default")
        self.assertTrue(brand["fields"]["required"])
        validator = ConfigValidator(loader)
        self.assertTrue(validator.validate_brand("default"), validator.errors)

    def test_hiijob_agent_fallback_generates_deterministic_comments(self):
        from core.hiijob_agent import HiijobAgentClient

        client = HiijobAgentClient(base_url="", agent_id="", token="")
        result = client.generate_comments({
            "candidate_name": "Alice",
            "position_title": "Medical Director",
            "resume_text": "Alice has oncology and medical affairs experience.",
        })

        comments = result["comments"]
        self.assertIn("recommendation_rationale", comments)
        self.assertIn("Medical Director", comments["role_fit"])
        self.assertTrue(result["missing_information"])

    def test_report_service_creates_draft_and_card_url(self):
        from core.report_service import ReportService

        with tempfile.TemporaryDirectory() as tmp:
            service = ReportService(
                config_dir=PROJECT_ROOT / "config",
                data_dir=Path(tmp),
                public_base_url="http://testserver",
            )
            draft = service.create_draft({
                "brand_id": "default",
                "candidate_name": "Alice",
                "position_title": "Medical Director",
                "resume_text": "Oncology medical affairs leader.",
            })

            self.assertEqual(draft["status"], "draft")
            self.assertTrue(draft["report_id"].startswith("report_"))
            self.assertIn("/cards/reports/", draft["card_url"])

    def test_report_service_default_public_url_uses_b9_port(self):
        from core.report_service import ReportService

        with tempfile.TemporaryDirectory() as tmp:
            service = ReportService(config_dir=PROJECT_ROOT / "config", data_dir=Path(tmp))
            draft = service.create_draft({
                "brand_id": "default",
                "candidate_name": "Alice",
                "position_title": "Medical Director",
            })

            self.assertTrue(draft["card_url"].startswith("http://localhost:8810/"))

    def test_report_service_renders_docx(self):
        from core.report_service import ReportService

        with tempfile.TemporaryDirectory() as tmp:
            service = ReportService(
                config_dir=PROJECT_ROOT / "config",
                data_dir=Path(tmp),
                public_base_url="http://testserver",
            )
            draft = service.create_draft({
                "brand_id": "default",
                "candidate_name": "Alice",
                "position_title": "Medical Director",
            })
            service.generate_comments(draft["report_id"])
            rendered = service.render_report(draft["report_id"])

            self.assertEqual(rendered["status"], "confirmed")
            self.assertTrue((Path(tmp) / "outputs" / rendered["filename"]).exists())

    def test_report_service_renders_review_card_html(self):
        from core.report_service import ReportService

        with tempfile.TemporaryDirectory() as tmp:
            service = ReportService(
                config_dir=PROJECT_ROOT / "config",
                data_dir=Path(tmp),
                public_base_url="http://testserver",
            )
            draft = service.create_draft({
                "brand_id": "default",
                "candidate_name": "Alice",
                "position_title": "Medical Director",
            })
            html = service.render_card_html(draft["report_id"])

            self.assertIn("Alice", html)
            self.assertIn("Medical Director", html)
            self.assertIn("Generate DOCX", html)


if __name__ == "__main__":
    unittest.main()
