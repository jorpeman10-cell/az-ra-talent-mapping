# 人才简历推荐报告生成工具（通用版）—— 开发文档

> **文档版本**: v1.0  
> **日期**: 2026-06-29  
> **状态**: 核心引擎已完成，待开发 UI / API / 集成层  
> **目标读者**: Claude / Codex / 技术团队

---

## 1. 项目概述

### 1.1 背景
Tstar 目前有一份针对 **AstraZeneca（AZ）** 的硬编码简历推荐报告工具，无法复用于其他客户。每新增一个客户需重新开发，成本高、交付慢。

### 1.2 目标
构建一个**可配置、可扩展**的通用报告生成引擎，支持：
- 多客户模板管理（配置化，无需代码变更）
- 简历上传即解析（PDF/Word）
- AI 自动生成推荐评语
- 品牌元素动态渲染（Logo、配色、字体）
- 报告一键导出 PDF/Word

### 1.3 成功指标
| 指标 | 基准 | 目标 |
|------|------|------|
| 单份报告生成时间 | 15-30 min（手动） | < 3 min |
| 新客户模板配置时间 | 1-2 周（开发） | < 1 天 |
| 评语生成准确率 | — | > 85% |
| 顾问使用率 | — | > 80%（上线 1 个月内） |

---

## 2. 项目结构

```
generic-report-tool/
├── core/                          # 核心引擎（已完成）
│   ├── __init__.py
│   ├── config_loader.py           # 配置加载器（支持继承、合并、热加载）
│   ├── parser.py                  # 简历解析（PDF/DOCX/TXT）
│   ├── redactor.py                # 隐私脱敏（可配置规则）
│   ├── validator.py               # 数据校验（必填字段、结构化子字段）
│   ├── renderer.py                # DOCX 渲染引擎（模板填充 + 程序化构建）
│   ├── prompt_engine.py           # Prompt 模板引擎（Jinja2）
│   └── mcp_server.py              # MCP 协议服务
├── config/                        # 配置文件（已完成）
│   ├── brands/
│   │   ├── default.yaml           # 通用默认配置
│   │   ├── az.yaml                # AstraZeneca 特化配置
│   │   └── jnj.yaml               # 强生示例配置
│   ├── templates/
│   │   ├── az_referral_report.yaml   # AZ 模板映射
│   │   └── generic_report.yaml       # 通用模板映射
│   ├── prompts/
│   │   └── prompt_engine.yaml   # Prompt 引擎配置
│   └── README.md                  # 配置系统架构说明
├── ui/                            # Streamlit 前端（待开发）
├── api/                           # HTTP API 服务（待开发）
├── templates/                     # 客户 DOCX 模板（存放客户提供的模板文件）
├── tests/                         # 测试（待开发）
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 3. 已完成的核心模块

### 3.1 配置加载器 (`core/config_loader.py`)

**功能**:
- 加载品牌配置（YAML），支持继承链（`inherits: "parent_id"`）
- 递归合并配置（子配置优先，字段定义按 `field` 合并，章节按 `id` 合并）
- 缓存机制（TTL 300秒，文件修改自动失效）
- 配置验证（字段唯一性、模板映射有效性等）

**关键 API**:
```python
from core.config_loader import get_loader, ConfigValidator

loader = get_loader("../config")  # 或环境变量 GENERIC_REPORT_CONFIG_DIR
brand_config = loader.load_brand("az")       # 加载品牌配置（含继承合并）
template_config = loader.load_template("az_referral_report")  # 加载模板映射
brands = loader.list_brands()               # 列出所有品牌

validator = ConfigValidator(loader)
validator.validate_brand("az")              # 验证品牌配置
validator.validate_template("az_referral_report")  # 验证模板配置
```

**CLI 用法**:
```bash
python -m core.config_loader --list                    # 列出所有品牌
python -m core.config_loader --validate az             # 验证 AZ 配置
python -m core.config_loader --show az                 # 查看合并后的配置
```

**配置继承规则**:
- 子配置覆盖父配置的标量字段
- 字典字段递归合并
- 字段定义列表（含 `field` 键）按 `field` 合并，子配置优先
- 章节列表（含 `id` 键）按 `id` 合并
- 简单列表（如 `focus_areas`）子配置完全覆盖

---

### 3.2 简历解析 (`core/parser.py`)

**功能**:
- 支持 PDF（pdfplumber）、DOCX（python-docx）、TXT/MD 格式
- 自动清理多余空白和特殊字符

**关键 API**:
```python
from core.parser import extract_resume_text

