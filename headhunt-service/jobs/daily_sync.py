# -*- coding: utf-8 -*-
"""每日跑批: 重新采集谷露 -> 全量重算 -> 输出. 容器内 cron 或宿主机定时调用.
用法: python -m jobs.daily_sync
"""
import os
import sys
import logging
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.run import run_pipeline

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE, "data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, f"daily_{datetime.now():%Y%m%d}.log"),
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    logging.info("daily sync start")
    try:
        res = run_pipeline(os.path.join(BASE, "config", "config.yaml"), use_cache=False)
        logging.info("done: active=%s market=%s", res["meta"]["n_active"], res["market"]["phase"])
        print(f"OK active={res['meta']['n_active']} market={res['market']['phase']}")
    except Exception:
        logging.error("daily sync failed:\n%s", traceback.format_exc())
        print("FAILED, see log")
        sys.exit(1)


if __name__ == "__main__":
    main()
