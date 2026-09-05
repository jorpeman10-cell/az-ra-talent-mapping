# -*- coding: utf-8 -*-
"""headhunt-service 部署到 hiijob-prod (139.129.192.85:9998)
纯增量: 只新增 headhunt-svc / headhunt-mcp 两个容器, 不动既有服务.
用法: py -3 deploy_headhunt.py [check|upload|up|verify|all]
"""
import base64
import io
import json
import sys
import tarfile
import time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parent          # headhunt-service/
CONFIG_FILE = Path(r"C:/Users/EDY/.kimi/advanced_analysis_publish/config/db_config.json")
REMOTE_DIR = "/root/headhunt-service"


def _decode(v):
    try:
        return base64.b64decode(v).decode()
    except Exception:
        return v


def connect():
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(cfg.get("ssh_host", "139.129.192.85"), port=int(cfg.get("ssh_port", 9998)),
              username=cfg.get("ssh_user", "root"), password=_decode(cfg["ssh_password"]),
              timeout=30, banner_timeout=60, auth_timeout=30)
    return c


def run(client, cmd, check=True, timeout=600):
    _, out, err = client.exec_command(cmd, timeout=timeout)
    o, e = out.read().decode("utf-8", "replace"), err.read().decode("utf-8", "replace")
    code = out.channel.recv_exit_status()
    print(f"\n$ {cmd}\n{o}{e}", flush=True)
    if check and code:
        raise RuntimeError(f"failed({code}): {cmd}")
    return code, o, e


def make_tar():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in ROOT.rglob("*"):
            rel = p.relative_to(ROOT).as_posix()
            if any(s in rel for s in ("__pycache__", ".pytest_cache")):
                continue
            if p.is_file():
                tar.add(p, arcname=rel)
    buf.seek(0)
    return buf


def check(client):
    run(client, "docker ps --format '{{.Names}} {{.Status}}' | head -30")
    run(client, "df -h / | tail -1 && free -m | head -2")
    run(client, "ss -tlnp | grep -E '18801|18802' || echo 'ports 18801/18802 free'")


def upload(client):
    run(client, f"mkdir -p {REMOTE_DIR}")
    buf = make_tar()
    sftp = client.open_sftp()
    with sftp.file(f"{REMOTE_DIR}/headhunt-service.tar.gz", "wb") as f:
        while True:
            chunk = buf.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    sftp.close()
    run(client, f"cd {REMOTE_DIR} && tar xzf headhunt-service.tar.gz && rm headhunt-service.tar.gz && ls")


def up(client):
    run(client, f"cd {REMOTE_DIR} && docker build -t headhunt-svc:local . 2>&1 | tail -5", timeout=1800)
    # 独立起两个容器(不并入主 compose, 零侵入)
    run(client, "docker rm -f headhunt-svc headhunt-mcp 2>/dev/null || true")
    # 2026-09-05: 必须并入 lobe-network——federation 网关经 HEADHUNT_API=http://headhunt-svc:18801
    # 在该网络内按容器名访问; 脱离该网络网关全部 headhunt 能力会断
    run(client, f"docker run -d --name headhunt-svc --restart unless-stopped "
                f"--network lobehubaliyundeploy_lobe-network "
                f"-p 18801:18801 --env-file {REMOTE_DIR}/config/.env "
                f"-v {REMOTE_DIR}/data:/app/data -v {REMOTE_DIR}/config:/app/config "
                f"headhunt-svc:local")
    run(client, f"docker run -d --name headhunt-mcp --restart unless-stopped "
                f"--network lobehubaliyundeploy_lobe-network "
                f"-p 18802:18802 --env-file {REMOTE_DIR}/config/.env "
                f"-v {REMOTE_DIR}/data:/app/data -v {REMOTE_DIR}/config:/app/config "
                f"headhunt-svc:local python -m mcp_ext.server")


def verify(client):
    time.sleep(8)
    run(client, "docker ps --filter name=headhunt --format '{{.Names}} {{.Status}}'")
    run(client, "curl -sf http://127.0.0.1:18801/api/board -o /tmp/board_smoke.json && "
                "head -c 300 /tmp/board_smoke.json || { echo 'BOARD SMOKE FAILED'; exit 1; }")
    run(client, "curl -sf -X POST http://127.0.0.1:18801/api/candidate/intake "
                "-H 'Content-Type: application/json' -d '{\"name\":\"deploy-smoke\"}' "
                "-o /tmp/intake_smoke.json && grep -o '\"self_url\"' /tmp/intake_smoke.json")
    # clean up the smoke candidate so verify() never pollutes the archive
    run(client, "SMOKE_CID=$(grep -o '\"cid\":\"[^\"]*\"' /tmp/intake_smoke.json | cut -d'\"' -f4); "
                "rm -rf /root/headhunt-service/data/candidates/$SMOKE_CID "
                "&& echo \"smoke candidate $SMOKE_CID removed\"")
    run(client, "curl -s -X POST http://127.0.0.1:18802/mcp -H 'Content-Type: application/json' "
                "-H 'Accept: application/json, text/event-stream' "
                "-d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}' "
                "-o /tmp/mcp_smoke.txt && head -c 500 /tmp/mcp_smoke.txt || { echo 'MCP SMOKE FAILED'; exit 1; }")
    run(client, "docker ps --format '{{.Names}} {{.RestartCount}}' | grep -v headhunt | awk '$2>0{c++} END{print \"non-headhunt containers with restarts:\", c+0}'")


if __name__ == "__main__":
    steps = sys.argv[1:] or ["all"]
    client = connect()
    try:
        if "all" in steps or "check" in steps:
            check(client)
        if "all" in steps or "upload" in steps:
            upload(client)
        if "all" in steps or "up" in steps:
            up(client)
        if "all" in steps or "verify" in steps:
            verify(client)
    finally:
        client.close()