text = extract_resume_text("/path/to/resume.pdf")   # 自动识别格式
```

---

### 3.3 隐私脱敏 (`core/redactor.py`)

**功能**:
- 可配置正则规则脱敏敏感信息
- 默认规则：身份证号、住址、护照

**关键 API**:
```python
from core.redactor import privacy_redact, get_default_rules

# 使用默认规则
redacted = privacy_redact(resume_text)

# 使用自定义规则（从品牌配置加载）
rules = brand_config["compliance"]["privacy_rules"]
redacted = privacy_redact(resume_text, rules)
```

---

### 3.4 数据校验 (`core/validator.py`)

**功能**:
- 根据品牌配置的字段定义校验必填项
- 支持结构化字段（如 `recommendation_rationale` 的子字段）
- 自动生成缺失字段占位符 `[待补充: ...]`

**关键 API**:
```python
from core.validator import DataValidator

validator = DataValidator(brand_config)
result = validator.validate(data)           # 返回 ValidationResult
is_valid = result.is_valid
missing = result.missing_items              # 缺失字段列表

# 生成草稿 payload（自动填充占位符）
draft_data = validator.prepare_draft_payload(data)
```

---

### 3.5 渲染引擎 (`core/renderer.py`)

**功能**:
- **模式 1**: 填充客户提供的 DOCX 模板（核心模式）
- **模式 2**: 程序化构建 DOCX（简化版，后续扩展）
- 支持占位符替换（`{{placeholder}}`）
- 支持结构化字段渲染（子字段合并为格式化文本）
- 支持条件渲染（字段为空时隐藏行或显示占位符）
- 全局字体样式应用

**关键 API**:
```python
from core.renderer import ReportRenderer

renderer = ReportRenderer(brand_config, template_config)
output_path = renderer.render(data, "/path/to/output.docx")
```

**模板映射配置示例**:
```yaml
field_mappings:
  - field: "position_title"
    target: "table.0.row.0.cell.1"
    render_mode: "text"
  
  - field: "recommendation_rationale"
    target: "table.1.row.4.cell.0"
    render_mode: "structured"
    structured_format:
      header: "Recommendation Rationale"
      sub_fields:
        - field: "strengths_summary"
          label: "Strengths Summary"
          prefix: "• "
      separator: "\n\n"
```

---

### 3.6 Prompt 模板引擎 (`core/prompt_engine.py`)

**功能**:
- 基于 Jinja2 的 Prompt 模板渲染
- 变量自动注入（从品牌配置、用户输入、简历数据解析）
- AI 响应解析（支持 JSON、Markdown 代码块、自动修复）

**关键 API**:
```python
from core.prompt_engine import PromptEngine

prompt_config = loader.load_prompt_engine()
engine = PromptEngine(prompt_config)

# 构建 Prompt
result = engine.build_prompt("generate_draft_comments", context={
    "brand_config": brand_config,
    "resume_text": resume_text,
    "position_title": "研发总监",
    "job_description": "",
    "known_fields": {},
})
# result = {"system_prompt": "...", "user_prompt": "...", "output_schema": {...}}

