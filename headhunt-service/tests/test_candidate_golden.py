# tests/test_candidate_golden.py
# Golden regression for the candidate engine (service copy), same fixtures as P0.
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from candidate.engine import assess

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(BASE, "tests", "fixtures")


def test_candidate_golden():
    inputs_dir = os.path.join(FIX, "inputs")
    expected_dir = os.path.join(FIX, "expected")
    os.makedirs(expected_dir, exist_ok=True)
    for fname in sorted(os.listdir(inputs_dir)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(inputs_dir, fname), encoding="utf-8") as f:
            bundle = json.load(f)
        actual = assess(bundle)
        exp_path = os.path.join(expected_dir, fname)
        if not os.path.exists(exp_path):
            with open(exp_path, "w", encoding="utf-8") as f:
                json.dump(actual, f, ensure_ascii=False, indent=1)
        with open(exp_path, encoding="utf-8") as f:
            expected = json.load(f)
        assert actual == expected, f"golden mismatch: {fname}"


if __name__ == "__main__":
    test_candidate_golden()
    print("candidate golden PASS")
