# tests/test_candidate_hrconfig.py
# HR config endpoints: grade map + market anchors read/write with validation.
# Env dirs come from tests/conftest.py.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient

TMP = os.environ["HEADHUNT_DATA_DIR"]
CFG = os.environ["HEADHUNT_CONFIG_DIR"]

from api.main import app

client = TestClient(app)


def test_get_returns_empty_defaults_and_grade_list():
    r = client.get("/api/hr-config")
    assert r.status_code == 200
    body = r.json()
    assert body["grade_map"] == {}
    assert body["anchors"] == {}
    assert body["grades"][0] == "ACT" and body["grades"][-1] == "ECON" and len(body["grades"]) == 10


def test_put_grade_map_valid_and_persisted():
    r = client.put("/api/hr-config/grade-map", json={"mapping": {"张三": "C1", "李四": "SC1"}})
    assert r.status_code == 200 and r.json()["saved"] is True
    # second GET reflects it (request-time read, file on disk in CFG)
    body = client.get("/api/hr-config").json()
    assert body["grade_map"] == {"张三": "C1", "李四": "SC1"}
    # _comment key preserved for humans reading the file
    import json
    raw = json.load(open(os.path.join(CFG, "candidate_grade_map.json"), encoding="utf-8"))
    assert "_comment" in raw and raw["mapping"] == {"张三": "C1", "李四": "SC1"}


def test_put_grade_map_invalid_grade_rejected():
    r = client.put("/api/hr-config/grade-map", json={"mapping": {"张三": "C99"}})
    assert r.status_code == 422
    r2 = client.put("/api/hr-config/grade-map", json={"mapping": {" ": "C1"}})
    assert r2.status_code == 422


def test_put_anchors_valid_and_invalid():
    ok = {"C1": {"p25": 14000, "p50": 16000, "p75": 18000}}
    r = client.put("/api/hr-config/anchors", json={"anchors": ok})
    assert r.status_code == 200
    body = client.get("/api/hr-config").json()
    assert body["anchors"]["C1"]["p50"] == 16000
    # unknown grade rejected
    assert client.put("/api/hr-config/anchors",
                      json={"anchors": {"XX": {"p25": 1, "p50": 2, "p75": 3}}}).status_code == 422
    # non-numeric value rejected
    assert client.put("/api/hr-config/anchors",
                      json={"anchors": {"C1": {"p25": "高", "p50": 2, "p75": 3}}}).status_code == 422
    # missing key rejected
    assert client.put("/api/hr-config/anchors",
                      json={"anchors": {"C1": {"p25": 1, "p75": 3}}}).status_code == 422


def test_grades_page_served():
    assert client.get("/grades").status_code == 200


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