# 解析 AI 响应
parsed = engine.parse_response(ai_response_text)
# parsed = {"comments": {...}, "missing_information": [...]}
```

**Prompt 模板变量**:
| 变量名 | 来源 | 说明 |
|--------|------|------|
| `brand_name` | `brand_config.brand_name` | 品牌名称 |
| `system_role` | `brand_config.prompt_rules.system_role` | AI 角色定义 |
| `tone` | `brand_config.comment_style.tone` | 评语语气 |
| `length` | `brand_config.comment_style.length` | 评语长度 |
| `language` | `brand_config.comment_style.language` | 语言 |
| `focus_areas` | `brand_config.comment_style.focus_areas` | 重点方向 |
| `must_follow_rules` | `brand_config.prompt_rules.must_follow` | 必须遵守规则 |
| `prohibited_rules` | `brand_config.prompt_rules.prohibited` | 禁止事项 |
| `resume_text` | `user_input.resume_text` | 简历文本 |
| `job_description` | `user_input.job_description` | 职位描述 |
| `position_title` | `user_input.position_title` | 目标职位 |

---

### 3.7 MCP 服务 (`core/mcp_server.py`)

**功能**:
- HTTP 服务，支持 MCP JSON-RPC 协议
- 端点：`/mcp`（MCP 协议）、`/draft`（草稿）、`/generate-report`（生成报告）
- 动态工具注册（根据品牌配置自动生成 `tools/list`）

**关键 API**:
```python
from core.mcp_server import run_server

