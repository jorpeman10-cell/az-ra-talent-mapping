# -*- coding: utf-8 -*-
"""step6: questionnaire template model, default template, validation, versioning.
Pure functions + JSON-friendly dicts. No LLM, no network, no production data.
"""
import copy

QUESTION_TYPES = {"choice", "number", "multi", "text"}
# dimension ids used by step7 engine — renaming requires syncing step7
DIM_IDS = ("performance", "domain", "speed", "stability", "compliance")

_DEFAULT = {
    "template_id": "consultant_v1",
    "version": 1,
    "dimensions": [
        {
            "id": "performance", "name": "业绩证据", "weight": 0.35,
            "self_questions": [
                {"id": "perf_amount", "type": "number", "label": "近两年平均年回款（万）", "unit": "万"},
                {"id": "perf_max_deal", "type": "number", "label": "最大单笔成单金额（万）", "unit": "万"},
                {"id": "perf_desc", "type": "text", "label": "简述近两年代表性成单（客户/职位/金额）"},
            ],
            "hr_questions": [
                {"id": "perf_verify", "type": "choice", "label": "申报业绩的可验证程度",
                 "options": [
                     {"label": "有流水/邮件/offer截图完整佐证", "score": 5, "redline": False},
                     {"label": "有部分佐证，数字合理", "score": 4, "redline": False},
                     {"label": "口头声明，符合行业常识", "score": 3, "redline": False},
                     {"label": "口头声明，数字偏高存疑", "score": 2, "redline": False},
                     {"label": "明显夸大或自相矛盾", "score": 1, "redline": False},
                 ]},
                {"id": "perf_probe", "type": "choice", "label": "追问细节（客户决策链/费率/周期）后的可信度",
                 "options": [
                     {"label": "细节完整自洽", "score": 5, "redline": False},
                     {"label": "基本自洽，个别含糊", "score": 4, "redline": False},
                     {"label": "多处含糊", "score": 3, "redline": False},
                     {"label": "关键细节答不上", "score": 2, "redline": False},
                     {"label": "回避追问", "score": 1, "redline": False},
                 ]},
            ],
        },
        {
            "id": "domain", "name": "职能深耕", "weight": 0.20,
            "self_questions": [
                {"id": "dom_tags", "type": "multi", "label": "主攻职能线（多选）",
                 "options": [
                     {"label": "医学"}, {"label": "临床运营"}, {"label": "BD"}, {"label": "商业BD"},
                     {"label": "CMC"}, {"label": "注册"}, {"label": "销售"}, {"label": "市场"},
                     {"label": "市场准入"}, {"label": "综合/不限"},
                 ]},
                {"id": "dom_share", "type": "text", "label": "各职能线成单占比（如：医学60% 临床运营40%）"},
            ],
            "hr_questions": [
                {"id": "dom_depth", "type": "choice", "label": "职能领域知识深度提问打分（靶点/管线/客户组织架构）",
                 "options": [
                     {"label": "能讲清管线与组织层级，有独家情报", "score": 5, "redline": False},
                     {"label": "领域知识扎实", "score": 4, "redline": False},
                     {"label": "泛泛了解", "score": 3, "redline": False},
                     {"label": "仅岗位名称层面", "score": 2, "redline": False},
                     {"label": "答非所问", "score": 1, "redline": False},
                 ]},
            ],
        },
        {
            "id": "speed", "name": "三速差", "weight": 0.20,
            "self_questions": [
                {"id": "speed_jc", "type": "choice", "label": "通常从接到 JC 到推荐首位候选人的耗时",
                 "options": [
                     {"label": "24小时内", "score": 5, "redline": False},
                     {"label": "1-2天", "score": 4, "redline": False},
                     {"label": "3-5天", "score": 3, "redline": False},
                     {"label": "1-2周", "score": 2, "redline": False},
                     {"label": "2周以上", "score": 1, "redline": False},
                 ]},
                {"id": "speed_case", "type": "text", "label": "描述最近一次 JC→首推的完整过程"},
            ],
            "hr_questions": [
                {"id": "speed_probe", "type": "choice", "label": "现场给真实 JC，评估其寻访路径（速度/情报/人脉）",
                 "options": [
                     {"label": "路径清晰有情报与人脉支撑", "score": 5, "redline": False},
                     {"label": "路径可行", "score": 4, "redline": False},
                     {"label": "常规路径无亮点", "score": 3, "redline": False},
                     {"label": "路径勉强", "score": 2, "redline": False},
                     {"label": "无有效路径", "score": 1, "redline": False},
                 ]},
            ],
        },
        {
            "id": "stability", "name": "稳定性", "weight": 0.15,
            "self_questions": [
                {"id": "stab_moves", "type": "choice", "label": "近5年换平台次数",
                 "options": [
                     {"label": "0次", "score": 5, "redline": False},
                     {"label": "1次", "score": 4, "redline": False},
                     {"label": "2次", "score": 3, "redline": False},
                     {"label": "3次", "score": 2, "redline": False},
                     {"label": "4次及以上", "score": 1, "redline": False},
                 ]},
                {"id": "stab_reason", "type": "text", "label": "过往换平台原因及当前看机会的原因"},
            ],
            "hr_questions": [
                {"id": "stab_verify", "type": "choice", "label": "离职原因交叉验证可信度",
                 "options": [
                     {"label": "完全自洽，可背调印证", "score": 5, "redline": False},
                     {"label": "基本可信", "score": 4, "redline": False},
                     {"label": "说法笼统", "score": 3, "redline": False},
                     {"label": "有出入", "score": 2, "redline": False},
                     {"label": "明显不实", "score": 1, "redline": False},
                 ]},
            ],
        },
        {
            "id": "compliance", "name": "协作与合规", "weight": 0.10,
            "self_questions": [
                {"id": "comp_share", "type": "choice", "label": "与 RD/其他顾问分单的态度",
                 "options": [
                     {"label": "主动合作让利", "score": 5, "redline": False},
                     {"label": "按规则分单", "score": 4, "redline": False},
                     {"label": "看情况", "score": 3, "redline": False},
                     {"label": "倾向独占", "score": 2, "redline": False},
                     {"label": "曾有争执/投诉", "score": 1, "redline": False},
                 ]},
            ],
            "hr_questions": [
                {"id": "comp_redline", "type": "choice", "label": "合规情景题（飞单/私收简历/挖同事客户）",
                 "options": [
                     {"label": "明确拒绝并知道边界", "score": 5, "redline": False},
                     {"label": "拒绝，边界感一般", "score": 4, "redline": False},
                     {"label": "含糊", "score": 3, "redline": False},
                     {"label": "找借口合理化", "score": 2, "redline": False},
                     {"label": "承认做过类似行为", "score": 1, "redline": True},
                 ]},
            ],
        },
    ],
}


