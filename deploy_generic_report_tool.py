from __future__ import annotations

import posixpath
import sys
import time
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parent
REMOTE_DIR = "/root/generic-report-tool"
NETWORK = "host"
CONTAINER = "hiijob-generic-report-tool"
IMAGE = "generic-report-tool:latest"
SSH_HOST = "139.129.192.85"
SSH_PORT = 9998
SSH_USER = "root"
SSH_KEY = Path(r"C:\Users\EDY\.ssh\Hiijob.pem")
PUBLIC_BASE_URL = "https://lobe.hiijob.cn/generic-report-tool"

EXCLUDE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "data",
    "docs",
    "tests",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log"}


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        SSH_HOST,
        port=SSH_PORT,
        username=SSH_USER,
        key_filename=str(SSH_KEY),
        timeout=30,
        banner_timeout=60,
        auth_timeout=30,
    )
    return client


def run(
    client: paramiko.SSHClient, command: str, check: bool = True
) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(command)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    sys.stdout.buffer.write(f"\n$ {command}\n{out}".encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()
    if err:
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
        sys.stderr.buffer.flush()
    if check and code:
        raise RuntimeError(f"Remote command failed ({code}): {command}")
    return code, out, err


def mkdirs(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    current = ""
    for part in remote_dir.strip("/").split("/"):
        current += "/" + part
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in relative.parts):
            continue
        if path.suffix in EXCLUDE_SUFFIXES:
            continue
        files.append(relative)
    return sorted(files)


def upload(client: paramiko.SSHClient) -> None:
    files = iter_files()
    sftp = client.open_sftp()
    try:
        for relative in files:
            remote = posixpath.join(REMOTE_DIR, relative.as_posix())
            mkdirs(sftp, posixpath.dirname(remote))
            sftp.put(str(ROOT / relative), remote)
            print(f"uploaded {relative.as_posix()}")
    finally:
        sftp.close()


def install_nginx(client: paramiko.SSHClient) -> None:
    _, out, _ = run(
        client,
        "find /etc/nginx/sites-enabled /etc/nginx/conf.d -maxdepth 1 -type f "
        "! -name '*.disabled' ! -name '*.bak*' -exec grep -l "
        "'server_name lobe.hiijob.cn' {} + 2>/dev/null | head -1",
    )
    config = out.strip()
    if not config:
        raise RuntimeError("Could not find active lobe.hiijob.cn nginx config")

    marker = "location ^~ /generic-report-tool/"

    snippet = """
    location ^~ /generic-report-tool/ {
        proxy_pass http://127.0.0.1:8810/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
"""
    encoded = snippet.encode("utf-8").hex()
    installer = f"""
from pathlib import Path

p = Path({config!r})
s = p.read_text()
server_marker = "server {{\\n    listen 443 ssl;\\n    server_name lobe.hiijob.cn;"
marker = {marker!r}
start = s.find(server_marker)
assert start >= 0, "lobe.hiijob.cn ssl server block not found"
end = s.find("\\nserver {{", start + 1)
if end < 0:
    end = len(s)
block = s[start:end]
if marker not in block:
    insert = s.find("\\n    location / {{", start, end)
    assert insert >= 0, "fallback location not found in lobe.hiijob.cn server block"
    snippet = bytes.fromhex({encoded!r}).decode()
    p.write_text(s[:insert] + snippet + s[insert:])
else:
    print("nginx route already present in active lobe.hiijob.cn server block")
"""
    encoded_installer = installer.encode("utf-8").hex()
    command = (
        f"backup='{config}.bak-generic-report-'$(date +%Y%m%d%H%M%S) && "
        f"cp '{config}' \"$backup\" && "
        f"python3 -c \"exec(bytes.fromhex('{encoded_installer}').decode())\" && "
        "nginx -t && (systemctl reload nginx || nginx -s reload)"
    )
    run(client, command)


def deploy() -> None:
    client = connect()
    try:
        run(client, f"mkdir -p {REMOTE_DIR}/data")
        upload(client)
        run(client, f"cd {REMOTE_DIR} && docker build -t {IMAGE} .")
        run(client, f"docker rm -f {CONTAINER} 2>/dev/null || true", check=False)
        network_args = "--network host" if NETWORK == "host" else f"--network {NETWORK} -p 127.0.0.1:8810:8810"
        run(
            client,
            "docker run -d "
            f"--name {CONTAINER} --restart unless-stopped "
            f"{network_args} "
            f"-v {REMOTE_DIR}/data:/app/data "
            "-e GENERIC_REPORT_CONFIG_DIR=/app/config "
            "-e GENERIC_REPORT_TEMPLATE_DIR=/app/templates "
            "-e GENERIC_REPORT_DATA_DIR=/app/data "
            f"-e GENERIC_REPORT_PUBLIC_BASE_URL={PUBLIC_BASE_URL} "
            f"{IMAGE}",
        )
        install_nginx(client)
        verify(client)
        print("\nDEPLOYED")
        print(f"Service: {PUBLIC_BASE_URL}/health")
    finally:
        client.close()


def verify(client: paramiko.SSHClient) -> None:
    run(
        client,
        f"docker ps --filter name={CONTAINER} "
        "--format 'table {{.Names}}\\t{{.Status}}\\t{{.Networks}}\\t{{.Ports}}'",
    )
    run(client, "curl -fsS http://127.0.0.1:8810/health")
    run(client, f"curl -fsS {PUBLIC_BASE_URL}/health")
    run(
        client,
        "python3 - <<'PY'\n"
        "import json, urllib.request\n"
        "body=json.dumps({'candidate_name':'Deploy Smoke','position_title':'Consultant'}).encode()\n"
        "req=urllib.request.Request('http://127.0.0.1:8810/api/v1/reports/draft', data=body, headers={'Content-Type':'application/json'}, method='POST')\n"
        "print(urllib.request.urlopen(req, timeout=10).read().decode())\n"
        "PY",
    )


def inspect() -> None:
    client = connect()
    try:
        run(client, "hostname && date")
        verify(client)
    finally:
        client.close()


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "deploy"
    started = time.time()
    if action == "deploy":
        deploy()
    elif action == "inspect":
        inspect()
    else:
        raise SystemExit("Usage: python deploy_generic_report_tool.py [deploy|inspect]")
    print(f"elapsed={time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
