# 猎头用工决策引擎服务 (headhunt-service)

确定性计算服务：谷露数据采集 → 清洗 → 产能画像 → 雇员/孵化双模式财务测算 → 决策看板。
**无 LLM 参与计算**，输出可复现、可审计。

## 快速开始（本地）

```bash
cd headhunt-service
cp config/.env.example config/.env   # 填入谷露 DB/SSH 凭据
pip install -r requirements.txt
python -m jobs.daily_sync            # 首次全量采集+重算（或复用 data/raw_cache.json）
uvicorn api.main:app --host 0.0.0.0 --port 18801
```

打开 http://127.0.0.1:18801 查看板。

## API

| 端点 | 说明 |
|---|---|
| `GET /api/board` | 排名看板（决策分布、市场阶段、排名分） |
| `GET /api/advisor/{id}` | 单顾问决策详情（画像/产能/双模式 NPV/IRR/季度历史） |
| `GET /api/advisor/{id}/salary_scan?scenario=A\|B\|C` | 调薪扫描：EMPLOY 极限月薪 + 盈亏平衡月薪 + NPV 曲线 |
| `GET /api/config` / `POST /api/config` | 参数读取/修改（浅合并，改后自动重跑） |
| `POST /api/rerun?fresh=true` | 手动重算；fresh=true 重新采集谷露 |

## 目录

- `pipeline/` 采集(collect) → 清洗(cleaning) → 引擎(engine) → 财务(finance, 勿改公式) → 入口(run)
- `config/config.yaml` 全部业务参数；`config/.env` 凭据（不入库）
- `data/` raw_cache、薪资表、成本表、输出、日志
- `tests/test_golden.py` 黄金样本回归（引擎改动后必须 `pytest` 全绿）
- `Dockerfile` + `docker-compose.fragment.yml` 服务器部署用

## 口径速查

- 产能基数 = max（近4Q/8Q回款均值×4, 近12月签约×回款率）
- CV = min（回款CV, 面试CV）；β 收缩 = 1+(β−1)×R²；波动惩罚不含 β
- 提成 = 税后回款×0.936×阶梯 − 已发底薪（2023 薪酬制度公式）
- 公摊按人头均摊（成本拆分 xlsx），社保率实算
- 现金流按季度滚动，IRR 按季年化；门槛：Y1 利润率≥15% 且 IRR≥20%
- 市场斜率默认公司口径，config `market.external_slope` 可切外部行业口径（医药赛道建议 -0.05）

## MCP 接入（Agent 调用）

服务自带 MCP server（`mcp_ext/server.py`，streamable-http，端口 18802），4 个工具：

| 工具 | 用途 |
|---|---|
| `headhunt_board()` | 排名看板：市场阶段、决策分布、全员排名 |
| `headhunt_advisor_decision(name_or_id)` | 单顾问决策 + `rationale` 逐条判断依据（支持姓名模糊查找） |
| `headhunt_salary_scan(name_or_id, scenario)` | 调薪幅度测算 + 极限/平衡月薪 + 依据（A 公司口径 / B 外部 -0.05 / C 乐观） |
| `headhunt_rerun(fresh)` | 重跑管线（管理员） |

Agent 直接问"于肖肖的调薪幅度"即可获得计算结果+判断依据（已实测验证）。

**接入方式二选一**：
1. 独立注册：`.mcp.json` 加 `"headhunt-decision": {"type":"http","url":"http://<host>:18802/mcp"}`（本机已注册）
2. 并入 hiijob 网关：`gateway_patch/headhunt_tools.py` 的 3 个函数粘进 `federation_gateway/mcp_server.py`，装饰器换成网关的 `mcp` 实例；工具内部 HTTP 调 headhunt-svc，地址用 `HEADHUNT_API` 环境变量覆盖

## 部署到 hiijob pro 服务器

```bash
# 1. headhunt-service/ 整目录上传 hiijob pro（与 federation_gateway 同级）
# 2. docker-compose.fragment.yml 并入主 docker-compose.yml（两个服务: API + MCP）
# 3. config/.env 填谷露凭据；保留 GLLUE_SSH_HOST=118.190.96.172（容器内经 SSH 隧道连谷露库）
docker compose up -d headhunt-svc headhunt-mcp
# 4. 每日跑批 cron:
# 30 6 * * * docker exec headhunt-svc python -m jobs.daily_sync
# 5. 网关侧: 按 gateway_patch/headhunt_tools.py 注册工具, 或网关配置里加 MCP 下游 http://headhunt-mcp:18802/mcp
```
