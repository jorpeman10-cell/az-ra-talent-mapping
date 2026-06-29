"""
Prompt 模板引擎 - 基于 Jinja2 的 AI 评语生成
"""

from __future__ import annotations

import json
import re
from typing import Any

from jinja2 import Template, Environment, BaseLoader


class PromptEngine:
    """Prompt 模板引擎"""

    def __init__(self, prompt_config: dict[str, Any]):
        self.prompt_config = prompt_config
        self.variables = prompt_config.get("variables", [])
        self.templates = prompt_config.get("templates", [])
        self.output_format = prompt_config.get("output_format", {})

        # 创建 Jinja2 环境
        self.jinja_env = Environment(loader=BaseLoader())

    def build_prompt(
        self,
        template_id: str,
        context: dict[str, Any],
    ) -> dict[str, str]:
        """
        构建 Prompt

        Args:
            template_id: 模板 ID
            context: 上下文变量（resume_text, job_description, known_fields 等）

        Returns:
            {"system_prompt": "...", "user_prompt": "..."}
        """
        template_def = self._find_template(template_id)
        if not template_def:
            raise ValueError(f"Template not found: {template_id}")

        # 解析变量
        variables = self._resolve_variables(context)

        # 渲染 system_prompt
        system_prompt_template = template_def.get("system_prompt", "")
        system_prompt = self._render_template(system_prompt_template, variables)

        # 渲染 user_prompt
        user_prompt_template = template_def.get("user_prompt", "")
        user_prompt = self._render_template(user_prompt_template, variables)

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "output_schema": template_def.get("output_schema", {}),
        }

    def parse_response(self, response_text: str) -> dict[str, Any]:
        """
        解析 AI 响应

        Args:
            response_text: AI 返回的文本

        Returns:
            解析后的 JSON 对象
        """
        if not response_text:
            return {"comments": {}, "missing_information": []}

        # 尝试直接解析 JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # 尝试从 Markdown 代码块中提取 JSON
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试修复常见 JSON 错误
        repaired = self._attempt_json_repair(response_text)
        if repaired:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass

        # 如果所有尝试都失败，返回原始文本作为 comments
        return {
            "comments": {"raw_text": response_text},
            "missing_information": [{"field": "parse_error", "message": "无法解析 AI 响应为 JSON"}],
        }

    def _find_template(self, template_id: str) -> dict[str, Any] | None:
        """查找模板定义"""
        for template in self.templates:
            if template.get("template_id") == template_id:
                return template
        return None

    def _resolve_variables(self, context: dict[str, Any]) -> dict[str, Any]:
        """解析变量值"""
        variables = {}

        # 从 prompt_config 的变量定义中解析
        for var_def in self.variables:
            var_name = var_def.get("name")
            source = var_def.get("source", "")
            default_value = var_def.get("default_value")

            if not var_name:
                continue

            # 解析 source
            # 格式: "brand_config.brand_name" 或 "user_input.resume_text"
            value = self._resolve_source(source, context)

            # 如果值为空，使用默认值
            if value is None:
                value = default_value

            variables[var_name] = value

        # 合并用户传入的上下文（优先级更高）
        for key, value in context.items():
            if value is not None:
                variables[key] = value

        return variables

    def _resolve_source(self, source: str, context: dict[str, Any]) -> Any:
        """解析 source 路径获取值"""
        if not source:
            return None

        # 处理 brand_config.xxx.yyy 格式
        if source.startswith("brand_config."):
            path = source.replace("brand_config.", "")
            return self._get_nested_value(context.get("brand_config", {}), path)

        # 处理 user_input.xxx 格式
        if source.startswith("user_input."):
            path = source.replace("user_input.", "")
            return self._get_nested_value(context.get("user_input", {}), path)

        # 处理 resume_data.xxx 格式
        if source.startswith("resume_data."):
            path = source.replace("resume_data.", "")
            return self._get_nested_value(context.get("resume_data", {}), path)

        # 直接作为 key 从 context 获取
        return context.get(source)

    def _render_template(self, template_text: str, variables: dict[str, Any]) -> str:
        """渲染 Jinja2 模板"""
        if not template_text:
            return ""

        try:
            template = self.jinja_env.from_string(template_text)
            return template.render(**variables)
        except Exception as e:
            print(f"Warning: failed to render template: {e}")
            return template_text

    def _get_nested_value(self, data: dict[str, Any], path: str) -> Any:
        """获取嵌套字典值"""
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def _attempt_json_repair(self, text: str) -> str | None:
        """尝试修复常见 JSON 错误"""
        # 策略 1: 移除 Markdown 代码块标记
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```", "", text)

        # 策略 2: 修复尾部逗号
        text = re.sub(r",(\s*[}\]])", r"\1", text)

        # 策略 3: 尝试找到 JSON 对象
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            return match.group(1)

        return None


# 便捷函数
__all__ = ["PromptEngine"]
