# 用法: logdig.py <logfile> <marker> [before]
# 打印最后一个 marker 命中行之前的 before 行 + 该行
import sys

path, marker = sys.argv[1], sys.argv[2]
before = int(sys.argv[3]) if len(sys.argv) > 3 else 30
lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
idx = max((i for i, l in enumerate(lines) if marker in l), default=-1)
if idx < 0:
    print(f"marker not found: {marker} (total {len(lines)} lines)")
else:
    for l in lines[max(0, idx - before): idx + 1]:
        print(l[:260])
