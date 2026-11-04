"""
Step 5 - Task 3: back-test, burn cost, premium, and cross-checks (bootstrap + fitted distribution).

Outputs: outputs/task3_backtest.csv, task3_sensitivity.csv, task3_crosschecks.csv, task3_pricing_summary.json
         figures/fig_task3_*.png
"""
import math

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

import config as C
from utils import banner, load_annual, load_json, make_design, payout, save_json, savefig


def premium_rule(burn, sd):
    lr = burn / C.TARGET_LOSS_RATIO
    sdm = burn + C.SD_LOADING_K * sd
    rec = max(lr, sdm)
    rec_round = math.ceil(rec / C.PREMIUM_ROUNDING) * C.PREMIUM_ROUNDING
    return lr, sdm, rec, float(rec_round)


def main():
    banner("STEP 5 (TASK 3): BACK-TEST AND PRICING")
    ann = load_annual()
    spec = load_json(C.OUT_DIR / "product_spec.json")
    I = ann["index_kwh_m2"]
    years = ann.index.values
    trig, ex, cap, mean_i = spec["trigger"], spec["exit"], spec["cap"], spec["mean_index"]

    # ---------------- back-test
    gen = C.AEP50_KWH * I.values / mean_i                      # proxy generation, calibrated to P50
    loss = np.maximum(0.0, C.AEP50_KWH - gen) * C.TARIFF       # modelled savings loss
    pay = payout(I.values, trig, ex, cap)
    bt = pd.DataFrame({
        "index_kwh_m2": I.values, "index_pct_of_mean": I.values / mean_i * 100.0,
        "proxy_generation_kwh": gen, "modelled_savings_loss_rs": loss,
        "payout_rs": pay, "payout_pct_of_cap": pay / cap * 100.0,
    }, index=years)
    bt.index.name = "year"
    bt.to_csv(C.OUT_DIR / "task3_backtest.csv", encoding="utf-8")
    print("Back-test (Rs):")
    print(bt.round(1).to_string())

    burn = float(pay.mean())
    sd = float(pay.std(ddof=1))
    n_pay = int((pay > 0).sum())
    n_cap = int((pay >= cap - 1e-9).sum())
    print("\nBurn cost (mean annual payout): Rs %.2f | std dev: Rs %.2f | max: Rs %.2f" % (burn, sd, pay.max()))
    print("Payout frequency: %d of %d years (%.0f%%) | years at maximum payout: %d" % (n_pay, len(pay), n_pay / len(pay) * 100, n_cap))
    print("Average payout in years that pay: Rs %.2f" % (pay[pay > 0].mean() if n_pay else 0.0))

    # ---------------- cross-checks
    rng = np.random.default_rng(C.SEED)
    boot_idx = rng.choice(I.values, size=(C.N_BOOTSTRAP, len(I)), replace=True)
    boot_burn = payout(boot_idx, trig, ex, cap).mean(axis=1)
    mu, s = float(I.mean()), float(I.std(ddof=1))
    draws = rng.normal(mu, s, size=C.N_SIM)
    pay_fit = payout(draws, trig, ex, cap)
    fit_burn = float(pay_fit.mean())
    fit_sd = float(pay_fit.std(ddof=1))
    p_trig_fit = float(stats.norm.cdf((trig - mu) / s))

    lr_ = lambda b: b / C.TARGET_LOSS_RATIO
    cross = pd.DataFrame([
        ["Historical back-test (20 years)", burn, lr_(burn)],
        ["Bootstrap mean (resampled years)", float(boot_burn.mean()), lr_(float(boot_burn.mean()))],
        ["Bootstrap 5th percentile", float(np.percentile(boot_burn, 5)), lr_(float(np.percentile(boot_burn, 5)))],
        ["Bootstrap 95th percentile", float(np.percentile(boot_burn, 95)), lr_(float(np.percentile(boot_burn, 95)))],
        ["Fitted normal distribution (%d draws)" % C.N_SIM, fit_burn, lr_(fit_burn)],
    ], columns=["method", "burn_cost_rs", "premium_at_target_loss_ratio_rs"])
    cross.to_csv(C.OUT_DIR / "task3_crosschecks.csv", index=False, encoding="utf-8")
    print("\nCross-checks on the burn cost (Rs/year):")
    print(cross.round(1).to_string(index=False))
    print("Fitted-normal probability of paying in a year: %.1f%% (historical frequency %.0f%%)" % (p_trig_fit * 100, n_pay / len(pay) * 100))

    # trend-adjusted sensitivity: shift every year to the 2024 level, same contract
    lr = stats.linregress(I.index.values.astype(float), I.values)
    adj = I.values + lr.slope * (I.index.values[-1] - I.index.values)
    burn_adj = float(payout(adj, trig, ex, cap).mean())
    print("Trend-adjusted burn cost (history shifted to 2024 level; trend %.2f kWh/m2/yr, p=%.3f): Rs %.2f"
          % (lr.slope, lr.pvalue, burn_adj))

    # ---------------- premium
    pricing_burn = burn
    note = "historical back-test"
    if burn <= 0.0:
        pricing_burn = fit_burn
        note = "fitted-normal burn cost (the historical back-test produced no payout)"
        print("\nNOTE: no historical year paid out, so the premium is based on the fitted-distribution burn cost.")
    pricing_sd = sd if burn > 0.0 else fit_sd
    lr_prem, sd_prem, rec, rec_round = premium_rule(pricing_burn, pricing_sd)
    print("\nPREMIUM (basis: %s, Rs %.2f):" % (note, pricing_burn))
    print("  Method 1, burn cost / target loss ratio %.2f : Rs %.2f" % (C.TARGET_LOSS_RATIO, lr_prem))
    print("  Method 2, burn cost + %.2f x std dev of payout: Rs %.2f" % (C.SD_LOADING_K, sd_prem))
    print("  Recommended (higher of the two, rounded up) : Rs %.0f per year" % rec_round)
    print("  = %.2f%% of annual savings (Rs %.0f) | %.2f%% of installation cost | rate on line %.2f%% of max payout"
          % (rec_round / C.ANNUAL_SAVINGS_P50 * 100, C.ANNUAL_SAVINGS_P50, rec_round / C.INSTALL_COST * 100, rec_round / cap * 100))
    print("  Expected loss ratio at this premium: %.1f%%" % (pricing_burn / rec_round * 100 if rec_round > 0 else 0.0))

    # ---------------- design sensitivity (trigger level)
    rows = []
    for tp in (0.90, 0.93, 0.95, 0.97, 1.00):
        dd = make_design(I.values, tp, C.EXIT_PERCENTILE, cap, C.MIN_BAND_PCT_OF_MEAN)
        pp = payout(I.values, dd["trigger"], dd["exit"], cap)
        b, sdv = float(pp.mean()), float(pp.std(ddof=1))
        _, _, _, prem = premium_rule(b, sdv)
        rows.append([tp, dd["trigger"], dd["exit"], int((pp > 0).sum()), b, sdv, prem, "<- chosen" if abs(tp - C.TRIGGER_PCT_OF_MEAN) < 1e-9 else ""])
    sens = pd.DataFrame(rows, columns=["trigger_pct_of_mean", "trigger", "exit", "years_paying", "burn_cost_rs",
                                       "std_rs", "recommended_premium_rs", "note"])
    sens.to_csv(C.OUT_DIR / "task3_sensitivity.csv", index=False, encoding="utf-8")
    print("\nSensitivity to the trigger level (exit rule and cap unchanged):")
    print(sens.round({"trigger_pct_of_mean": 2, "trigger": 1, "exit": 1, "burn_cost_rs": 1,
                      "std_rs": 1, "recommended_premium_rs": 0}).to_string(index=False))

    save_json({
        "burn_cost_rs": burn, "std_payout_rs": sd, "max_payout_rs": float(pay.max()), "years_paying": n_pay,
        "years_at_cap": n_cap, "pricing_basis": note, "pricing_burn_rs": pricing_burn,
        "premium_loss_ratio_method_rs": lr_prem, "premium_sd_method_rs": sd_prem,
        "recommended_premium_rs": rec_round,
        "premium_pct_of_savings": rec_round / C.ANNUAL_SAVINGS_P50 * 100,
        "premium_pct_of_install_cost": rec_round / C.INSTALL_COST * 100,
        "rate_on_line_pct": rec_round / cap * 100,
        "expected_loss_ratio_pct": (pricing_burn / rec_round * 100) if rec_round > 0 else 0.0,
        "bootstrap_mean": float(boot_burn.mean()), "bootstrap_p5": float(np.percentile(boot_burn, 5)),
        "bootstrap_p95": float(np.percentile(boot_burn, 95)),
        "fitted_normal_burn_rs": fit_burn, "fitted_normal_prob_trigger": p_trig_fit,
        "trend_adjusted_burn_rs": burn_adj, "trend_slope_kwh_m2_per_year": float(lr.slope), "trend_p_value": float(lr.pvalue),
    }, C.OUT_DIR / "task3_pricing_summary.json")

    # ---------------- figures
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(years, pay, color="#c0392b")
    ax.axhline(burn, color="k", ls="--", label="burn cost Rs %.0f" % burn)
    ax.axhline(cap, color="grey", ls=":", label="maximum payout")
    ax.set_xlabel("Year")
    ax.set_ylabel("Payout (Rs)")
    ax.set_title("Back-tested annual payout")
    ax.legend()
    savefig(fig, "fig_task3_backtest.png")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(boot_burn, bins=40, color="#2e8b57", alpha=0.8)
    ax.axvline(burn, color="k", ls="--", label="historical %.0f" % burn)
    ax.axvline(fit_burn, color="#1f4e9c", ls="-.", label="fitted normal %.0f" % fit_burn)
    ax.set_xlabel("Burn cost estimate (Rs/year)")
    ax.set_ylabel("Frequency")
    ax.set_title("Bootstrap distribution of the burn cost")
    ax.legend()
    savefig(fig, "fig_task3_bootstrap.png")
    print("\nTask 3 outputs saved.")


if __name__ == "__main__":
    main()