run_server(host="0.0.0.0", port=8767, config_dir="../config")
```

---

## 4. 配置系统详解

### 4.1 品牌配置 (`config/brands/*.yaml`)

**核心字段**:
```yaml
brand_id: "az_custom_v2"          # 唯一标识
brand_name: "AstraZeneca 定制版"   # 显示名称
inherits: "default"                # 继承自哪个配置（可选）
version: "2.0.0"

branding:                          # 品牌元素
  tstar_logo_url: "..."
  primary_color: "#830051"
  font_family: "Microsoft YaHei"
  font_family_en: "Arial"

report_structure:                  # 报告章节
  sections:
    - id: "cover"
      name: "封面"
      enabled: true

fields:                            # 字段定义
  groups:                          # 字段分组
  required:                        # 必填字段
  optional:                        # 可选字段
  hidden:                          # 隐藏字段

comment_style:                     # 评语风格
  tone: "professional"             # professional / casual / formal
  length: "medium"                 # short / medium / detailed
  language: "zh-en"                # zh / en / zh-en
  focus_areas: [...]               # 重点方向
  sections: [...]                  # 评语模块

compliance:                        # 合规声明
  disclaimer: {...}
  confidentiality: {...}
  privacy_rules: [...]             # 脱敏规则

template_mapping:                  # 模板映射
  use_client_template: true
  client_template_path: "az/Candidate Referral Report.docx"

prompt_rules:                      # AI Prompt 规则
  system_role: "..."
  must_follow: [...]
  prohibited: [...]

export:                            # 导出配置
  default_format: "docx"
  filename_template: "AZ_{candidate_name}_Report_{date}"
```

**字段定义结构**:
```yaml
- field: "position_title"          # 字段名（唯一标识）
  group: "position"                # 所属分组
  label: "职位名称"                 # 显示标签
  label_en: "Position Title"       # 英文标签
  type: "string"                    # 数据类型：string / text / number / boolean / structured_text
  max_length: 200                   # 最大长度
  placeholder: "..."                # 占位符提示
  required: true                    # 是否必填（用于结构化子字段）
  validation:                       # 校验规则
    - type: "not_empty"
      message: "..."
  ai_prompt_hint: "..."             # AI 生成提示
```

### 4.2 模板映射配置 (`config/templates/*.yaml`)

```yaml
template_id: "az_referral_report_v2"
brand_id: "az_custom_v2"
docx_path: "az/Candidate Referral Report.docx"

field_mappings:                    # 字段映射（核心）
  - field: "position_title"
    target: "table.0.row.0.cell.1"  # 定位语法
    target_type: "table_cell"
    render_mode: "text"             # text / structured / append_paragraphs / replace_placeholder
  
  - field: "recommendation_rationale"
    target: "table.1.row.4.cell.0"
    render_mode: "structured"
    structured_format:
      header: "..."
      sub_fields:
        - field: "strengths_summary"
          label: "Strengths Summary"
          prefix: "• "
          condition: "not_empty"   # 条件：为空时不显示
      separator: "\n\n"

placeholders:                      # 占位符替换
  - placeholder: "{{REPORT_DATE}}"
    field: "report_date"
    format: "date"
    format_pattern: "%Y-%m-%d"

render_rules:                      # 渲染规则
  font:
    family: "Microsoft YaHei"
    size: 7
  table_style:
    border: true
    border_color: "#000000"
  page_break:
    before_sections: []
    after_sections: ["original_resume"]

conditional_rendering:             # 条件渲染
  - condition: "field_empty"
    field: "technical_skill_areas"
    action: "hide_section"
    target: "table.1.row.4.cell.0"
```

### 4.3 Prompt 引擎配置 (`config/prompts/prompt_engine.yaml`)

```yaml
variables:                         # 变量定义
  - name: "brand_name"
    source: "brand_config.brand_name"
    default_value: "Tstar"

templates:                         # Prompt 模板
  - template_id: "generate_draft_comments"
    system_prompt: |
      {{ system_role }}
      你正在为 {{ brand_name }} 撰写候选人推荐报告。
      ...
    user_prompt: |
      【候选人简历】
      {{ resume_text }}
      ...
    output_schema:                   # 输出 JSON Schema
      type: "object"
      properties:
        comments: {...}
        missing_information: {...}

output_format:                     # 输出格式配置
  json_parsing:
    allow_markdown_wrapper: true
    attempt_repair: true
```

---

## 5. 待开发任务清单

### 5.1 高优先级（MVP 必需）

| # | 任务 | 说明 | 预估工时 |
|---|------|------|----------|
| 1 | **Streamlit UI 开发** | 基于现有 AZ 工具 `az_report_app.py` 重构，支持品牌选择、字段动态渲染 | 2-3 天 |
| 2 | **LLM 集成层** | 封装 OpenAI / Claude / 通义千问 API 调用，支持配置切换 | 1-2 天 |
| 3 | **API 服务完善** | 完善 `api/bridge.py`，支持完整的报告生成流程 | 1-2 天 |
| 4 | **测试用例** | 单元测试覆盖配置加载、渲染、校验、Prompt 引擎 | 1-2 天 |
| 5 | **AZ 模板迁移验证** | 使用现有 AZ DOCX 模板验证填充逻辑正确性 | 1 天 |

### 5.2 中优先级（增强体验）

| # | 任务 | 说明 | 预估工时 |
|---|------|------|----------|
| 6 | **PDF 导出支持** | 集成 WeasyPrint / Playwright，支持 HTML → PDF | 2-3 天 |
| 7 | **简历结构化解析** | 使用 LLM 将简历文本解析为结构化 JSON | 2-3 天 |
| 8 | **解析结果可视化编辑** | UI 支持查看和编辑解析后的简历字段 | 2 天 |
| 9 | **评语一键重生成** | 基于用户反馈重新生成或优化评语 | 1 天 |
| 10 | **报告历史列表** | 我的报告列表、复用、搜索 | 1-2 天 |

### 5.3 低优先级（后续迭代）

| # | 任务 | 说明 | 预估工时 |
|---|------|------|----------|
| 11 | **批量处理** | 一次上传多份简历，批量生成报告 | 3-5 天 |
| 12 | **客户反馈闭环** | 客户对推荐评语的反馈，反哺 AI | 3-5 天 |
| 13 | **飞书/企业微信集成** | 机器人接入，快速生成报告 | 2-3 天 |
| 14 | **移动端适配** | 响应式布局优化 | 2-3 天 |
| 15 | **数据分析看板** | 报告生成数据、客户反馈数据分析 | 3-5 天 |

---

## 6. 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 前端 | Streamlit | 组件化、快速开发 |
| 后端 | Python 3.12 | 纯 Python，无框架依赖 |
| 配置解析 | PyYAML | YAML 配置解析 |
| 模板引擎 | Jinja2 | Prompt 模板渲染 |
| DOCX 操作 | python-docx | 模板填充和程序化构建 |
| PDF 解析 | pdfplumber | 简历文本提取 |
| LLM 调用 | requests + OpenAI/Claude API | 评语生成 |
| 部署 | Docker + Docker Compose | 容器化 |

---

## 7. 关键设计决策

### 7.1 配置驱动 vs 代码驱动
- **决策**: 采用配置驱动（YAML），新增客户无需代码变更
- **理由**: 降低运营团队依赖技术团队的程度，缩短新客户接入时间

### 7.2 模板填充 vs 程序化构建
- **决策**: 优先支持"填充客户提供的模板"模式
- **理由**: 客户（如 AZ）通常有官方品牌模板，填充模式能保证品牌一致性

### 7.3 配置继承 vs 完全复制
- **决策**: 支持配置继承（`inherits`）
- **理由**: 减少重复配置，子配置只需定义差异部分

### 7.4 Prompt 模板化 vs 硬编码
- **决策**: 使用 Jinja2 模板引擎，Prompt 完全模板化
- **理由**: 不同客户的 AI 规则差异大（如 AZ 强制英语评估），模板化支持灵活配置

---

## 8. 与现有 AZ 工具的对比

| 能力 | 现有 AZ 工具 | 新通用架构 |
|------|-------------|----------|
| 新增客户时间 | 1-2 周开发 | < 1 天配置 |
| 模板适配方式 | 硬编码行索引 | YAML 配置化映射 |
| 品牌元素 | 硬编码 | 配置化（Logo、颜色、字体） |
| 字段定义 | 硬编码 Python 字典 | YAML Schema 驱动 |
| Prompt 规则 | 硬编码字符串 | Jinja2 模板引擎 |
| 评语风格 | 固定 | 配置化（语气、长度、重点） |
| 合规声明 | 硬编码 | 配置化（免责声明、隐私规则） |
| 部署方式 | 单服务 | 容器化 + 配置热加载 |

---

## 9. 新增客户配置示例

### 步骤 1: 创建品牌配置
```bash
cp config/brands/default.yaml config/brands/roche.yaml
```

### 步骤 2: 修改配置
```yaml
brand_id: "roche_custom_v1"
brand_name: "Roche 定制版"
version: "1.0.0"
inherits: "default"

branding:
  primary_color: "#0066CC"        # 罗氏蓝
  font_family: "Source Han Sans CN"

fields:
  required:
    - field: "req_id"
      # ... 罗氏特化字段
  
  optional:
    # 覆盖 default 的 optional，只保留罗氏需要的字段
```

### 步骤 3: 验证配置
```bash
python -m core.config_loader --validate roche
```

### 步骤 4: 上线
配置自动热加载，无需重启服务。

---

## 10. 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `GENERIC_REPORT_CONFIG_DIR` | `./config` | 配置目录 |
| `GENERIC_REPORT_TEMPLATE_DIR` | `./templates` | 模板文件目录 |
| `GENERIC_REPORT_DATA_DIR` | `./data` | 数据存储目录 |
| `GENERIC_REPORT_BRIDGE_TOKEN` | — | API 认证 Token |
| `GENERIC_REPORT_PUBLIC_BASE_URL` | `http://localhost:8767` | 公共服务地址 |
| `AZ_LLM_BASE_URL` | — | LLM API 地址 |
| `AZ_LLM_MODEL` | — | LLM 模型名称 |
| `AZ_LLM_API_KEY` | — | LLM API 密钥 |

---

## 11. 附录

### 11.1 参考文件
- PRD: `/c/Users/EDY/Downloads/PRD_Resume_Referral_Report_Generator.md`
- 现有 AZ 工具: `/c/Users/EDY/.kimi/az-referral-report-tool/`
- AZ Skill 版本: `/c/Users/EDY/.kimi/skills/az-referral-report/`

### 11.2 术语表
| 术语 | 说明 |
|------|------|
| Brand | 客户品牌配置（如 AZ、强生） |
| Template Mapping | 字段到 DOCX 模板单元格的映射配置 |
| Prompt Engine | 基于 Jinja2 的 AI Prompt 模板引擎 |
| MCP | Model Context Protocol，AI 工具调用协议 |
| Render Mode | 渲染模式：text / structured / append_paragraphs |

---

*本文档为开发交接文档，供 Claude / Codex / 技术团队参考执行后续开发任务。*
