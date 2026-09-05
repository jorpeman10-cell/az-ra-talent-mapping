FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline/ pipeline/
COPY api/ api/
COPY web/ web/
COPY jobs/ jobs/
COPY tests/ tests/
COPY mcp_ext/ mcp_ext/
COPY config/config.yaml config/config.yaml
# config/.env 与 data/ 通过 volume/环境变量注入, 不打入镜像

EXPOSE 18801
# 每日 06:30 跑批由宿主机 cron 调用: docker exec headhunt-svc python -m jobs.daily_sync
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "18801"]
