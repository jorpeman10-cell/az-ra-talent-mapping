"""
数据校验模块 - 验证报告数据完整性
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MissingItem:
    """缺失项"""
    field: str
    message: str
    severity: str = "error"  # error / warning / info


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool = True
    missing_items: list[MissingItem] = field(default_factory=list)
    warnings: list[MissingItem] = field(default_factory=list)

    def add_missing(self, field: str, message: str, severity: str = "error") -> None:
        """添加缺失项"""
        item = MissingItem(field=field, message=message, severity=severity)
        if severity == "error":
            self.is_valid = False
            self.missing_items.append(item)
        else:
            self.warnings.append(item)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "is_valid": self.is_valid,
            "missing_items": [
                {"field": item.field, "message": item.message, "severity": item.severity}
                for item in self.missing_items
            ],
            "warnings": [
                {"field": item.field, "message": item.message, "severity": item.severity}
                for item in self.warnings
            ],
        }


class DataValidator:
    """数据校验器"""

    def __init__(self, brand_config: dict[str, Any]):
        self.brand_config = brand_config
        self.fields_config = brand_config.get("fields", {})

    def validate(self, data: dict[str, Any]) -> ValidationResult:
        """校验报告数据"""
        result = ValidationResult()

        # 校验必填字段
        required_fields = self.fields_config.get("required", [])
        for field_def in required_fields:
            if not isinstance(field_def, dict):
                continue

            field_name = field_def.get("field")
            label = field_def.get("label", field_name)

            if not field_name:
                continue

            value = data.get(field_name)

            # 检查是否为空
            if not value or (isinstance(value, str) and not value.strip()):
                result.add_missing(field_name, f"请补充 {label}。", "error")
                continue

            # 检查结构化字段的子字段
            if field_def.get("type") == "structured_text" and isinstance(value, dict):
                sub_fields = field_def.get("sub_fields", [])
                for sub_def in sub_fields:
                    if not isinstance(sub_def, dict):
                        continue
                    sub_name = sub_def.get("field")
                    sub_label = sub_def.get("label", sub_name)
                    sub_required = sub_def.get("required", False)

                    if sub_required and sub_name:
                        sub_value = value.get(sub_name)
                        if not sub_value or (isinstance(sub_value, str) and not sub_value.strip()):
                            result.add_missing(
                                f"{field_name}.{sub_name}",
                                f"请补充 {sub_label}。",
                                "error",
                            )

        # 校验隐藏字段
        hidden_fields = self.fields_config.get("hidden", [])
        for field_def in hidden_fields:
            if not isinstance(field_def, dict):
                continue

            field_name = field_def.get("field")
            if field_name == "candidate_consent_confirmed":
                consent = data.get(field_name, False)
                if not consent:
                    result.add_missing(
                        field_name,
                        "请确认已获得候选人同意。",
                        "error",
                    )

        return result

    def prepare_draft_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        准备草稿 payload，对缺失字段添加占位符
        """
        result = dict(data)
        validation = self.validate(data)

        # 对缺失字段添加占位符
        for item in validation.missing_items:
            field_path = item.field
            placeholder = f"[待补充: {item.message}]"

            # 处理嵌套字段（如 recommendation_rationale.strengths_summary）
            if "." in field_path:
                parts = field_path.split(".")
                current = result
                for part in parts[:-1]:
                    if part not in current or not isinstance(current[part], dict):
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = placeholder
            else:
                if not result.get(field_path):
                    result[field_path] = placeholder

        # 添加 missing_information 列表
        result["missing_information"] = [
            {"field": item.field, "message": item.message}
            for item in validation.missing_items
        ]

        return result


# 便捷函数
__all__ = ["MissingItem", "ValidationResult", "DataValidator"]
