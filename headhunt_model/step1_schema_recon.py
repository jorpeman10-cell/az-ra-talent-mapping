# -*- coding: utf-8 -*-
"""第八章 表结构调研: SHOW TABLES + DESCRIBE 关键表"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:/Users/EDY/.kimi/advanced_analysis_publish")
from gllue_db_client import GllueDBConfig, GllueDBClient

config = GllueDBConfig(
    db_type="mysql", host="127.0.0.1", port=3306, database="gllue",
    username="debian-sys-maint", password="IfUntY7bQZN5kDsk",
    use_ssh=True, ssh_host="118.190.96.172", ssh_port=9998,
    ssh_user="root", ssh_password="Tstar2026!",
)
client = GllueDBClient(config)

# 1. SHOW TABLES
tables_df = client.query("SHOW TABLES")
tables = tables_df.iloc[:, 0].tolist()
print(f"=== 共 {len(tables)} 张表 ===")
for t in tables:
    print(" ", t)

# 2. 按关键词筛选可能相关的表
KEYWORDS = ["user", "advisor", "consultant", "employee",
            "project", "job", "case", "order",
            "payment", "invoice", "revenue", "performance", "achievement", "forecast", "offer",
            "client", "company", "customer",
            "budget", "target", "kpi"]
hit = sorted({t for t in tables for k in KEYWORDS if k in t.lower()})
print(f"\n=== 关键词命中 {len(hit)} 张表 ===")
for t in hit:
    print(" ", t)

# 3. DESCRIBE 重点表 + 行数
report = {}
for t in hit:
    try:
        desc = client.query(f"DESCRIBE `{t}`")
        cnt = client.query(f"SELECT COUNT(*) AS c FROM `{t}`").iloc[0, 0]
        report[t] = {"row_count": int(cnt),
                     "columns": desc.to_dict("records")}
        print(f"\n--- {t} ({cnt} rows) ---")
        print(desc[["Field", "Type", "Null", "Key"]].to_string(index=False))
    except Exception as e:
        print(f"\n--- {t} DESCRIBE失败: {e}")

with open(r"C:/Users/EDY/Documents/kimi/workspace/headhunt_model/schema_report.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1, default=str)
print("\n报告已保存 schema_report.json")
