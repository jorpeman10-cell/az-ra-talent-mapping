# 验收阶段: headhunt.* -> enabled, allowlist=[Steven]
import sys
sys.path.insert(0, "/app")
from runtime_config_service import get_runtime_config

STEVEN = "user_qF9UExioemTLeThYLOKnvOj5UEg"
KEYS = ["headhunt.decision_board", "headhunt.consultant_decision",
        "headhunt.salary_scan", "headhunt.pipeline_rerun"]

rc = get_runtime_config()
flags = rc.get("capability.flags") or {}
allow = rc.get("capability.allowlists") or {}
for k in KEYS:
    flags[k] = "enabled"
    allow[k] = [STEVEN]
rc.set("capability.flags", flags)
rc.set("capability.allowlists", allow)
print("ENABLED:", {k: flags[k] for k in KEYS})
