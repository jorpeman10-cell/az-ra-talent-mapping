# -*- coding: utf-8 -*-
"""
第二章 数据采集 (按谷露实际schema调整)
  表A 顾问季度回款: invoiceassignment JOIN invoice(status='Received')
  表B 顾问客户关系: client.addedBy_id == 顾问 -> SELF, 否则 COMPANY
  表C 项目明细:     invoice + offersign + joborder (成单周期/费率)
  表D 公司季度汇总: invoice 聚合 + 顾问数 + 项目数 + 平均成单周期
  表E 预算vs实际:   report_revenue_annual_target (无年份字段, 仅当前年度目标)
输出: dict of list[dict], 金额单位=万
"""
import sys
sys.path.insert(0, r"C:/Users/EDY/.kimi/advanced_analysis_publish")
from gllue_db_client import GllueDBConfig, GllueDBClient

SINCE = "2021-01-01"  # 取近5年+, 保证 >=8 个季度历史用于 beta 回归

_CONFIG = GllueDBConfig(
    db_type="mysql", host="127.0.0.1", port=3306, database="gllue",
    username="debian-sys-maint", password="IfUntY7bQZN5kDsk",
    use_ssh=True, ssh_host="118.190.96.172", ssh_port=9998,
    ssh_user="root", ssh_password="Tstar2026!")

_PAID = "i.status='Received' AND i.paymentReceivedDate IS NOT NULL" \
        " AND (i.is_credit_memo IS NULL OR i.is_credit_memo=0)"


