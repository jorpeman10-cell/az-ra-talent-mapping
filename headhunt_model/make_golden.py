# -*- coding: utf-8 -*-
"""Regenerate golden fixtures: python make_golden.py [--update].
Reads fixtures/inputs/*.json (assess bundles), writes/compares fixtures/expected/*.json.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from step7_candidate import assess

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

def run(update: bool):
    inputs_dir = os.path.join(BASE, "inputs")
    expected_dir = os.path.join(BASE, "expected")
    os.makedirs(expected_dir, exist_ok=True)
    failures = []
    for fname in sorted(os.listdir(inputs_dir)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(inputs_dir, fname), encoding="utf-8") as f:
            bundle = json.load(f)
        actual = assess(bundle)
        exp_path = os.path.join(expected_dir, fname)
        if update or not os.path.exists(exp_path):
            with open(exp_path, "w", encoding="utf-8") as f:
                json.dump(actual, f, ensure_ascii=False, indent=1)
            print(f"{fname}: written")
        else:
            with open(exp_path, encoding="utf-8") as f:
                expected = json.load(f)
            if actual != expected:
                failures.append(fname)
                print(f"{fname}: MISMATCH")
            else:
                print(f"{fname}: ok")
    return failures

if __name__ == "__main__":
    fails = run(update="--update" in sys.argv)
    sys.exit(1 if fails else 0)
