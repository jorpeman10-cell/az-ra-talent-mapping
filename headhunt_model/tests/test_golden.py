# tests/test_golden.py
# Golden regression: assess() output must match frozen fixtures exactly.
import json, os, sys, io
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from step7_candidate import assess

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")

def _cases():
    inputs_dir = os.path.join(BASE, "inputs")
    for fname in sorted(os.listdir(inputs_dir)):
        if fname.endswith(".json"):
            yield fname

def test_golden():
    for fname in _cases():
        with open(os.path.join(BASE, "inputs", fname), encoding="utf-8") as f:
            bundle = json.load(f)
        with open(os.path.join(BASE, "expected", fname), encoding="utf-8") as f:
            expected = json.load(f)
        actual = assess(bundle)
        assert actual == expected, f"golden mismatch: {fname}"

if __name__ == "__main__":
    test_golden(); print("golden PASS")
