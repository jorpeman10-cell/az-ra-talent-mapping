import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DeployNginxTests(unittest.TestCase):
    def test_generic_report_nginx_route_accepts_large_uploads(self):
        source = (PROJECT_ROOT / "deploy_generic_report_tool.py").read_text(encoding="utf-8")

        route_start = source.index("location ^~ /generic-report-tool/")
        route_end = source.index("proxy_pass http://127.0.0.1:8810/", route_start)
        route_source = source[route_start:route_end]

        self.assertIn("client_max_body_size 100m;", route_source)


if __name__ == "__main__":
    unittest.main()
