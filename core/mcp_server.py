"""
MCP 服务协议实现 - 支持 tools/list, tools/call, initialize
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .config_loader import get_loader
from .parser import extract_resume_text
from .redactor import privacy_redact, get_default_rules
from .renderer import ReportRenderer
from .validator import DataValidator


class MCPServerHandler(BaseHTTPRequestHandler):
    """MCP 协议处理器"""

    def __init__(self, config_dir: str | Path | None = None, *args, **kwargs):
        self.config_dir = config_dir
        super().__init__(*args, **kwargs)

    def do_POST(self) -> None:
        """处理 POST 请求"""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            message = json.loads(body)
        except json.JSONDecodeError:
            self._send_json_response({"error": "Invalid JSON"}, 400)
            return

        path = self.path

        if path == "/mcp":
            self._handle_mcp_message(message)
        elif path == "/draft":
            self._handle_draft(message)
        elif path == "/generate-report":
            self._handle_generate_report(message)
        else:
            self._send_json_response({"error": "Unknown endpoint"}, 404)

    def do_GET(self) -> None:
        """处理 GET 请求"""
        if self.path == "/mcp":
            # MCP 初始化或工具列表
            self._send_json_response({"status": "MCP server ready"})
        else:
            self._send_json_response({"error": "Unknown endpoint"}, 404)

    # ============================================================
    # MCP 协议处理
    # ============================================================

    def _handle_mcp_message(self, message: dict[str, Any]) -> None:
        """处理 MCP JSON-RPC 消息"""
        method = message.get("method")
        params = message.get("params", {})

        if method == "initialize":
            self._send_json_response({
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "generic-report-tool",
                        "version": "1.0.0",
                    }
                }
            })
        elif method == "tools/list":
            self._send_json_response({
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": {
                    "tools": self._get_tools()
                }
            })
        elif method == "tools/call":
            self._handle_tool_call(message)
        else:
            self._send_json_response({
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }, 400)

    def _get_tools(self) -> list[dict[str, Any]]:
        """获取可用工具列表"""
        loader = get_loader(self.config_dir)
        brands = loader.list_brands()

        tools = []
        for brand in brands:
            brand_id = brand["brand_id"]
            brand_name = brand["brand_name"]
            tools.append({
                "name": f"generate_{brand_id}_report",
                "description": f"Generate {brand_name} candidate referral report",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string"},
                        "position_title": {"type": "string"},
                        "resume_text": {"type": "string"},
                        "motivation": {"type": "string"},
                        "recommendation_rationale": {"type": "object"},
                        "opportunity_to_improve": {"type": "string"},
                        "role_fit": {"type": "string"},
                    },
                    "required": ["candidate_name", "position_title", "resume_text"],
                }
            })

        return tools

    def _handle_tool_call(self, message: dict[str, Any]) -> None:
        """处理工具调用"""
        params = message.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # 从工具名提取 brand_id
        # 格式: generate_{brand_id}_report
        if tool_name.startswith("generate_") and tool_name.endswith("_report"):
            brand_id = tool_name[len("generate_"):-len("_report")]
        else:
            self._send_json_response({
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}
            }, 400)
            return

        # 生成报告
        try:
            result = self._generate_report(brand_id, arguments)
            self._send_json_response({
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                }
            })
        except Exception as e:
            self._send_json_response({
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32603, "message": f"Report generation failed: {str(e)}"}
            }, 500)

    # ============================================================
    # 业务逻辑处理
    # ============================================================

    def _handle_draft(self, data: dict[str, Any]) -> None:
        """处理草稿请求"""
        # 转发到本地编辑器或返回 JSON
        self._send_json_response({
            "status": "draft_received",
            "data": data,
        })

    def _handle_generate_report(self, data: dict[str, Any]) -> None:
        """处理生成报告请求"""
        brand_id = data.get("brand_id", "default")

        try:
            result = self._generate_report(brand_id, data)
            self._send_json_response(result)
        except Exception as e:
            self._send_json_response({"error": str(e)}, 500)

    def _generate_report(self, brand_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """生成报告"""
        # 加载配置
        loader = get_loader(self.config_dir)
        brand_config = loader.load_brand(brand_id)

        # 加载模板配置（如果有）
        template_config = None
        template_mapping = brand_config.get("template_mapping", {})
        if template_mapping.get("use_client_template"):
            template_id = f"{brand_id}_referral_report"
            try:
                template_config = loader.load_template(template_id)
            except FileNotFoundError:
                pass

        # 脱敏
        resume_text = data.get("original_resume", "")
        privacy_rules = brand_config.get("compliance", {}).get("privacy_rules")
        if resume_text and privacy_rules:
            data["original_resume"] = privacy_redact(resume_text, privacy_rules)

        # 校验数据
        validator = DataValidator(brand_config)
        validation = validator.validate(data)

        # 准备草稿 payload（如果有缺失字段）
        if not validation.is_valid:
            data = validator.prepare_draft_payload(data)

        # 渲染报告
        renderer = ReportRenderer(brand_config, template_config)

        # 生成文件名
        export_config = brand_config.get("export", {})
        filename_template = export_config.get("filename_template", "{brand_id}_{candidate_name}_report_{date}")
        from datetime import datetime
        filename = filename_template.format(
            brand_id=brand_id,
            brand_name=brand_config.get("brand_name", brand_id),
            candidate_name=data.get("candidate_name", "unknown"),
            date=datetime.now().strftime("%Y%m%d"),
        )

        # 确定输出格式
        default_format = export_config.get("default_format", "pdf")
        output_path = Path("/tmp") / f"{filename}.{default_format}"

        # 渲染
        renderer.render(data, output_path)

        # 构建响应
        public_base_url = os.environ.get("GENERIC_REPORT_PUBLIC_BASE_URL", "http://localhost:8767")
        download_url = f"{public_base_url}/download/{output_path.name}"

        return {
            "download_url": download_url,
            "filename": output_path.name,
            "status": "draft" if not validation.is_valid else "confirmed",
            "missing_information": validation.to_dict()["missing_items"] if not validation.is_valid else [],
        }

    # ============================================================
    # 辅助方法
    # ============================================================

    def _send_json_response(self, data: dict[str, Any], status_code: int = 200) -> None:
        """发送 JSON 响应"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        """重写日志方法，减少输出"""
        pass


def run_server(host: str = "0.0.0.0", port: int = 8767, config_dir: str | Path | None = None) -> None:
    """运行 MCP HTTP 服务"""
    # 使用闭包传递 config_dir
    class Handler(MCPServerHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(config_dir, *args, **kwargs)

    server = HTTPServer((host, port), Handler)
    print(f"MCP Server running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


# 便捷函数
__all__ = ["MCPServerHandler", "run_server"]
