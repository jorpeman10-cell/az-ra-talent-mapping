# 读取生产 runtime config 现状(flags/allowlists)与用户表
import os
import sys
import sqlite3
sys.path.insert(0, "/app")
from runtime_config_service import get_runtime_config

rc = get_runtime_config()
print("FLAGS:", rc.get("capability.flags"))
print("ALLOWLISTS:", rc.get("capability.allowlists"))

db = os.environ.get("FEDERATION_DATA_DIR", "/app/data") + "/federation.db"
con = sqlite3.connect(db)
tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
print("TABLES:", tables)
for t in ("users", "enterprise_users", "user", "accounts"):
    if t in tables:
        cols = [c[1] for c in con.execute(f"pragma table_info({t})")]
        print(f"COLS[{t}]:", cols[:10])
        try:
            rows = list(con.execute(f"select * from {t} limit 50"))
            for r in rows:
                line = " | ".join(str(x)[:40] for x in r)
                if "steven" in line.lower() or "Steven" in line:
                    print("STEVEN_ROW:", line)
        except Exception as e:
            print("err", t, e)
