# -*- coding: utf-8 -*-
"""网关接入补丁: 粘贴进 federation_gateway/mcp_server.py (或 import 后注册)
与网关上 100+ 个 @mcp.tool() 同构; 内部 HTTP 调 headhunt-svc (确定性引擎)
前提: headhunt-svc 与网关同机或内网可达, 地址用环境变量 HEADHUNT_API 覆盖
"""
import os
import json
import urllib.request

HEADHUNT_API = os.environ.get("HEADHUNT_API", "http://127.0.0.1:18801")


def _hh_get(path: str) -> dict:
    with urllib.request.urlopen(f"{HEADHUNT_API}{path}", timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# === 以下装饰器换成网关 mcp_server.py 里的 mcp 实例 ===
# from . import mcp  # 网关 FastMCP 实例

# @mcp.tool()
def headhunt_board() -> dict:
    """顾问用工决策排名看板: 市场阶段、EMPLOY/INCUBATE/PASS 分布、全员排名。
    数据来自谷露回款/签约/面试 + 财务薪酬成本, 每日跑批更新。"""
    return _hh_get("/api/board")


# @mcp.tool()
def headhunt_advisor_decision(name_or_id: str) -> dict:
    """单顾问用工决策与判断依据: 产能画像、双模式 NPV/IRR、决策理由(rationale)。
    name_or_id: 顾问姓名或谷露用户ID。用于回答'XX该不该留/转孵化/淘汰'。"""
    # 姓名->ID 解析由 headhunt-svc 的 MCP 层支持; HTTP 层先按 ID, 姓名走列表匹配
    if name_or_id.isdigit():
        return _hh_get(f"/api/advisor/{name_or_id}")
    board = _hh_get("/api/board")
    hits = [a for a in board["advisors"] if name_or_id in a["name"]]
    if len(hits) != 1:
        return {"error": f"命中{len(hits)}人", "candidates": [h["name"] for h in hits]}
    return _hh_get(f"/api/advisor/{hits[0]['advisor_id']}")


# @mcp.tool()
def headhunt_salary_scan(name_or_id: str, scenario: str = "B") -> dict:
    """调薪幅度测算: EMPLOY 极限月薪、盈亏平衡月薪、NPV 曲线与判断依据(rationale)。
    用于回答'XX能调薪到多少'。scenario: A=公司口径(保守) B=外部行业-0.05(默认) C=乐观。"""
    d = headhunt_advisor_decision(name_or_id)
    if "error" in d:
        return d
    return _hh_get(f"/api/advisor/{d['advisor_id']}/salary_scan?scenario={scenario}")
def _hh_post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{HEADHUNT_API}{path}", method="POST",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# @mcp.tool()
def headhunt_candidate_intake(name: str, target_line: str = "", notes: str = "", created_by: str = "") -> dict:
    """外部顾问候选人建档(面试信息采集): 返回候选人自评问卷链接(self_url, 公网 token-only)
    和 HR 评估链接(hr_url)。用于回答'给候选人XX建档'。name 必填; target_line 目标职能线。"""
    if not name.strip():
        return {"error": "name required"}
    rec = _hh_post("/api/candidate/intake",
                   {"name": name.strip(), "target_line": target_line.strip(),
                    "notes": notes.strip(), "created_by": created_by.strip()})
    base = os.environ.get("HEADHUNT_PUBLIC_BASE", "https://www.hiijob.cn").rstrip("/")
    rec["self_url"] = f"{base}{rec['self_url']}"
    rec["hr_url"] = f"{base}{rec['hr_url']}"
    return rec
