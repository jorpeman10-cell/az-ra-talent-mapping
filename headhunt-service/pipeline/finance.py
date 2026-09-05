"""
财务引擎 (原 headhunt_model_irr20.py v8, 已经8轮真实数据验证, 勿改公式)
v8.1: tier阶梯与税后系数改为构造参数, 由 config.yaml 注入
"""
import math


class HeadhuntDecisionModel:
    def __init__(self, discount_rate=0.12, attrition_rate=0.10, terminal_multiple=0.5,
                 irr_threshold=0.20, tiers=None, tax_ratio=0.936):
        self.discount_rate = discount_rate
        self.attrition_rate = attrition_rate
        self.terminal_multiple = terminal_multiple
        self.irr_threshold = irr_threshold
        # [(上限万, 比例), ...] 升序; 默认与2023薪酬激励政策一致
        self.tiers = tiers or [(40, 0.30), (60, 0.32), (100, 0.35),
                               (150, 0.38), (200, 0.40), (float("inf"), 0.45)]
        self.tax_ratio = tax_ratio

    def tier(self, r):
        for cap, rate in self.tiers:
            if r <= cap:
                return rate
        return self.tiers[-1][1]

    def _wpct(self, values_weights, p):
        if not values_weights: return 0
        svw = sorted(values_weights, key=lambda x: x[0])
        tw = sum(w for _, w in svw)
        if tw == 0: return svw[len(svw)//2][0]
        twp = tw * p
        cs = 0
        for v, w in svw:
            cs += w
            if cs >= twp: return v
        return svw[-1][0]

    def calibration(self, records, current_year, difficulty_curve):
        valid = [r for r in records if r.get("annualized", 0) > 0 and r.get("actual", 0) >= 0]
        vw = []
        for rec in valid:
            yr = rec["year"]
            dt = difficulty_curve.get(yr, 1.0)
            dn = difficulty_curve.get(current_year, 1.0)
            adj_actual = rec["actual"] / dt * dn
            needed = max(0, 1 - adj_actual / rec["annualized"])
            ya = current_year - yr
            weight = 1 / ((1 + self.discount_rate) ** ya)
            vw.append((needed, weight))
        n = len(vw)
        cap = min(0.5, max(0.05, self._wpct(vw, 0.9))) if n >= 5 else 0.3
        return {"n": n, "cap": cap}

    def _irr(self, cashflows, guess=0.15):
        # 现金流无变号则无IRR(全负=纯亏损, 全正=无投资)
        if not (any(cf > 0 for cf in cashflows) and any(cf < 0 for cf in cashflows)):
            return None
        def npv(rate):
            return sum(cf / ((1 + rate) ** t) for t, cf in enumerate(cashflows))
        def dnpv(rate):
            return sum(-t * cf / ((1 + rate) ** (t + 1)) for t, cf in enumerate(cashflows) if t > 0)
        rate = guess
        for _ in range(50):
            n = npv(rate); d = dnpv(rate)
            if abs(d) < 1e-12: break
            nr = rate - n / d
            if abs(nr - rate) < 1e-6: break
            rate = max(-0.99, min(2, nr))
        return rate if not math.isnan(rate) else None

    def evaluate(self, quarters, demand_pct, competition_pct, target_pct, insurance_pct,
                 salary_annual, lift_pct, op_cost_pct, equity_pct, support_cost,
                 history_records, current_year, company_fixed_cost, management_cost,
                 difficulty_curve, discount_override=None):
        avg = sum(quarters)/len(quarters)
        sd = math.sqrt(sum((x-avg)**2 for x in quarters)/len(quarters))
        cv = sd/avg if avg else 1
        c = self.calibration(history_records, current_year, difficulty_curve)
        # 外部引擎(v2交互模型)已完成产能折减时, 传 discount_override=0 避免双重折减
        discount = min(c["cap"], cv*0.5) if discount_override is None else discount_override
        conservative = avg*4*(1-discount)
        d = demand_pct/100; comp = competition_pct/100
        tgt = target_pct/100; ins = insurance_pct/100
        lift = lift_pct/100; cost = op_cost_pct/100
        eq = equity_pct/100

        r_y1 = max(0, conservative*(1+d)*(1-comp))
        fy = [current_year+1, current_year+2, current_year+3]
        r_series = []
        for i, yr in enumerate(fy):
            df = difficulty_curve.get(yr, difficulty_curve.get(current_year, 1.0))
            ry = avg*4*df*(1+d)*(1-comp)*((1-self.attrition_rate)**i)
            r_series.append(max(0, ry))

        # 提成 = 税后回款×tier − 已发底薪 (官方制度公式, 底薪含在提成盘子内不双算)
        # 成本随年度回款逐年浮动
        def official_bonus(rev):
            return max(0.0, rev*self.tax_ratio*self.tier(rev) - salary_annual)
        bonus_y1 = official_bonus(r_y1)
        emp_cost_series = [salary_annual*(1+ins) + official_bonus(r)
                           + company_fixed_cost + management_cost for r in r_series]
        emp_profit_series = [r-c for r, c in zip(r_series, emp_cost_series)]
        emp_margin_y1 = emp_profit_series[0]/r_y1 if r_y1 else -1
        # 季度现金流: 成本按季滚动, NPV按季折现, IRR按季求解后年化
        emp_cf = [p/4 for p in emp_profit_series for _ in range(4)]
        emp_npv = sum(cf/((1+self.discount_rate)**(t/4)) for t, cf in enumerate(emp_cf))
        emp_irr_q = self._irr(emp_cf)
        if emp_irr_q is not None:
            emp_irr = (1+emp_irr_q)**4 - 1
        elif all(cf > 0 for cf in emp_cf):
            emp_irr = 9.99  # 无期初投资且各季净现金流全正, 视为远超门槛
        else:
            emp_irr = None

        irs = [r*(1+lift) for r in r_series]
        ops = [ir*cost for ir in irs]
        ips = [ir-op for ir, op in zip(irs, ops)]
        comps = [ip*eq-support_cost for ip in ips]
        founders = [ip*(1-eq) for ip in ips]

        # 孵化: t=0 仅一次性启动成本, 后续按季净分成, 期末加终端价值
        inc_cf = [-(support_cost+company_fixed_cost+management_cost)] + \
                 [cp/4 for cp in comps for _ in range(4)]
        tv = r_series[-1]*self.terminal_multiple*eq
        inc_cf[-1] += tv
        inc_npv = sum(cf/((1+self.discount_rate)**(t/4)) for t, cf in enumerate(inc_cf))
        inc_irr_q = self._irr(inc_cf)
        inc_irr = (1+inc_irr_q)**4 - 1 if inc_irr_q is not None else None

        emp_irr_ok = emp_irr is not None and emp_irr >= self.irr_threshold
        inc_irr_ok = inc_irr is not None and inc_irr >= self.irr_threshold

        emp_feasible = (emp_margin_y1 >= tgt) and emp_irr_ok
        founder_baseline = salary_annual + bonus_y1*0.7
        inc_feasible = inc_irr_ok and (founders[0] >= founder_baseline)

        if emp_feasible: decision = "EMPLOY"
        elif inc_feasible: decision = "INCUBATE"
        else: decision = "PASS"

        return {
            "decision": decision,
            "emp_npv": emp_npv, "emp_irr": emp_irr, "emp_irr_ok": emp_irr_ok,
            "incubate_npv": inc_npv, "incubate_irr": inc_irr, "incubate_irr_ok": inc_irr_ok,
            "emp_feasible": emp_feasible, "inc_feasible": inc_feasible,
            "emp_margin_y1": emp_margin_y1,
            "forecast_series": r_series,
            "emp_profit_series": emp_profit_series,
            "company_series": comps,
            "founder_series": founders,
            "cap": c["cap"], "discount": discount,
        }
