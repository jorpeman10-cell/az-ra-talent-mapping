# -*- coding: utf-8 -*-
"""MCP 服务: 把决策引擎包成 3 个工具给 Agent 调用 (确定性计算, 无 LLM 参与)
独立运行: python -m mcp_ext.server  (默认 127.0.0.1:18802, streamable-http)
网关接入: 见 gateway_patch/headhunt_tools.py (同语义的 @mcp.tool 版本)
"""
import os
import json
import glob

from mcp.server.fastmcp import FastMCP

from pipeline.run import run_pipeline, load_config
from api.main import _salary_scan_compute, _advisor, _board
from api.rationale import build_rationale, build_scan_rationale

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "output")

mcp = FastMCP("headhunt-decision", host="0.0.0.0", port=18802,
              streamable_http_path="/mcp")


def _find_advisor(name_or_id: str) -> dict:
    """支持 ID 或姓名(模糊)查找"""
    p = os.path.join(OUT, "advisors", f"{name_or_id}.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    hits = []
    for f in glob.glob(os.path.join(OUT, "advisors", "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if name_or_id in d.get("advisor_name", ""):
            hits.append(d)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"找不到顾问: {name_or_id}")
    raise ValueError(f"命中多个顾问: {[h['advisor_name'] for h in hits]}, 请用 ID")


@mcp.tool()
def headhunt_board() -> dict:
    """顾问用工决策排名看板: 市场阶段、EMPLOY/INCUBATE/PASS 决策分布、全员排名分。
    数据来自谷露回款/签约/面试 + 财务真实薪酬成本, 每日跑批更新。"""
    return _board()


@mcp.tool()
def headhunt_advisor_decision(name_or_id: str) -> dict:
    """单顾问用工决策: 产能画像(μ/CV/β/α)、保守产能、雇员/孵化双模式 NPV+IRR、
    最终决策和逐条判断依据(rationale 字段)。
    name_or_id: 顾问姓名(如'于肖肖')或谷露用户ID。"""
    d = _find_advisor(name_or_id)
    d["rationale"] = build_rationale(d)
    return d


@mcp.tool()
def headhunt_salary_scan(name_or_id: str, scenario: str = "B") -> dict:
    """调薪幅度测算: 扫描年薪 6-30万, 返回 EMPLOY 极限月薪、盈亏平衡月薪、
    NPV 曲线和判断依据(rationale)。
    scenario: A=公司斜率口径(保守) / B=外部行业斜率-0.05(默认) / C=外部+免波动惩罚(乐观)"""
    d = _find_advisor(name_or_id)
    s = _salary_scan_compute(d["advisor_id"], scenario)
    s["rationale"] = build_scan_rationale(s)
    return s


@mcp.tool()
def headhunt_rerun(fresh: bool = False) -> dict:
    """重跑决策管线(管理员用). fresh=true 重新采集谷露数据库, 否则用缓存数据重算."""
    res = run_pipeline(os.path.join(BASE, "config", "config.yaml"), use_cache=not fresh)
    return {"ok": True, "n_active": res["meta"]["n_active"],
            "market": res["market"], "generated_at": res["board"]["generated_at"]}


@mcp.tool()
def headhunt_candidate_intake(name: str, target_line: str = "", notes: str = "", created_by: str = "") -> dict:
    """外部顾问候选人建档(面试信息采集): 创建候选人记录, 返回自评问卷链接和 HR 评估链接。
    自评问卷公网可达(token-only): 把 self_url 发给候选人填写, HR 用 hr_url 做面试评估。
    name: 候选人姓名(必填); target_line: 目标职能线(如'临床运营'); notes: 备注(如来源/推荐人)。"""
    if not name.strip():
        raise ValueError("候选人姓名不能为空")
    from candidate.store import new_candidate
    rec = new_candidate(name.strip(), target_line.strip(), notes.strip(), created_by=created_by.strip())
    base = os.environ.get("HEADHUNT_PUBLIC_BASE", "https://www.hiijob.cn").rstrip("/")
    return {"cid": rec["cid"], "name": rec["name"], "status": rec["status"],
            "self_url": f"{base}/q/{rec['token']}",
            "hr_url": f"{base}/h/{rec['hr_token']}",
            "expires_at": rec["token_expires_at"]}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
