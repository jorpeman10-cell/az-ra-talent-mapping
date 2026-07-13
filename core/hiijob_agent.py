from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from .resume_parser import resume_evidence_from_data


@dataclass
class HiijobAgentClient:
    base_url: str | None = None
    agent_id: str | None = None
    token: str | None = None
    timeout: float | None = None

    @classmethod
    def from_env(cls) -> "HiijobAgentClient":
        timeout_raw = os.environ.get("HIIJOB_AGENT_TIMEOUT", "30")
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 30.0
        return cls(
            base_url=os.environ.get("HIIJOB_AGENT_BASE_URL", ""),
            agent_id=os.environ.get("HIIJOB_REPORT_AGENT_ID", ""),
            token=os.environ.get("HIIJOB_AGENT_TOKEN", ""),
            timeout=timeout,
        )

    def generate_comments(self, context: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url or not self.agent_id or not self.token:
            return self._fallback_comments(context)

        payload = {
            "agent_id": self.agent_id,
            "task": "generate_candidate_referral_comments",
            "context": context,
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            self.base_url.rstrip("/") + "/api/v1/agents/run",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            timeout=self.timeout or 30,
        )
        response.raise_for_status()
        data = response.json()
        if "comments" in data:
            return data
        if isinstance(data.get("result"), dict) and "comments" in data["result"]:
            return data["result"]
        return self._fallback_comments(context)

    def _fallback_comments(self, context: dict[str, Any]) -> dict[str, Any]:
        candidate = context.get("candidate_name") or "the candidate"
        position = context.get("position_title") or "the target role"
        jd_text = str(context.get("job_description") or "").strip()
        evidence = resume_evidence_from_data(context, limit=4)
        evidence_text = "; ".join(evidence[:3]) if evidence else "resume evidence is limited"
        jd_focus = _compact_text(jd_text, 260) if jd_text else "no formal JD was provided"
        is_zh = bool(re.search(r"[\u4e00-\u9fff]", " ".join([str(candidate), str(position), jd_text, str(context.get("resume_text") or context.get("original_resume") or "")])))
        if is_zh:
            summary = f"{candidate} 与 {position} 存在初步相关性，主要依据包括：{evidence_text}。JD 对照重点为：{jd_focus}。建议顾问继续核实关键业绩与客户岗位要求的匹配度。"
            risk_notes = "建议顾问继续确认业绩真实性、与客户岗位的可迁移性、候选人动机、薪资期望、到岗时间、汇报线偏好及竞业限制。"
            motivation = "候选人动机仍需通过访谈记录进一步补充，例如换岗原因、目标平台偏好和长期职业诉求。"
            role_fit = f"对 {position} 的岗位匹配需要结合简历中的项目、业绩证据与 JD 要求判断，重点关注业务场景、客户硬性条件和可迁移经验。"
            if not evidence:
                risk_notes += " 当前简历提取信息偏少，建议补充更完整简历或顾问访谈记录。"
            return {
                "comments": {
                    "recommendation_rationale": {
                        "strengths_summary": summary,
                        "risk_notes": risk_notes,
                    },
                    "motivation": motivation,
                    "role_fit": role_fit,
                },
                "missing_information": [
                    {"field": "consultant_notes", "message": "请补充已验证的访谈记录或沟通摘要。"}
                ],
            }
        summary = (
            f"EN: {candidate} shows initial relevance for {position} based on resume evidence: {evidence_text}. "
            f"The comparison point from the JD is: {jd_focus}. "
            "CN: 基于简历证据，该候选人与目标岗位存在初步匹配；需要重点对照 JD 中的职责、业务场景和客户要求进行复核。"
        )
        risk_notes = (
            "EN: Please verify whether the achievements are directly transferable to the client context, and confirm motivation, "
            "compensation expectations, availability, reporting line preference, and any non-compete constraints. "
            "CN: 建议顾问继续确认业绩真实性、与客户岗位的可迁移性、候选人动机、薪酬期望、到岗时间、汇报线偏好及竞业限制。"
        )
        motivation = (
            "EN: Motivation still needs consultant validation through interview notes. "
            "CN: 候选人动机目前需要顾问通过沟通记录进一步补充，例如换岗原因、目标平台偏好和长期职业诉求。"
        )
        role_fit = (
            f"EN: Initial role fit for {position} is supported when the resume evidence aligns with the JD priorities above; "
            "final recommendation should depend on consultant validation and client-specific must-haves. "
            f"CN: 对 {position} 的岗位匹配需要结合简历中的项目/业绩证据与 JD 要求判断，尤其是医学策略、跨部门协作、业务影响和客户硬性条件。"
        )
        if not evidence:
            risk_notes += " EN: Resume extraction appears thin; upload a richer resume or add consultant notes before submission. CN: 当前简历提取信息偏少，建议补充更完整简历或顾问访谈记录。"
        return {
            "comments": {
                "recommendation_rationale": {
                    "strengths_summary": summary,
                    "risk_notes": risk_notes,
                },
                "motivation": motivation,
                "role_fit": role_fit,
            },
            "missing_information": [
                {"field": "consultant_notes", "message": "Add verified interview notes or call summary."}
            ],
        }

    def _fallback_comments(self, context: dict[str, Any]) -> dict[str, Any]:
        candidate = context.get("candidate_name") or "the candidate"
        position = context.get("position_title") or "the target role"
        jd_text = str(context.get("job_description") or "").strip()
        evidence = resume_evidence_from_data(context, limit=4)
        evidence_text = "; ".join(evidence[:3]) if evidence else "resume evidence is limited"
        jd_focus = _compact_text(jd_text, 260) if jd_text else "no formal JD was provided"
        probe = " ".join(
            [
                str(candidate),
                str(position),
                jd_text,
                str(context.get("resume_text") or context.get("original_resume") or ""),
            ]
        )
        is_zh = bool(re.search(r"[\u4e00-\u9fff]", probe))

        if is_zh:
            evidence_cn = evidence_text if evidence else "当前简历证据较少"
            jd_cn = jd_focus if jd_text else "暂无正式 JD，需以顾问补充的岗位要求为准"
            summary = (
                f"{candidate} 与 {position} 存在初步相关性，主要依据包括：{evidence_cn}。"
                f"岗位对照重点：{jd_cn}。建议顾问继续核实关键业绩与客户岗位要求的匹配度。"
            )
            risk_notes = (
                "建议顾问继续确认业绩真实性、业绩能否迁移到客户场景、候选人动机、薪资期望、"
                "到岗时间、汇报线偏好以及竞业限制。"
            )
            motivation = (
                "候选人动机仍需要通过访谈记录进一步补充，例如换岗原因、目标平台偏好、"
                "长期职业诉求以及对客户机会的真实兴趣。"
            )
            role_fit = (
                f"对 {position} 的岗位匹配需要结合简历中的项目、业绩证据与 JD 要求判断，"
                "重点关注业务场景、客户硬性条件、团队管理经验和可迁移成果。"
            )
            if not evidence:
                risk_notes += " 当前简历提取信息偏少，建议补充更完整简历或顾问访谈记录。"
            missing_message = "请补充已验证的访谈记录或沟通摘要。"
        else:
            summary = (
                f"{candidate} shows initial relevance for {position} based on resume evidence: {evidence_text}. "
                f"The comparison point from the JD is: {jd_focus}. "
                "The consultant should verify the most relevant achievements against client-specific requirements before submission."
            )
            risk_notes = (
                "Please verify whether the achievements are directly transferable to the client context, and confirm motivation, "
                "compensation expectations, availability, reporting line preference, and any non-compete constraints."
            )
            motivation = (
                "Motivation still needs consultant validation through interview notes, including change drivers, platform preference, "
                "and long-term career objectives."
            )
            role_fit = (
                f"Initial role fit for {position} is supported when resume evidence aligns with the JD priorities above; "
                "final recommendation should depend on consultant validation and client-specific must-haves."
            )
            if not evidence:
                risk_notes += " Resume extraction appears thin; upload a richer resume or add consultant notes before submission."
            missing_message = "Add verified interview notes or call summary."

        return {
            "comments": {
                "recommendation_rationale": {
                    "strengths_summary": summary,
                    "risk_notes": risk_notes,
                },
                "motivation": motivation,
                "role_fit": role_fit,
            },
            "missing_information": [
                {"field": "consultant_notes", "message": missing_message}
            ],
        }


def _compact_text(text: str, limit: int) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."
