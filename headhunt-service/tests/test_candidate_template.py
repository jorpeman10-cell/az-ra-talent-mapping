# tests/test_candidate_template.py
# Template GET/PUT with validation, forced version bump, history archive.
# Env dirs come from tests/conftest.py.
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from api.main import app
from candidate.questionnaire import validate_template

# conftest.py sets HEADHUNT_DATA_DIR before api.main imports; pytest does not
# inject conftest globals into test modules, so re-read it here.
TMP = os.environ["HEADHUNT_DATA_DIR"]

client = TestClient(app)


def test_get_seeds_default():
    t = client.get("/api/template").json()
    assert t["template_id"] == "consultant_v1" and t["version"] == 2  # v2: CV questions
    assert len(t["dimensions"]) == 5


def test_put_invalid_rejected():
    t = client.get("/api/template").json()
    t["dimensions"][0]["weight"] = 0.9     # breaks the 1.0 sum
    r = client.put("/api/template", json=t)
    assert r.status_code == 422
    assert any("weight" in e for e in r.json()["detail"])


def test_question_label_length_is_limited_to_300_characters():
    t = client.get("/api/template").json()
    question = t["dimensions"][0]["self_questions"][0]

    question["label"] = "题" * 300
    assert not any("question label" in error for error in validate_template(t))

    question["label"] = "题" * 301
    errors = validate_template(t)
    assert any("question label exceeds 300 characters" in error for error in errors)
    response = client.put("/api/template", json=t)
    assert response.status_code == 422


def test_put_valid_bumps_version_and_archives():
    t = client.get("/api/template").json()
    t["dimensions"][0]["name"] = "业绩证据（修订）"
    r = client.put("/api/template", json=t)
    assert r.status_code == 200 and r.json()["version"] == 3
    t2 = client.get("/api/template").json()
    assert t2["version"] == 3 and t2["dimensions"][0]["name"] == "业绩证据（修订）"
    hist = os.path.join(TMP, "templates", "v2.json")
    assert os.path.isfile(hist)
    assert json.load(open(hist, encoding="utf-8"))["version"] == 2


def test_editor_page_served():
    response = client.get("/template")
    assert response.status_code == 200
    assert 'maxlength="300"' in response.text


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
