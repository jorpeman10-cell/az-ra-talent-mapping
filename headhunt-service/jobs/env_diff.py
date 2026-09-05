# 对比两个容器的 printenv, 找出"都存在但值不同"和"worker有而api缺"的键(值只给哈希)
import hashlib
import subprocess
import sys


def env_of(container):
    out = subprocess.run(["docker", "exec", container, "printenv"],
                         capture_output=True, text=True).stdout
    d = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v
    return d


def h(v):
    return hashlib.md5(v.encode()).hexdigest()[:8]


a = env_of("hiijob-federation-api")
w = env_of("hiijob-report-index-worker")
conflicts = [(k, h(a[k]), h(w[k])) for k in a if k in w and a[k] != w[k]]
missing = [k for k in w if k not in a]
print("CONFLICTS:", conflicts)
print("MISSING_IN_API:", missing)