def collect_all():
    client = GllueDBClient(_CONFIG)
    out = {}

    # ---- 顾问主档 (状态/入离职日期, 清洗用) ----
    out["advisors"] = client.query("""
        SELECT id AS advisor_id, COALESCE(chineseName, englishName, email) AS advisor_name,
               status, joinInDate, leaveDate, annualTarget
        FROM user
    """).to_dict("records")

    # ---- 表A: 顾问季度回款 ----
    out["A"] = client.query(f"""
        SELECT ia.user_id AS advisor_id,
               COALESCE(u.chineseName, u.englishName, u.email) AS advisor_name,
               YEAR(i.paymentReceivedDate) AS year, QUARTER(i.paymentReceivedDate) AS quarter,
               SUM(ia.revenue)/10000.0 AS revenue
        FROM invoiceassignment ia
        JOIN invoice i ON i.id = ia.invoice_id
        JOIN `user` u ON u.id = ia.user_id
        WHERE {_PAID} AND i.paymentReceivedDate >= '{SINCE}'
        GROUP BY ia.user_id, YEAR(i.paymentReceivedDate), QUARTER(i.paymentReceivedDate)
        ORDER BY ia.user_id, year, quarter
    """).to_dict("records")

    # ---- 表B: 顾问客户关系 (来源 = 客户创建人是否本人) ----
    out["B"] = client.query(f"""
        SELECT ia.user_id AS advisor_id, i.client_id,
               c.name AS client_name,
               CASE WHEN c.addedBy_id = ia.user_id THEN 'SELF' ELSE 'COMPANY' END AS source_type,
               MIN(i.paymentReceivedDate) AS first_deal_date,
               SUM(ia.revenue)/10000.0 AS total_revenue,
               COUNT(DISTINCT i.id) AS deal_count
        FROM invoiceassignment ia
        JOIN invoice i ON i.id = ia.invoice_id
        JOIN client c ON c.id = i.client_id
        WHERE {_PAID} AND i.paymentReceivedDate >= '{SINCE}'
        GROUP BY ia.user_id, i.client_id, c.addedBy_id, c.name
    """).to_dict("records")

    # ---- 表C: 项目明细 (成单周期=signDate-openDate, 费率) ----
    out["C"] = client.query(f"""
        SELECT ia.user_id AS advisor_id, i.joborder_id AS project_id, i.client_id,
               jo.openDate, os.signDate, os.annualSalary,
               i.contract_charge_rate AS fee_rate,
               i.paymentReceivedDate AS payment_date,
               ia.revenue/10000.0 AS payment_amount
        FROM invoiceassignment ia
        JOIN invoice i ON i.id = ia.invoice_id
        LEFT JOIN joborder jo ON jo.id = i.joborder_id
        LEFT JOIN offersign os ON os.jobsubmission_id = i.jobsubmission_id AND os.active=1
        WHERE {_PAID} AND i.paymentReceivedDate >= '{SINCE}'
    """).to_dict("records")

    # ---- 表D: 公司季度汇总 ----
    out["D"] = client.query(f"""
        SELECT YEAR(i.paymentReceivedDate) AS year, QUARTER(i.paymentReceivedDate) AS quarter,
               SUM(i.paymentReceived)/10000.0 AS total_revenue,
               COUNT(DISTINCT i.joborder_id) AS total_projects,
               (SELECT COUNT(DISTINCT ia2.user_id) FROM invoiceassignment ia2
                 JOIN invoice i2 ON i2.id = ia2.invoice_id
                WHERE i2.status='Received'
                  AND YEAR(i2.paymentReceivedDate)=YEAR(i.paymentReceivedDate)
                  AND QUARTER(i2.paymentReceivedDate)=QUARTER(i.paymentReceivedDate)
               ) AS total_advisors
        FROM invoice i
        WHERE {_PAID} AND i.paymentReceivedDate >= '{SINCE}'
        GROUP BY YEAR(i.paymentReceivedDate), QUARTER(i.paymentReceivedDate)
        ORDER BY year, quarter
    """).to_dict("records")

    # 表D补充: 每季度平均成单周期(天) 与平均费率
    try:
        cycles = client.query(f"""
            SELECT YEAR(i.paymentReceivedDate) AS year, QUARTER(i.paymentReceivedDate) AS quarter,
                   AVG(DATEDIFF(os.signDate, jo.openDate)) AS avg_cycle_days,
                   AVG(i.contract_charge_rate)*100 AS avg_fee_rate
            FROM invoice i
            JOIN joborder jo ON jo.id = i.joborder_id
            JOIN offersign os ON os.jobsubmission_id = i.jobsubmission_id AND os.active=1
            WHERE {_PAID} AND os.signDate IS NOT NULL AND jo.openDate IS NOT NULL
              AND i.paymentReceivedDate >= '{SINCE}'
            GROUP BY YEAR(i.paymentReceivedDate), QUARTER(i.paymentReceivedDate)
        """).to_dict("records")
        cyc = {(r["year"], r["quarter"]): r for r in cycles}
        for r in out["D"]:
            extra = cyc.get((r["year"], r["quarter"]), {})
            r["avg_cycle_days"] = extra.get("avg_cycle_days")
            r["avg_fee_rate"] = extra.get("avg_fee_rate")
            r["win_rate"] = None  # 谷露无直接赢单率口径, v1 留空
    except Exception as e:
        print(f"  [warn] 表D周期/费率补充查询失败: {e}")

    # ---- 表E: 年度目标 (谷露该表无年份, 作为当前年度预算) ----
    out["E_raw"] = client.query("""
        SELECT t.user_id AS advisor_id, t.target/10000.0 AS target_wan
        FROM report_revenue_annual_target t
        WHERE t.target > 0
    """).to_dict("records")

    # ---- 表F: 在途签约管道 (Accepted offer 按签约口径, v3 有效基数修正项) ----
    # signed_12m: 近12个月签约额(万), 作为年化产能的另一估计量(解决回款滞后低估)
    # collection_prob: 历史回款率 = 已回款单数 / (已回款 + 超9个月未开票疑似坏账)
    # 防呆: 1) invoice 先按 jobsubmission 去重(一对多会导致签约额重复计数)
    #       2) 单笔签约 >100万 视为录入异常, 截断并计数(outlier_cnt 供人工复核)
    out["F"] = client.query("""
        SELECT os.user_id AS advisor_id,
               SUM(CASE WHEN os.signDate >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                        THEN LEAST(os.revenue, 1000000) ELSE 0 END)/10000.0 AS signed_12m_wan,
               SUM(CASE WHEN os.revenue > 1000000 THEN 1 ELSE 0 END) AS outlier_cnt,
               SUM(inv.any_received) AS received_cnt,
               SUM(CASE WHEN inv.any_invoice IS NULL
                         AND os.signDate < DATE_SUB(CURDATE(), INTERVAL 9 MONTH)
                        THEN 1 ELSE 0 END) AS stale_unpaid_cnt,
               SUM(CASE WHEN inv.any_invoice = 1 AND inv.any_received = 0
                         AND os.signDate >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                        THEN LEAST(os.revenue, 1000000) ELSE 0 END)/10000.0 AS invoiced_unpaid_12m_wan,
               SUM(CASE WHEN inv.any_invoice IS NULL
                         AND os.signDate >= DATE_SUB(CURDATE(), INTERVAL 9 MONTH)
                        THEN LEAST(os.revenue, 1000000) ELSE 0 END)/10000.0 AS uninvoiced_recent_wan
        FROM offersign os
        LEFT JOIN (
            SELECT jobsubmission_id,
                   MAX(CASE WHEN status='Received' THEN 1 ELSE 0 END) AS any_received,
                   1 AS any_invoice
            FROM invoice WHERE active=1 GROUP BY jobsubmission_id
        ) inv ON inv.jobsubmission_id = os.jobsubmission_id
        WHERE os.active=1 AND os.offerStatus='Accepted' AND os.signDate >= '2023-01-01'
        GROUP BY os.user_id
    """).to_dict("records")

    return out
