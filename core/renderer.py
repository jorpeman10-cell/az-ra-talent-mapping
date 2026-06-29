"""
DOCX 渲染引擎 - 支持"填充现有模板"和"程序化构建"两种模式
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt, RGBColor
from docx.oxml.ns import qn


class ReportRenderer:
    """报告渲染引擎"""

    def __init__(self, brand_config: dict[str, Any], template_config: dict[str, Any] | None = None):
        self.brand_config = brand_config
        self.template_config = template_config or {}
        self.render_rules = self.template_config.get("render_rules", {})
        self.font_config = self.render_rules.get("font", {})

    def render(self, data: dict[str, Any], output_path: str | Path) -> Path:
        """
        渲染报告

        Args:
            data: 报告数据
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        output_path = Path(output_path)

        # 判断使用哪种模式
        template_mapping = self.brand_config.get("template_mapping", {})
        use_client_template = template_mapping.get("use_client_template", False)

        if use_client_template and self.template_config:
            # 模式 1: 填充客户提供的模板
            doc = self._render_with_template(data)
        else:
            # 模式 2: 程序化构建（TODO: 后续实现）
            doc = self._render_programmatically(data)

        # 保存
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))

        return output_path

    # ============================================================
    # 模式 1: 填充现有模板
    # ============================================================

    def _render_with_template(self, data: dict[str, Any]) -> Document:
        """使用客户提供的模板填充数据"""
        template_mapping = self.brand_config.get("template_mapping", {})
        template_path = template_mapping.get("client_template_path", "")

        if not template_path:
            raise ValueError("client_template_path is not configured")

        # 加载模板
        full_path = Path(__file__).parent.parent / "templates" / template_path
        if not full_path.exists():
            raise FileNotFoundError(f"Template file not found: {full_path}")

        doc = Document(str(full_path))

        # 处理占位符替换
        self._replace_placeholders(doc, data)

        # 处理字段映射
        field_mappings = self.template_config.get("field_mappings", [])
        for mapping in field_mappings:
            self._apply_field_mapping(doc, mapping, data)

        # 处理条件渲染
        conditional_rules = self.template_config.get("conditional_rendering", [])
        for rule in conditional_rules:
            self._apply_conditional_rendering(doc, rule, data)

        # 应用全局样式
        self._apply_global_styles(doc)

        return doc

    def _replace_placeholders(self, doc: Document, data: dict[str, Any]) -> None:
        """替换 {{placeholder}} 形式的占位符"""
        placeholders = self.template_config.get("placeholders", [])

        # 构建占位符映射
        placeholder_map = {}
        for ph in placeholders:
            placeholder = ph.get("placeholder", "")
            field = ph.get("field", "")
            if not placeholder or not field:
                continue

            # 获取值
            value = self._get_nested_value(data, field)
            if value is not None:
                placeholder_map[placeholder] = self._format_value(value, ph.get("format"))

        # 替换段落中的占位符
        for paragraph in doc.paragraphs:
            for placeholder, value in placeholder_map.items():
                if placeholder in paragraph.text:
                    paragraph.text = paragraph.text.replace(placeholder, str(value))

        # 替换表格中的占位符
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for placeholder, value in placeholder_map.items():
                            if placeholder in paragraph.text:
                                paragraph.text = paragraph.text.replace(placeholder, str(value))

    def _apply_field_mapping(self, doc: Document, mapping: dict[str, Any], data: dict[str, Any]) -> None:
        """应用字段映射到文档"""
        field_name = mapping.get("field")
        target = mapping.get("target")
        render_mode = mapping.get("render_mode", "text")

        if not field_name or not target:
            return

        # 获取字段值
        field_value = data.get(field_name)
        if field_value is None:
            return

        # 解析目标位置
        target_parts = target.split(".")

        if target_parts[0] == "table":
            self._fill_table_cell(doc, target_parts, field_value, render_mode, mapping)
        elif target_parts[0] == "paragraph":
            self._fill_paragraph(doc, target_parts, field_value)

    def _fill_table_cell(
        self,
        doc: Document,
        target_parts: list[str],
        value: Any,
        render_mode: str,
        mapping: dict[str, Any],
    ) -> None:
        """填充表格单元格"""
        try:
            table_idx = int(target_parts[1])
            if table_idx >= len(doc.tables):
                return

            table = doc.tables[table_idx]

            # 如果目标是整个表格（如原始简历）
            if len(target_parts) == 2:
                if render_mode == "append_paragraphs":
                    self._append_to_table(table, value, mapping)
                return

            row_idx = int(target_parts[3]) if len(target_parts) > 3 else 0
            cell_idx = int(target_parts[5]) if len(target_parts) > 5 else 0

            if row_idx >= len(table.rows):
                return

            cell = table.rows[row_idx].cells[cell_idx]

            if render_mode == "structured":
                self._fill_structured_cell(cell, value, mapping.get("structured_format", {}))
            else:
                self._set_cell_text(cell, str(value))

        except (IndexError, ValueError) as e:
            print(f"Warning: failed to fill table cell at {'.'.join(target_parts)}: {e}")

    def _fill_structured_cell(self, cell: Any, value: dict[str, Any], format_config: dict[str, Any]) -> None:
        """填充结构化字段（如 Recommendation Rationale）"""
        # 清空单元格
        cell.text = ""

        header = format_config.get("header", "")
        sub_fields = format_config.get("sub_fields", [])
        separator = format_config.get("separator", "\n\n")
        sub_field_separator = format_config.get("sub_field_separator", "\n")

        paragraphs = []

        if header:
            paragraphs.append(f"{header}")
            paragraphs.append("")

        for sub_def in sub_fields:
            sub_field_name = sub_def.get("field")
            sub_label = sub_def.get("label", sub_field_name)
            prefix = sub_def.get("prefix", "")
            condition = sub_def.get("condition")

            sub_value = value.get(sub_field_name) if isinstance(value, dict) else None

            # 条件检查
            if condition == "not_empty" and not sub_value:
                continue

            if sub_value:
                formatted = f"{prefix}{sub_label}: {sub_value}"
                paragraphs.append(formatted)

        # 写入单元格
        cell.text = "\n".join(paragraphs)
        self._apply_font_to_cell(cell)

    def _append_to_table(self, table: Any, value: str, mapping: dict[str, Any]) -> None:
        """将长文本分段追加到表格"""
        config = mapping.get("append_paragraphs_config", {})
        max_chars = config.get("max_chars_per_cell", 2000)
        split_strategy = config.get("split_strategy", "paragraph")

        if split_strategy == "paragraph":
            paragraphs = value.split("\n\n")
        else:
            paragraphs = [value[i:i + max_chars] for i in range(0, len(value), max_chars)]

        for para in paragraphs:
            if not para.strip():
                continue

            row = table.add_row()
            cell = row.cells[0]
            cell.text = para.strip()
            self._apply_font_to_cell(cell)

    def _fill_paragraph(self, doc: Document, target_parts: list[str], value: Any) -> None:
        """填充段落"""
        try:
            para_idx = int(target_parts[1])
            if para_idx < len(doc.paragraphs):
                doc.paragraphs[para_idx].text = str(value)
        except (IndexError, ValueError):
            pass

    def _apply_conditional_rendering(self, doc: Document, rule: dict[str, Any], data: dict[str, Any]) -> None:
        """应用条件渲染规则"""
        condition = rule.get("condition")
        field_name = rule.get("field")
        action = rule.get("action")
        target = rule.get("target")

        if not all([condition, field_name, action, target]):
            return

        # 获取字段值
        field_value = data.get(field_name)

        # 评估条件
        condition_met = False
        if condition == "field_empty":
            condition_met = not field_value or (isinstance(field_value, str) and not field_value.strip())
        elif condition == "field_not_empty":
            condition_met = bool(field_value) and (not isinstance(field_value, str) or field_value.strip())

        if not condition_met:
            return

        # 执行动作
        if action == "hide_row":
            self._hide_row(doc, target)
        elif action == "show_placeholder":
            self._show_placeholder(doc, target, rule.get("placeholder", ""))

    def _hide_row(self, doc: Document, target: str) -> None:
        """隐藏表格行"""
        try:
            parts = target.split(".")
            table_idx = int(parts[1])
            row_idx = int(parts[3])

            if table_idx < len(doc.tables):
                table = doc.tables[table_idx]
                if row_idx < len(table.rows):
                    row = table.rows[row_idx]
                    # 隐藏行：将行高设为 0
                    row.height = Pt(0)
                    # 清空内容
                    for cell in row.cells:
                        cell.text = ""
        except (IndexError, ValueError):
            pass

    def _show_placeholder(self, doc: Document, target: str, placeholder: str) -> None:
        """显示占位符"""
        try:
            parts = target.split(".")
            table_idx = int(parts[1])
            row_idx = int(parts[3])
            cell_idx = int(parts[5]) if len(parts) > 5 else 0

            if table_idx < len(doc.tables):
                table = doc.tables[table_idx]
                if row_idx < len(table.rows):
                    cell = table.rows[row_idx].cells[cell_idx]
                    cell.text = placeholder
                    self._apply_font_to_cell(cell, italic=True, color="999999")
        except (IndexError, ValueError):
            pass

    # ============================================================
    # 模式 2: 程序化构建（简化版）
    # ============================================================

    def _render_programmatically(self, data: dict[str, Any]) -> Document:
        """程序化构建 DOCX（简化版，后续扩展）"""
        doc = Document()

        # 设置默认字体
        style = doc.styles["Normal"]
        font = style.font
        font.name = self.font_config.get("family_en", "Arial")
        font.size = Pt(self.font_config.get("size", 10.5))

        # 添加标题
        title = doc.add_heading("候选人推荐报告", level=0)
        title.alignment = 1  # 居中

        # 添加基本信息
        doc.add_heading("职位信息", level=1)
        self._add_info_table(doc, data, ["position_title", "location", "department_function", "req_id"])

        # 添加候选人信息
        doc.add_heading("候选人信息", level=1)
        self._add_info_table(doc, data, ["candidate_name", "current_title", "current_company", "years_of_experience"])

        # 添加顾问评估
        doc.add_heading("顾问评估", level=1)
        self._add_assessment_section(doc, data)

        # 添加原始简历
        if data.get("original_resume"):
            doc.add_heading("原始简历", level=1)
            doc.add_paragraph(data["original_resume"])

        return doc

    def _add_info_table(self, doc: Document, data: dict[str, Any], fields: list[str]) -> None:
        """添加信息表格"""
        table = doc.add_table(rows=0, cols=2)
        table.style = "Table Grid"

        for field_name in fields:
            value = data.get(field_name, "")
            if not value:
                continue

            row = table.add_row()
            row.cells[0].text = field_name.replace("_", " ").title()
            row.cells[1].text = str(value)

        doc.add_paragraph()

    def _add_assessment_section(self, doc: Document, data: dict[str, Any]) -> None:
        """添加顾问评估部分"""
        assessment_fields = [
            ("motivation", "跳槽动因"),
            ("recommendation_rationale", "推荐理由"),
            ("opportunity_to_improve", "可提升空间"),
            ("role_fit", "岗位契合度"),
        ]

        for field_name, label in assessment_fields:
            value = data.get(field_name)
            if not value:
                continue

            doc.add_heading(label, level=2)

            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if sub_value:
                        p = doc.add_paragraph()
                        p.add_run(f"{sub_key.replace('_', ' ').title()}: ").bold = True
                        p.add_run(str(sub_value))
            else:
                doc.add_paragraph(str(value))

    # ============================================================
    # 工具方法
    # ============================================================

    def _set_cell_text(self, cell: Any, text: str) -> None:
        """设置单元格文本并应用字体"""
        cell.text = text
        self._apply_font_to_cell(cell)

    def _apply_font_to_cell(self, cell: Any, bold: bool = False, italic: bool = False, color: str | None = None) -> None:
        """应用字体样式到单元格"""
        font_family = self.font_config.get("family", "Microsoft YaHei")
        font_family_en = self.font_config.get("family_en", "Arial")
        font_size = self.font_config.get("size", 10.5)

        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.name = font_family_en
                run.font.size = Pt(font_size)
                run.bold = bold
                run.italic = italic
                if color:
                    run.font.color.rgb = RGBColor.from_string(color)

                # 设置中文字体
                run._element.rPr.rFonts.set(qn("w:eastAsia"), font_family)

    def _apply_global_styles(self, doc: Document) -> None:
        """应用全局样式"""
        # 遍历所有段落和表格单元格，统一字体
        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                self._apply_font_to_run(run)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            self._apply_font_to_run(run)

    def _apply_font_to_run(self, run: Any) -> None:
        """应用字体到 run"""
        font_family = self.font_config.get("family", "Microsoft YaHei")
        font_family_en = self.font_config.get("family_en", "Arial")
        font_size = self.font_config.get("size", 10.5)

        run.font.name = font_family_en
        run.font.size = Pt(font_size)
        run._element.rPr.rFonts.set(qn("w:eastAsia"), font_family)

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

    def _format_value(self, value: Any, format_config: dict[str, Any] | None) -> str:
        """根据格式配置格式化值"""
        if not format_config:
            return str(value)

        fmt_type = format_config.get("type")

        if fmt_type == "date" and isinstance(value, str):
            # 简单日期格式化
            from datetime import datetime
            try:
                dt = datetime.strptime(value, "%Y-%m-%d")
                pattern = format_config.get("pattern", "%Y-%m-%d")
                return dt.strftime(pattern)
            except ValueError:
                return str(value)

        if fmt_type == "number" and isinstance(value, (int, float)):
            suffix = format_config.get("suffix", "")
            return f"{value}{suffix}"

        return str(value)


# 便捷函数
__all__ = ["ReportRenderer"]
