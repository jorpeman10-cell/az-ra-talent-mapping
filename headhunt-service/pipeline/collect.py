# -*- coding: utf-8 -*-
"""谷露数据采集 (表A-F + 顾问主档). 凭据全部走环境变量, 见 config/.env.example"""
import os
import pandas as pd
from sqlalchemy import create_engine


def _engine():
    """GLLUE_SSH_HOST 非空时经 SSH 隧道连接, 否则(服务器内网)直连"""
    host = os.environ.get("GLLUE_DB_HOST", "127.0.0.1")
    port = int(os.environ.get("GLLUE_DB_PORT", "3306"))
    tunnel = None
    ssh_host = os.environ.get("GLLUE_SSH_HOST")
    if ssh_host:
        from sshtunnel import SSHTunnelForwarder
        fwd = SSHTunnelForwarder(
            (ssh_host, int(os.environ.get("GLLUE_SSH_PORT", "22"))),
            ssh_username=os.environ.get("GLLUE_SSH_USER", "root"),
            ssh_password=os.environ["GLLUE_SSH_PASSWORD"],
            remote_bind_address=(host, port))
        fwd.start()
        tunnel = fwd
        host, port = "127.0.0.1", fwd.local_bind_port
    url = f"mysql+pymysql://{os.environ['GLLUE_DB_USER']}:{os.environ['GLLUE_DB_PASSWORD']}@{host}:{port}/{os.environ.get('GLLUE_DB_NAME', 'gllue')}?charset=utf8mb4"
    return create_engine(url), tunnel


_PAID = "i.status='Received' AND i.paymentReceivedDate IS NOT NULL" \
        " AND (i.is_credit_memo IS NULL OR i.is_credit_memo=0)"


def _q(engine, sql):
    return pd.read_sql(sql, engine).to_dict("records")


def collect_all(since="2021-01-01"):
    engine, tunnel = _engine()
    try:
        out = {}
        out["advisors"] = _q(engine, """
            SELECT id AS advisor_id, COALESCE(chineseName, englishName, email) AS advisor_name,
                   status, joinInDate, leaveDate, annualTarget
            FROM user""")

        # 表A: 顾问季度回款
        out["A"] = _q(engine, f"""
            SELECT ia.user_id AS advisor_id,
                   COALESCE(u.chineseName, u.englishName, u.email) AS advisor_name,
                   YEAR(i.paymentReceivedDate) AS year, QUARTER(i.paymentReceivedDate) AS quarter,
                   SUM(ia.revenue)/10000.0 AS revenue
            FROM invoiceassignment ia
            JOIN invoice i ON i.id = ia.invoice_id
            JOIN `user` u ON u.id = ia.user_id
            WHERE {_PAID} AND i.paymentReceivedDate >= '{since}'
            GROUP BY ia.user_id, YEAR(i.paymentReceivedDate), QUARTER(i.paymentReceivedDate)
            ORDER BY ia.user_id, year, quarter""")

        # 表B: 顾问客户关系 (客户创建人=本人 -> SELF)
        out["B"] = _q(engine, f"""
            SELECT ia.user_id AS advisor_id, i.client_id, c.name AS client_name,
                   CASE WHEN c.addedBy_id = ia.user_id THEN 'SELF' ELSE 'COMPANY' END AS source_type,
                   MIN(i.paymentReceivedDate) AS first_deal_date,
                   SUM(ia.revenue)/10000.0 AS total_revenue,
                   COUNT(DISTINCT i.id) AS deal_count
            FROM invoiceassignment ia
            JOIN invoice i ON i.id = ia.invoice_id
            JOIN client c ON c.id = i.client_id
            WHERE {_PAID} AND i.paymentReceivedDate >= '{since}'
            GROUP BY ia.user_id, i.client_id, c.addedBy_id, c.name""")

        # 表C: 项目明细
        out["C"] = _q(engine, f"""
            SELECT ia.user_id AS advisor_id, i.joborder_id AS project_id, i.client_id,
                   jo.openDate, os.signDate, os.annualSalary,
                   i.contract_charge_rate AS fee_rate,
                   i.paymentReceivedDate AS payment_date,
                   ia.revenue/10000.0 AS payment_amount
            FROM invoiceassignment ia
            JOIN invoice i ON i.id = ia.invoice_id
            LEFT JOIN joborder jo ON jo.id = i.joborder_id
            LEFT JOIN offersign os ON os.jobsubmission_id = i.jobsubmission_id AND os.active=1
            WHERE {_PAID} AND i.paymentReceivedDate >= '{since}'""")

        # 表D: 公司季度汇总
        out["D"] = _q(engine, f"""
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
            WHERE {_PAID} AND i.paymentReceivedDate >= '{since}'
            GROUP BY YEAR(i.paymentReceivedDate), QUARTER(i.paymentReceivedDate)
            ORDER BY year, quarter""")

        # 表E: 年度目标 (谷露无年份字段, 仅当前年)
        out["E_raw"] = _q(engine, """
            SELECT t.user_id AS advisor_id, t.target/10000.0 AS target_wan
            FROM report_revenue_annual_target t WHERE t.target > 0""")

        # 表F: 在途签约管道 (invoice按jobsubmission去重 + >100万/单截断)
        out["F"] = _q(engine, """
            SELECT os.user_id AS advisor_id,
                   SUM(CASE WHEN os.signDate >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                            THEN LEAST(os.revenue, 1000000) ELSE 0 END)/10000.0 AS signed_12m_wan,
                   SUM(CASE WHEN os.revenue > 1000000 THEN 1 ELSE 0 END) AS outlier_cnt,
                   SUM(inv.any_received) AS received_cnt,
                   SUM(CASE WHEN inv.any_invoice IS NULL
                             AND os.signDate < DATE_SUB(CURDATE(), INTERVAL 9 MONTH)
                            THEN 1 ELSE 0 END) AS stale_unpaid_cnt
            FROM offersign os
            LEFT JOIN (
                SELECT jobsubmission_id,
                       MAX(CASE WHEN status='Received' THEN 1 ELSE 0 END) AS any_received,
                       1 AS any_invoice
                FROM invoice WHERE active=1 GROUP BY jobsubmission_id
            ) inv ON inv.jobsubmission_id = os.jobsubmission_id
            WHERE os.active=1 AND os.offerStatus='Accepted' AND os.signDate >= '2023-01-01'
            GROUP BY os.user_id""")

        # 活动量: 推荐 + 面试 (按顾问x季度)
        out["activity"] = {
            "recommend": _q(engine, """
                SELECT user_id AS advisor_id, YEAR(dateAdded) AS year, QUARTER(dateAdded) AS quarter,
                       COUNT(*) AS cnt
                FROM jobsubmission
                WHERE dateAdded >= '2021-01-01' AND user_id IS NOT NULL
                GROUP BY user_id, YEAR(dateAdded), QUARTER(dateAdded)"""),
            "interview": _q(engine, """
                SELECT user_id AS advisor_id, YEAR(date) AS year, QUARTER(date) AS quarter,
                       COUNT(*) AS cnt
                FROM clientinterview
                WHERE date >= '2021-01-01' AND user_id IS NOT NULL
                GROUP BY user_id, YEAR(date), QUARTER(date)"""),
        }
        return out
    finally:
        engine.dispose()
        if tunnel:
            tunnel.stop()