def default_template() -> dict:
    return copy.deepcopy(_DEFAULT)


def validate_template(t: dict) -> list:
    """Return list of error strings; empty list means valid."""
    errors = []
    dims = t.get("dimensions", [])
    ids = [d.get("id") for d in dims]
    if len(ids) != len(set(ids)):
        errors.append("duplicate dimension id")
    for i in ids:
        if i not in DIM_IDS:
            errors.append(f"unknown dimension id: {i}")
    wsum = round(sum(d.get("weight", 0.0) for d in dims), 6)
    if abs(wsum - 1.0) > 1e-6:
        errors.append(f"weights must sum to 1.0, got {wsum}")
    for d in dims:
        for q in d.get("self_questions", []) + d.get("hr_questions", []):
            if q.get("type") not in QUESTION_TYPES:
                errors.append(f"bad question type: {q.get('type')}")
            if "redline" in q:
                errors.append(f"redline only allowed on choice options, not question: {q.get('id')}")
            if q.get("type") == "choice":
                opts = q.get("options", [])
                if not opts:
                    errors.append(f"choice question needs options: {q.get('id')}")
                for o in opts:
                    if not isinstance(o.get("score"), (int, float)):
                        errors.append(f"option missing score: {q.get('id')}")
            else:
                for o in q.get("options") or []:
                    if isinstance(o, dict) and "redline" in o:
                        errors.append(f"redline only allowed on choice options: {q.get('id')}")
                        break
    return errors


def next_version(t: dict) -> dict:
    t2 = copy.deepcopy(t)
    t2["version"] = t.get("version", 1) + 1
    return t2


# ---------- scoring ----------

# verify coefficient map keyed by rounded-down face-eval performance score
VERIFY_COEF = {5: 1.0, 4: 0.9, 3: 0.8, 2: 0.65, 1: 0.5}


def _qmap(t, role):
    """{(dim_id, qid): question} for the given role."""
    out = {}
    for d in t["dimensions"]:
        for q in d.get(f"{role}_questions", []):
            out[(d["id"], q["id"])] = q
    return out


def score_questionnaire(t: dict, responses: dict, role: str) -> dict:
    """Score one questionnaire (role='self'|'hr').

    Rules:
    - dimension score = mean of its choice-question scores (1-5); number/multi/text are captured, not scored
    - dimension with no choice questions (self 'performance') gets neutral 5.0
    - missing choice answer -> that dimension score 0 and missing=True (engine blocks assess)
    - redline=True if any chosen option has redline=True
    """
    assert role in ("self", "hr")
    result = {
        "role": role,
        "template_version": t["version"],
        "dimensions": {}, "claimed_billing_wan": None,
        "domain_tags": [], "redline": False,
    }
    for d in t["dimensions"]:
        scores, answers, missing = [], {}, False
        for q in d.get(f"{role}_questions", []):
            ans = responses.get(q["id"])
            answers[q["id"]] = ans
            if q["type"] == "choice":
                if ans is None:
                    missing = True
                    continue
                opt = next((o for o in q["options"] if o["label"] == ans), None)
                if opt is None:
                    missing = True
                    continue
                scores.append(float(opt["score"]))
                if opt.get("redline"):
                    result["redline"] = True
            elif q["type"] == "number" and isinstance(ans, (int, float)):
                if q["id"] == "perf_amount":
                    result["claimed_billing_wan"] = float(ans)
            elif q["type"] == "multi" and isinstance(ans, list):
                if q["id"] == "dom_tags":
                    result["domain_tags"] = [str(x) for x in ans]
        entry = {"score": round(sum(scores) / len(scores), 2) if scores else 5.0,
                 "answers": answers}
        if missing:
            entry["score"] = 0
            entry["missing"] = True
        result["dimensions"][d["id"]] = entry
    return result


def verify_coefficient(hr_result: dict) -> float:
    """Map HR performance dimension score (1-5) to a verification coefficient."""
    score = hr_result["dimensions"]["performance"]["score"]
    step = min(5, max(1, int(score)))  # floor to nearest whole step
    return VERIFY_COEF[step]
