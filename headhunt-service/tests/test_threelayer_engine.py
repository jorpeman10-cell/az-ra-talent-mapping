# -*- coding: utf-8 -*-
"""三层风险结构引擎单元测试: L1 收缩单调性 / L2 流失触发器 / L3 分位单调性."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.engine import calculate_effective_capacity, evaluate_advisor

MARKET = {"phase": "VOLATILE", "market_slope": -0.3088, "market_cv": 0.3094}
RISK = {"cv_prior": {"a": 1.6716, "b1": -0.4454, "b2": 0.3667, "k": 8,
                     "clip_min": 0.1, "clip_max": 2.5},
        "churn_addon_pp": 5, "quantiles": [0.25, 0.5, 0.75]}
ECFG = {"discount_rate": 0.12, "attrition_rate": 0.10, "terminal_multiple": 0.5,
        "irr_threshold": 0.20, "commission_tiers": [[40, 0.30]], "tax_ratio": 0.936,
        "demand_pct": 0.0, "competition_pct": 0.0, "target_pct": 15.0,
        "lift_pct": 10.0, "op_cost_pct": 15.0, "equity_pct": 20.0,
        "support_cost": 5.0, "salary_annual": 8.52, "insurance_pct": 30.0,
        "company_fixed_cost": 6.37, "management_cost": 0.0}


def _profile(n_hist=8, cv=0.3, mu=10.0):
    return {"advisor_id": "t1", "mu": mu, "cv": cv, "beta": 1.0, "beta_r2": 0.0,
            "alpha": 0.0, "beta_estimated": True, "n_history_quarters": n_hist}


class L1ShrinkageTests(unittest.TestCase):
    def test_new_hire_uses_pure_prior(self):
        """n_hist=0 且有成单估计时, cv_shrunk == cv_prior(纯先验)."""
        cap = calculate_effective_capacity(
            _profile(n_hist=0, cv=1.0), MARKET, deals_12m=4.0, risk=RISK)
        self.assertIsNotNone(cap["cv_prior"])
        self.assertEqual(cap["cv_used"], cap["cv_prior"])

    def test_measured_low_cv_not_pulled_up(self):
        """实际低 CV(min 口径) <= 先验时保持实际值, 单侧不上拉."""
        cap = calculate_effective_capacity(
            _profile(n_hist=8, cv=0.3), MARKET, deals_12m=4.0, risk=RISK)
        # prior for M=4: 1.6716-0.4454*ln4 ≈ 1.05 >> 0.3 → keep 0.3
        self.assertEqual(cap["cv_used"], 0.3)

    def test_noisy_high_cv_blends_down(self):
        """实际 CV > 先验时向先验收缩(双向混合)."""
        cap = calculate_effective_capacity(
            _profile(n_hist=8, cv=2.0), MARKET, deals_12m=4.0, risk=RISK)
        prior = cap["cv_prior"]
        self.assertLess(cap["cv_used"], 2.0)
        self.assertGreaterEqual(cap["cv_used"], min(prior, 2.0) - 1e-9)

    def test_legacy_toggle_restores_plain_cv(self):
        cap = calculate_effective_capacity(
            _profile(n_hist=8, cv=2.0), MARKET, deals_12m=4.0,
            risk={"enabled": False})
        self.assertEqual(cap["cv_used"], 2.0)


class L2ChurnAlertTests(unittest.TestCase):
    def test_two_consecutive_drops_trigger_addon(self):
        series = {(2025, 1): 8, (2025, 2): 7, (2025, 3): 6, (2025, 4): 5}
        base = calculate_effective_capacity(
            _profile(), MARKET, deals_12m=4.0, client_series=series, risk=RISK)
        self.assertTrue(base["monitoring"]["churn_alert"])
        clean = calculate_effective_capacity(
            _profile(), MARKET, deals_12m=4.0, risk=RISK)
        self.assertAlmostEqual(
            base["total_discount"], min(0.6, clean["total_discount"] + 0.05), places=4)

    def test_single_drop_does_not_trigger(self):
        series = {(2025, 1): 8, (2025, 2): 7, (2025, 3): 7, (2025, 4): 6}
        cap = calculate_effective_capacity(
            _profile(), MARKET, deals_12m=4.0, client_series=series, risk=RISK)
        self.assertFalse(cap["monitoring"]["churn_alert"])

    def test_current_partial_quarter_excluded(self):
        # 数据含"当前未完结季度"(客户数必然低), 不应误判为流失
        from datetime import datetime
        y, q = datetime.now().year, (datetime.now().month - 1) // 3 + 1
        series = {(y, q - 3): 8, (y, q - 2): 8, (y, q - 1): 8, (y, q): 1}
        cap = calculate_effective_capacity(
            _profile(), MARKET, deals_12m=4.0, client_series=series, risk=RISK)
        self.assertFalse(cap["monitoring"]["churn_alert"])


class L3QuantileTests(unittest.TestCase):
    def test_quantiles_monotonic(self):
        cap = calculate_effective_capacity(
            _profile(), MARKET, deals_12m=4.0, risk=RISK)
        q = cap["quantiles"]
        self.assertGreaterEqual(q["p75"], q["p50"])
        self.assertGreaterEqual(q["p50"], q["p25"])

    def test_quantile_models_attached(self):
        cap = calculate_effective_capacity(
            _profile(), MARKET, deals_12m=4.0, risk=RISK)
        d = evaluate_advisor(_profile(), cap, MARKET, [10.0, 10.0, 10.0, 10.0],
                             [], 2026, {}, ECFG)
        qm = d["models"]["quantiles"]
        self.assertEqual(set(qm), {"p25", "p50", "p75"})
        self.assertGreaterEqual(qm["p75"]["npv_3y"], qm["p25"]["npv_3y"])
        self.assertEqual(d["decision"], d["decision_band"]["p50_base"])


if __name__ == "__main__":
    unittest.main()
