# tests/test_candidate_store.py
# Storage, token TTL/single-use, status machine. Paths come from tests/conftest.py.
import os, sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from candidate import store
from candidate.store import CANDIDATES_DIR


def test_new_candidate_and_get():
    rec = store.new_candidate("张三", target_line="肿瘤线", notes="内推")
    assert rec["name"] == "张三" and rec["status"] == "CREATED"
    assert len(rec["token"]) >= 24 and rec["cid"].startswith("c")
    got = store.get(rec["cid"])
    assert got["token"] == rec["token"]
    assert os.path.isfile(os.path.join(CANDIDATES_DIR, rec["cid"], "profile.json"))


def test_token_valid_then_used():
    rec = store.new_candidate("李四")
    cid, reason = store.validate_token(rec["token"])
    assert cid == rec["cid"] and reason is None
    store.update(rec["cid"], self_submitted_at="2026-09-06T00:00:00+00:00")
    cid2, reason2 = store.validate_token(rec["token"])
    assert cid2 is None and reason2 == "already_submitted"


def test_token_expiry():
    rec = store.new_candidate("王五")
    future = datetime.now(timezone.utc) + timedelta(hours=49)
    cid, reason = store.validate_token(rec["token"], now=future)
    assert cid is None and reason == "expired"
    cid2, _ = store.validate_token(rec["token"], now=datetime.now(timezone.utc))
    assert cid2 == rec["cid"]


def test_unknown_token():
    cid, reason = store.validate_token("no-such-token")
    assert cid is None and reason == "not_found"


def test_status_machine_and_save_load():
    rec = store.new_candidate("赵六")
    assert store.derive_status(rec) == "CREATED"
    store.update(rec["cid"], self_submitted_at="t1")
    assert store.derive_status(store.get(rec["cid"])) == "SELF_DONE"
    store.save_json(rec["cid"], "hr_assess.json", {"scored": {"x": 1}})
    assert store.load_json(rec["cid"], "hr_assess.json")["scored"] == {"x": 1}
    store.update(rec["cid"], hr_submitted_at="t2", assessed_at="t3")
    assert store.derive_status(store.get(rec["cid"])) == "ASSESSED"
    assert store.load_json(rec["cid"], "nope.json") is None


def test_list_candidates():
    a = store.new_candidate("甲"); store.new_candidate("乙")
    names = [c["name"] for c in store.list_candidates()]
    assert "甲" in names and "乙" in names


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
