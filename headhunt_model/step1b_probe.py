# -*- coding: utf-8 -*-
"""补充探查: 状态枚举/币种/客户来源字段, 为 step2 SQL 定稿"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:/Users/EDY/.kimi/advanced_analysis_publish")
from gllue_db_client import GllueDBConfig, GllueDBClient

config = GllueDBConfig(
    db_type="mysql", host="127.0.0.1", port=3306, database="gllue",
    username="debian-sys-maint", password="IfUntY7bQZN5kDsk",
    use_ssh=True, ssh_host="118.190.96.172", ssh_port=9998,
    ssh_user="root", ssh_password="Tstar2026!")
client = GllueDBClient(config)

def q(label, sql):
    print(f"\n### {label}")
    try:
        print(client.query(sql).to_string(index=False))
    except Exception as e:
        print("ERR:", e)

q("user.status 分布", "SELECT status, COUNT(*) c FROM user GROUP BY status ORDER BY c DESC")
q("user.user_type 分布", "SELECT user_type, COUNT(*) c FROM user GROUP BY user_type ORDER BY c DESC")
q("在职顾问数", "SELECT COUNT(*) c FROM user WHERE status='active'")
q("invoice.status 分布", "SELECT status, COUNT(*) c, SUM(paymentReceived)/10000 paid_wan FROM invoice GROUP BY status")
q("invoice 年度分布(已回款)", """SELECT YEAR(paymentReceivedDate) y, COUNT(*) c, SUM(paymentReceived)/10000 wan
  FROM invoice WHERE paymentReceivedDate IS NOT NULL GROUP BY y ORDER BY y""")
q("invoice is_credit_memo", "SELECT is_credit_memo, COUNT(*) c FROM invoice GROUP BY is_credit_memo")
q("invoiceassignment revenue vs unified", """SELECT COUNT(*) c,
  SUM(revenue)/10000 rev_wan, SUM(unified_revenue)/10000 uni_wan,
  SUM(CASE WHEN unified_revenue IS NULL THEN 1 ELSE 0 END) uni_null
  FROM invoiceassignment""")
q("invoiceassignment 汇率版本分布", """SELECT unified_revenue_exchange_rate_version_id v, COUNT(*) c
  FROM invoiceassignment GROUP BY v ORDER BY c DESC LIMIT 5""")
q("invoiceassignment assignment_role", "SELECT assignment_role, COUNT(*) c FROM invoiceassignment GROUP BY assignment_role ORDER BY c DESC")
q("invoiceassignment 年度分布", """SELECT YEAR(i.paymentReceivedDate) y, COUNT(*) c, SUM(ia.unified_revenue)/10000 wan
  FROM invoiceassignment ia JOIN invoice i ON i.id=ia.invoice_id
  WHERE i.paymentReceivedDate IS NOT NULL GROUP BY y ORDER BY y""")
q("report_revenue_annual_target.view 值", "SELECT view, COUNT(*) c FROM report_revenue_annual_target GROUP BY view")
q("annual_target 样本", "SELECT * FROM report_revenue_annual_target LIMIT 8")
q("user.annualTarget 非空", "SELECT COUNT(*) c FROM user WHERE annualTarget IS NOT NULL AND annualTarget>0")
q("client 关键来源字段", """SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA='gllue' AND TABLE_NAME='client'
  AND (COLUMN_NAME LIKE '%source%' OR COLUMN_NAME LIKE '%addedBy%' OR COLUMN_NAME LIKE '%owner%'
       OR COLUMN_NAME LIKE '%develop%' OR COLUMN_NAME LIKE '%channel%')""")
q("client addedBy 覆盖", "SELECT COUNT(*) total, COUNT(addedBy_id) with_adder FROM client")
q("joborder 费率/状态字段", """SELECT COLUMN_NAME FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA='gllue' AND TABLE_NAME='joborder'
  AND (COLUMN_NAME LIKE '%fee%' OR COLUMN_NAME LIKE '%rate%' OR COLUMN_NAME LIKE '%status%'
       OR COLUMN_NAME LIKE '%date%' OR COLUMN_NAME LIKE '%client%')""")
q("joborderstatuschangerecord 样本", "SELECT * FROM joborderstatuschangerecord LIMIT 5")
q("offersign offerStatus 分布", "SELECT offerStatus, COUNT(*) c FROM offersign GROUP BY offerStatus ORDER BY c DESC")
q("offersign 年度分布(signDate)", """SELECT YEAR(signDate) y, COUNT(*) c, SUM(revenue)/10000 wan
  FROM offersign WHERE signDate IS NOT NULL AND active=1 GROUP BY y ORDER BY y""")
