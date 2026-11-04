"""
Step 6 - Task 4: quantify three failure modes for a book of 10,000 customers.
  A. Spatial basis risk       B. Non-weather losses       C. Correlated (portfolio) exposure
Assumptions are in config.py and are labelled ASSUMPTION there.

Outputs: outputs/task4_*.csv / json, figures/fig_task4_*.png
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import config as C
from utils import banner, load_annual, load_json, payout, save_json, savefig

CRORE = 1e7


def main():
    banner("STEP 6 (TASK 4): PRODUCT CRITIQUE ON 10,000 CUSTOMERS")
    ann = load_annual()
    spec = load_json(C.OUT_DIR / "product_spec.json")
    price = load_json(C.OUT_DIR / "task3_pricing_summary.json")
    I = ann["index_kwh_m2"]
    years = ann.index.values
    Y, N = len(I), C.N_CUSTOMERS
    trig, ex, cap, mean_i = spec["trigger"], spec["exit"], spec["cap"], spec["mean_index"]
    prem = float(price["recommended_premium_rs"])
    burn = float(price["burn_cost_rs"])
    P_y = payout(I.values, trig, ex, cap)
    gen_y = C.AEP50_KWH * I.values / mean_i
    material = C.MATERIAL_LOSS_PCT * C.ANNUAL_SAVINGS_P50
    paid_row = (P_y > 0)[:, None]
    rng = np.random.default_rng(C.SEED)

    print("Book: %d customers | premium Rs %.0f | premium pool Rs %.2f crore | maximum exposure Rs %.2f crore"
          % (N, prem, N * prem / CRORE, N * cap / CRORE))
    print("Material loss threshold: Rs %.2f (%.0f%% of annual savings)" % (material, C.MATERIAL_LOSS_PCT * 100))

    # ============================================================ A. SPATIAL BASIS RISK
    print("\n--- A. SPATIAL BASIS RISK ---")
    cell_cols = [c for c in ann.columns if c.startswith("cell_")]
    cell_rows = []
    for c in cell_cols:
        ci = ann[c].values
        offset_pct = (ci.mean() / I.mean() - 1.0) * 100.0
        adj = ci / ci.mean() * I.mean()               # remove the cell's systematic offset (absorbed by P50 calibration)
        pc = payout(adj, trig, ex, cap)
        cell_rows.append([c.replace("cell_", ""), offset_pct, float(np.mean(np.abs(pc - P_y))), float(np.max(np.abs(pc - P_y))),
                          int(((pc > 0) != (P_y > 0)).sum())])
    cells_df = pd.DataFrame(cell_rows, columns=["cell", "mean_offset_vs_pooled_pct", "mean_abs_payout_diff_rs",
                                                "max_abs_payout_diff_rs", "years_trigger_decision_differs"])
    cells_df.to_csv(C.OUT_DIR / "task4_A_cells.csv", index=False, encoding="utf-8")
    spread = float((ann[cell_cols].std(axis=1, ddof=0) / ann[cell_cols].mean(axis=1)).mean() * 100.0) if len(cell_cols) > 1 else 0.0
    print("Measured spread between the %d ERA5-Land cells: %.2f%% of the annual index (cells are ~11 km apart)." % (len(cell_cols), spread))
    print(cells_df.round(2).to_string(index=False))
    print("Note: ERA5-Land cells are strongly correlated, so this understates rooftop-scale deviation.")
    print("Rooftop-level deviation is therefore simulated (ASSUMPTION: std dev %.1f%% of annual generation)." % (C.LOCAL_SD_PCT * 100))

    def sim_A(sigma, gen_rng):
        eps = gen_rng.normal(0.0, sigma, size=(Y, N))
        loss = np.maximum(0.0, C.AEP50_KWH - gen_y[:, None] * (1.0 + eps)) * C.TARIFF
        mat = loss >= material
        miss = mat & ~paid_row
        false_pay = (~mat) & paid_row
        n_mat = int(mat.sum())
        n_paid = int(paid_row.sum() * N)
        return {
            "sigma_pct": sigma * 100.0,
            "miss_rate_pct": float(miss.sum() / n_mat * 100.0) if n_mat else 0.0,
            "false_payout_rate_pct": float(false_pay.sum() / n_paid * 100.0) if n_paid else 0.0,
            "avg_customers_uncovered_per_year": float(miss.sum(axis=1).mean()),
            "worst_year_customers_uncovered": int(miss.sum(axis=1).max()),
            "avg_customers_material_loss_per_year": float(mat.sum(axis=1).mean()),
        }, miss, false_pay

    sens_rows = []
    main_A = None
    for sg in sorted(set(C.LOCAL_SD_SENSITIVITY + [C.LOCAL_SD_PCT])):
        res, miss, fp = sim_A(sg, np.random.default_rng(C.SEED))
        sens_rows.append(res)
        if abs(sg - C.LOCAL_SD_PCT) < 1e-12:
            main_A = (res, miss, fp)
    sensA = pd.DataFrame(sens_rows)
    sensA.to_csv(C.OUT_DIR / "task4_A_sensitivity.csv", index=False, encoding="utf-8")
    resA, missA, fpA = main_A
    byyear = pd.DataFrame({
        "index_kwh_m2": I.values, "payout_rs": P_y,
        "customers_material_loss_no_payout": missA.sum(axis=1),
        "customers_payout_without_material_loss": fpA.sum(axis=1),
    }, index=years)
    byyear.index.name = "year"
    byyear.to_csv(C.OUT_DIR / "task4_A_by_year.csv", encoding="utf-8")
    print("\nSimulated result (base case, %.1f%% local deviation):" % resA["sigma_pct"])
    print("  Customer-years with a material weather loss that receive NO payout: %.1f%%" % resA["miss_rate_pct"])
    print("  Customer-years that receive a payout without a material loss      : %.1f%%" % resA["false_payout_rate_pct"])
    print("  On average %.0f of %d customers per year are uncovered despite a material loss (worst year: %d)."
          % (resA["avg_customers_uncovered_per_year"], N, resA["worst_year_customers_uncovered"]))
    print("Sensitivity to the local deviation assumption:")
    print(sensA.round(1).to_string(index=False))

    # ============================================================ B. NON-WEATHER LOSSES
    print("\n--- B. NON-WEATHER LOSSES (inverter failure, soiling, shading, grid outage) ---")
    lo, hi = C.NONWEATHER_LOSS_RANGE
    rngB = np.random.default_rng(C.SEED + 1)
    eps = rngB.normal(0.0, C.LOCAL_SD_PCT, size=(Y, N))
    gen_w = gen_y[:, None] * (1.0 + eps)
    loss_w = np.maximum(0.0, C.AEP50_KWH - gen_w) * C.TARIFF
    event = rngB.random((Y, N)) < C.NONWEATHER_PROB
    u = rngB.uniform(lo, hi, size=(Y, N))
    gen_t = gen_w * (1.0 - event * u)
    loss_t = np.maximum(0.0, C.AEP50_KWH - gen_t) * C.TARIFF
    nw_loss = loss_t - loss_w
    mat_t = loss_t >= material
    miss_t = mat_t & ~paid_row
    n_ev = int(event.sum())
    resB = {
        "customers_hit_per_year": float(event.sum(axis=1).mean()),
        "avg_nonweather_loss_per_hit_customer_rs": float(nw_loss[event].mean()) if n_ev else 0.0,
        "total_nonweather_loss_per_year_rs": float(nw_loss.sum(axis=1).mean()),
        "nonweather_share_of_total_loss_pct": float(nw_loss.sum() / loss_t.sum() * 100.0) if loss_t.sum() > 0 else 0.0,
        "premium_pool_rs": N * prem,
        "expected_payout_pool_rs": N * burn,
        "miss_rate_with_nonweather_pct": float(miss_t.sum() / mat_t.sum() * 100.0) if mat_t.sum() else 0.0,
        "miss_rate_weather_only_pct": resA["miss_rate_pct"],
    }
    resB["nonweather_loss_over_premium_pool"] = resB["total_nonweather_loss_per_year_rs"] / max(N * prem, 1.0)
    save_json(resB, C.OUT_DIR / "task4_B_summary.json")
    print("Assumptions: %.0f%% of customers per year hit; each loses %.0f-%.0f%% of annual generation."
          % (C.NONWEATHER_PROB * 100, lo * 100, hi * 100))
    print("  Customers hit per year: %.0f of %d | average loss per hit customer: Rs %.0f"
          % (resB["customers_hit_per_year"], N, resB["avg_nonweather_loss_per_hit_customer_rs"]))
    print("  Total non-weather loss per year: Rs %.2f crore = %.1f x the whole premium pool (Rs %.2f crore)"
          % (resB["total_nonweather_loss_per_year_rs"] / CRORE, resB["nonweather_loss_over_premium_pool"], N * prem / CRORE))
    print("  Non-weather events cause %.0f%% of all customer savings shortfall; none of it is paid by this product."
          % resB["nonweather_share_of_total_loss_pct"])
    print("  Customer-years with a material loss and no payout rise from %.1f%% (weather only) to %.1f%% (with non-weather losses)."
          % (resB["miss_rate_weather_only_pct"], resB["miss_rate_with_nonweather_pct"]))

    # ============================================================ C. CORRELATED EXPOSURE
    print("\n--- C. CORRELATED (PORTFOLIO) EXPOSURE ---")
    agg = N * P_y
    pool = N * prem
    byC = pd.DataFrame({"index_kwh_m2": I.values, "aggregate_payout_rs": agg, "premium_pool_rs": pool,
                        "aggregate_loss_ratio_pct": agg / max(pool, 1.0) * 100.0}, index=years)
    byC.index.name = "year"
    byC.to_csv(C.OUT_DIR / "task4_C_by_year.csv", encoding="utf-8")
    mu, s = float(I.mean()), float(I.std(ddof=1))
    sim_idx = np.random.default_rng(C.SEED + 2).normal(mu, s, size=C.N_SIM)
    sim_agg = N * payout(sim_idx, trig, ex, cap)
    var99 = float(np.percentile(sim_agg, 99))
    var995 = float(np.percentile(sim_agg, 99.5))
    tail = sim_agg[sim_agg >= var99]
    tvar99 = float(tail.mean()) if len(tail) else var99
    resC = {
        "premium_pool_rs": pool, "max_exposure_rs": N * cap, "max_exposure_over_pool": N * cap / max(pool, 1.0),
        "worst_historical_year": int(years[int(np.argmax(agg))]), "worst_historical_aggregate_rs": float(agg.max()),
        "years_aggregate_above_pool": int((agg > pool).sum()),
        "sim_prob_aggregate_above_pool_pct": float((sim_agg > pool).mean() * 100.0),
        "sim_var99_rs": var99, "sim_var995_rs": var995, "sim_tvar99_rs": tvar99,
        "capital_buffer_for_var99_rs": max(0.0, var99 - pool),
    }
    save_json(resC, C.OUT_DIR / "task4_C_summary.json")
    print("Premium pool Rs %.2f crore vs maximum possible payout Rs %.2f crore (%.1f x the pool)."
          % (pool / CRORE, N * cap / CRORE, resC["max_exposure_over_pool"]))
    print("Worst historical year %d: aggregate payout Rs %.2f crore (%.0f%% of pool). Years with aggregate payout above the pool: %d of %d."
          % (resC["worst_historical_year"], agg.max() / CRORE, agg.max() / max(pool, 1.0) * 100, resC["years_aggregate_above_pool"], Y))
    print("Fitted-normal stress (%d simulated years): P(aggregate > pool) = %.1f%% | 99th pct Rs %.2f crore | 99.5th pct Rs %.2f crore"
          % (C.N_SIM, resC["sim_prob_aggregate_above_pool_pct"], var99 / CRORE, var995 / CRORE))
    print("Extra capital or reinsurance needed to cover the 99th percentile year: Rs %.2f crore" % (resC["capital_buffer_for_var99_rs"] / CRORE))
    print("Every customer is paid by the same weather, so there is no diversification inside one pincode area.")

    save_json({"A": resA, "B": resB, "C": resC}, C.OUT_DIR / "task4_summary.json")

    # ---------------- figures
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(years - 0.2, byyear["customers_material_loss_no_payout"], width=0.4, color="#c0392b", label="material loss, no payout")
    ax.bar(years + 0.2, byyear["customers_payout_without_material_loss"], width=0.4, color="#1f4e9c", label="payout, no material loss")
    ax.set_xlabel("Year")
    ax.set_ylabel("Customers (of %d)" % N)
    ax.set_title("A. Spatial basis risk: mismatches by year (base case)")
    ax.legend()
    savefig(fig, "fig_task4_A_spatial.png")

    fig, ax = plt.subplots(figsize=(6, 4))
    vals = [N * burn / CRORE, pool / CRORE, resB["total_nonweather_loss_per_year_rs"] / CRORE]
    ax.bar(["Expected\npayouts", "Premium\npool", "Non-weather\nlosses (uncovered)"], vals, color=["#c0392b", "#2e8b57", "#7f8c8d"])
    ax.set_ylabel("Rs crore per year")
    ax.set_title("B. Non-weather losses vs money in the product")
    savefig(fig, "fig_task4_B_nonweather.png")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(years, agg / CRORE, color="#c0392b", label="aggregate payout")
    ax.axhline(pool / CRORE, color="k", ls="--", label="premium pool")
    ax.axhline(N * cap / CRORE, color="grey", ls=":", label="maximum exposure")
    ax.set_xlabel("Year")
    ax.set_ylabel("Rs crore")
    ax.set_title("C. Correlated exposure: all customers paid in the same year")
    ax.legend()
    savefig(fig, "fig_task4_C_aggregate.png")
    print("\nTask 4 outputs saved.")


if __name__ == "__main__":
    main()
