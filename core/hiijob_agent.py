from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests


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
        resume_text = (context.get("resume_text") or "").strip()
        summary = (
            f"{candidate} appears potentially relevant for {position} based on the provided profile. "
            "Please review and enrich this draft with verified consultant notes."
        )
        if resume_text:
            summary = (
                f"{candidate} appears potentially relevant for {position}. "
                "The provided resume text should be reviewed against the role requirements before submission."
            )
        return {
            "comments": {
                "recommendation_rationale": {
                    "strengths_summary": summary,
                    "risk_notes": "Pending consultant verification of achievements, motivation, compensation, and availability.",
                },
                "motivation": "Pending consultant input.",
                "role_fit": f"Initial fit for {position} requires consultant validation.",
            },
            "missing_information": [
                {"field": "consultant_notes", "message": "Add verified interview notes or call summary."}
            ],
        }
