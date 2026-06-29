"""
隐私脱敏模块 - 自动脱敏敏感信息
"""

from __future__ import annotations

import re
from typing import Any


def privacy_redact(text: str, rules: list[dict[str, Any]] | None = None) -> str:
    """
    根据规则脱敏敏感信息

    Args:
        text: 原始文本
        rules: 脱敏规则列表，每个规则包含 pattern, action, replacement
               如果为 None，使用默认规则

    Returns:
        脱敏后的文本
    """
    if not text:
        return ""

    if rules is None:
        rules = get_default_rules()

    redacted = text
    for rule in rules:
        pattern = rule.get("pattern", "")
        action = rule.get("action", "redact")
        replacement = rule.get("replacement", "[REDACTED]")

        if not pattern:
            continue

        try:
            if action == "redact":
                redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)
            elif action == "redact_line":
                redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE | re.MULTILINE)
            elif action == "mask":
                # 部分遮盖，如手机号 138****1234
                redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)
        except re.error as e:
            print(f"Warning: invalid regex pattern '{pattern}': {e}")
            continue

    return redacted


def get_default_rules() -> list[dict[str, Any]]:
    """获取默认脱敏规则"""
    return [
        {
            "pattern": r"\b\d{17}[\dXx]\b",
            "action": "redact",
            "replacement": "[身份信息已脱敏]",
            "description": "18位身份证号",
        },
        {
            "pattern": r"\b\d{15}\b",
            "action": "redact",
            "replacement": "[身份信息已脱敏]",
            "description": "15位身份证号",
        },
        {
            "pattern": r"(?im)^(.*(?:身份证|身份证号|ID No\.?|National ID).*)$",
            "action": "redact_line",
            "replacement": "[身份信息行已脱敏]",
            "description": "包含身份证关键字的整行",
        },
        {
            "pattern": r"(?im)^(.*(?:家庭住址|详细住址|Home Address|Residential Address).*)$",
            "action": "redact_line",
            "replacement": "[住址信息行已脱敏]",
            "description": "包含住址关键字的整行",
        },
        {
            "pattern": r"(?im)^(.*(?:护照|Passport No|护照号码).*)$",
            "action": "redact_line",
            "replacement": "[护照信息行已脱敏]",
            "description": "包含护照关键字的整行",
        },
    ]


# 便捷函数
__all__ = ["privacy_redact", "get_default_rules"]
