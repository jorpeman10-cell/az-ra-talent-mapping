# Generic Report Tool

可配置、可扩展的通用候选人推荐报告生成引擎。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行 Streamlit UI
python -m streamlit run ui/streamlit_app.py --server.port=8505

# 运行 API 服务
python api/bridge.py --host 0.0.0.0 --port 8767
```

## 项目结构

```
generic-report-tool/
├── config/                    # 配置文件（品牌、模板、Prompt）
│   ├── brands/               # 品牌配置
│   ├── templates/            # 模板映射配置
│   └── prompts/              # Prompt 引擎配置
├── core/                     # 核心引擎
│   ├── __init__.py
│   ├── config_loader.py      # 配置加载器
│   ├── parser.py             # 简历解析
│   ├── redactor.py           # 隐私脱敏
│   ├── validator.py          # 数据校验
│   ├── renderer.py           # DOCX 渲染引擎
│   ├── prompt_engine.py      # Prompt 模板引擎
│   └── mcp_server.py         # MCP 服务协议
├── templates/                # 客户提供的 DOCX 模板
│   ├── az/
│   └── generic/
├── ui/                       # Streamlit 前端
│   └── streamlit_app.py
├── api/                      # HTTP API 服务
│   └── bridge.py
├── tests/                    # 测试
│   └── test_smoke.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 新增客户配置

1. 复制 `config/brands/default.yaml` → `config/brands/{client}.yaml`
2. 修改品牌专属字段（名称、Logo、颜色、字段定义等）
3. （可选）创建模板映射配置 `config/templates/{client}_report.yaml`
4. 运行验证：`python -m core.config_loader --validate {client}`

## 技术栈

- Python 3.12+
- python-docx (DOCX 操作)
- pdfplumber (PDF 解析)
- PyYAML (配置解析)
- Jinja2 (Prompt 模板)
- Streamlit (UI)
