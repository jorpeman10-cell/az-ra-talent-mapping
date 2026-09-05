# tests/test_step6_template.py
# Tests for questionnaire template model: structure, validation, versioning.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from step6_questionnaire import default_template, validate_template, next_version

def test_default_template_valid():
    t = default_template()
    assert validate_template(t) == []

def test_weights_must_sum_to_one():
    t = default_template()
    t["dimensions"][0]["weight"] = 0.5  # break the sum
    assert any("weight" in e for e in validate_template(t))

def test_duplicate_dimension_id_rejected():
    t = default_template()
    t["dimensions"][1]["id"] = t["dimensions"][0]["id"]
    assert any("duplicate" in e for e in validate_template(t))

def test_choice_question_needs_options_with_scores():
    t = default_template()
    q = t["dimensions"][0]["self_questions"][0]
    q["type"] = "choice"; q.pop("options", None)
    assert any("options" in e for e in validate_template(t))

def test_redline_flag_only_on_choice():
    t = default_template()
    t["dimensions"][0]["self_questions"][0]["redline"] = True  # not allowed at question level
    assert any("redline" in e for e in validate_template(t))

def test_unknown_dimension_id_rejected():
    t = default_template()
    t["dimensions"][0]["id"] = "bogus"
    assert any("unknown dimension id" in e for e in validate_template(t))

def test_option_level_redline_on_non_choice_rejected():
    t = default_template()
    q = next(q for q in t["dimensions"][1]["self_questions"] if q["type"] == "multi")
    q["options"][0]["redline"] = True
    assert any("redline" in e for e in validate_template(t))

def test_next_version_bumps_and_copies():
    t = default_template()
    t2 = next_version(t)
    assert t2["version"] == t["version"] + 1
    t2["dimensions"][0]["weight"] = 0.9
    assert t["dimensions"][0]["weight"] != 0.9  # deep copy, original untouched

if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"): fn(); print(f"{name} PASS")
