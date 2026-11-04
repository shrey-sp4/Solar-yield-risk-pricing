"""
Step 3 - Task 1 evidence: why annual solar irradiation (SSRD) is the index.

Outputs: outputs/task1_stats.json, task1_monthly_climatology.csv, task1_variance_by_month.csv, task1_correlations.csv
         figures/fig_task1_*.png
"""
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

import config as C
from utils import banner, load_annual, save_json, savefig

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def main():
    banner("STEP 3 (TASK 1): INDEX SELECTION EVIDENCE")
    daily = pd.read_csv(C.OUT_DIR / "daily.csv", index_col="date", parse_dates=True)
    ann = load_annual()
    I = ann["index_kwh_m2"]

    # ---------- monthly totals matrix (years x months)
    mg = daily["ghi_kwh_m2"].resample("MS").sum().to_frame("v")
    mr = daily["rain_mm"].resample("MS").sum().to_frame("v")
    for d in (mg, mr):
        d["y"] = d.index.year
        d["m"] = d.index.month
    M = mg.pivot(index="y", columns="m", values="v")
    R = mr.pivot(index="y", columns="m", values="v")

    clim = pd.DataFrame({"ghi_kwh_m2_per_month": M.mean(axis=0).values,
                         "rain_mm_per_month": R.mean(axis=0).values}, index=MONTHS)
    clim.index.name = "month"
    clim.to_csv(C.OUT_DIR / "task1_monthly_climatology.csv", encoding="utf-8")
    print("Monthly climatology (mean over 20 years):")
    print(clim.round(1).to_string())

    # ---------- which months drive year-to-year variability of the annual index?
    annual_from_months = M.sum(axis=1)
    contrib = np.array([np.cov(M[m].values, annual_from_months.values)[0, 1] for m in M.columns]) \
        / np.var(annual_from_months.values, ddof=1)
    vcontrib = pd.DataFrame({"share_of_annual_variance_pct": contrib * 100.0}, index=MONTHS)
    vcontrib.index.name = "month"
    vcontrib.to_csv(C.OUT_DIR / "task1_variance_by_month.csv", encoding="utf-8")
    monsoon_share = float(vcontrib.loc[["Jun", "Jul", "Aug", "Sep"], "share_of_annual_variance_pct"].sum())
    print("\nShare of year-to-year variance of the ANNUAL index by month (sums to 100):")
    print(vcontrib.round(1).T.to_string())
    print("Monsoon (Jun-Sep) share: %.1f%% | rest of year: %.1f%%" % (monsoon_share, 100.0 - monsoon_share))

    # ---------- correlations GHI vs rain
    doy = daily.index.dayofyear
    anom = daily - daily.groupby(doy).transform("mean")
    raw_p = daily["ghi_kwh_m2"].corr(daily["rain_mm"])
    anom_p = anom["ghi_kwh_m2"].corr(anom["rain_mm"])
    anom_s = stats.spearmanr(anom["ghi_kwh_m2"].values, anom["rain_mm"].values)[0]

    mg_s = mg["v"]
    mr_s = mr["v"]
    mg_anom = mg_s - mg_s.groupby(mg_s.index.month).transform("mean")
    mr_anom = mr_s - mr_s.groupby(mr_s.index.month).transform("mean")
    monthly_anom_p = mg_anom.corr(mr_anom)

    ann_r, ann_p = stats.pearsonr(I.values, ann["rain_mm_total"].values)
    ms_ghi = M[[6, 7, 8, 9]].sum(axis=1).values
    ms_rain = R[[6, 7, 8, 9]].sum(axis=1).values
    ms_r, ms_p = stats.pearsonr(ms_ghi, ms_rain)

    corr = pd.DataFrame([
        ["daily, raw (includes seasonal cycle)", raw_p, np.nan],
        ["daily anomalies (seasonality removed), Pearson", anom_p, np.nan],
        ["daily anomalies (seasonality removed), Spearman", anom_s, np.nan],
        ["monthly anomalies, Pearson", monthly_anom_p, np.nan],
        ["annual GHI vs annual rain (n=20), Pearson", ann_r, ann_p],
        ["monsoon GHI vs monsoon rain (n=20), Pearson", ms_r, ms_p],
    ], columns=["pair: GHI vs rainfall", "correlation", "p_value"])
    corr.to_csv(C.OUT_DIR / "task1_correlations.csv", index=False, encoding="utf-8")
    print("\nCorrelation of irradiance (GHI) with rainfall:")
    print(corr.round(3).to_string(index=False))

    # ---------- distribution and trend of the annual index
    pcts = {("p%d" % p): float(np.percentile(I.values, p)) for p in (5, 10, 20, 25, 50)}
    sh_p = float(stats.shapiro(I.values)[1])
    lr = stats.linregress(I.index.values.astype(float), I.values)
    trend_pct_decade = float(lr.slope * 10.0 / I.mean() * 100.0)
    print("\nAnnual index (kWh/m2/year): mean %.1f | std %.1f | CV %.2f%% | min %.1f (%d) | max %.1f (%d)"
          % (I.mean(), I.std(ddof=1), I.std(ddof=1) / I.mean() * 100.0, I.min(), I.idxmin(), I.max(), I.idxmax()))
    print("Percentiles:", {k: round(v, 1) for k, v in pcts.items()})
    print("Shapiro-Wilk normality p-value: %.3f (above 0.05 = no evidence against normality)" % sh_p)
    print("Linear trend: %.2f%% of mean per decade (p = %.3f)" % (trend_pct_decade, lr.pvalue))

    # ---------- link to the technical assumptions
    spec_yield = C.AEP50_KWH / C.CAPACITY_KVA
    implied_ghi = C.AEP50_KWH / (C.CAPACITY_KVA * C.PR)
    print("\nTechnical consistency check (assuming 1 kVA ~ 1 kWp):")
    print("  Specific yield implied by AEP50: %.0f kWh/kWp/year" % spec_yield)
    print("  Horizontal irradiation needed for that at PR %.2f: %.0f kWh/m2/year" % (C.PR, implied_ghi))
    print("  ERA5-Land mean annual irradiation: %.0f kWh/m2/year (ratio ERA5 / needed = %.2f)"
          % (I.mean(), I.mean() / implied_ghi))
    print("  The proxy generation model rescales the index so its 20-year mean equals AEP50 (4,600 kWh).")

    save_json({
        "annual_index_mean": I.mean(), "annual_index_std": I.std(ddof=1), "annual_index_cv_pct": I.std(ddof=1) / I.mean() * 100,
        "percentiles": pcts, "shapiro_p": sh_p, "trend_pct_per_decade": trend_pct_decade, "trend_p_value": lr.pvalue,
        "monsoon_variance_share_pct": monsoon_share,
        "corr_daily_raw": raw_p, "corr_daily_anomaly_pearson": anom_p, "corr_daily_anomaly_spearman": anom_s,
        "corr_monthly_anomaly": monthly_anom_p, "corr_annual": ann_r, "corr_annual_p": ann_p,
        "implied_specific_yield": spec_yield, "implied_required_ghi": implied_ghi, "era5_over_required": I.mean() / implied_ghi,
    }, C.OUT_DIR / "task1_stats.json")

    # ---------- figures
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(MONTHS, clim["ghi_kwh_m2_per_month"], color="#e8a317", label="Irradiation (kWh/m2/month)")
    ax.set_ylabel("Irradiation (kWh/m2/month)")
    ax2 = ax.twinx()
    ax2.plot(MONTHS, clim["rain_mm_per_month"], color="#1f4e9c", marker="o", label="Rainfall (mm/month)")
    ax2.set_ylabel("Rainfall (mm/month)")
    ax.set_title("Monthly climatology 2005-2024: irradiation falls when rain rises")
    savefig(fig, "fig_task1_monthly_climatology.png")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(I.index, I.values, color="#e8a317")
    ax.axhline(I.mean(), color="k", ls="--", label="20-year mean")
    ax.plot(I.index, lr.intercept + lr.slope * I.index.values, color="#1f4e9c", label="linear trend")
    ax.set_ylim(I.min() * 0.97, I.max() * 1.02)
    ax.set_xlabel("Year")
    ax.set_ylabel("Annual irradiation (kWh/m2)")
    ax.set_title("Annual index by year")
    ax.legend()
    savefig(fig, "fig_task1_annual_index.png")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(MONTHS, vcontrib["share_of_annual_variance_pct"], color="#2e8b57")
    ax.set_ylabel("% of annual variance")
    ax.set_title("Which months drive year-to-year variation of the annual index")
    savefig(fig, "fig_task1_variance_by_month.png")
    print("\nTask 1 outputs saved.")


if __name__ == "__main__":
    main()
