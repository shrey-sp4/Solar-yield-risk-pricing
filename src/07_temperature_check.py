"""Does temperature change the picture? Evidence test only - the contract index stays irradiance-only.
Method: generation_year = sum over days of GHI x (1 + gamma x (T_midday - T_ref)), rescaled so the
20-year mean = AEP50. T_ref = GHI-weighted mean temperature, so the AVERAGE heat loss is already
inside the 80% PR and only the year-to-year anomaly matters."""
import glob, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent
try:
    import config as cfg
except Exception:
    cfg = None


def cget(name, default):
    return getattr(cfg, name, default)


TRIGGER = cget("TRIGGER_PCT_OF_MEAN", 0.99)
CAP_PCT = cget("CAP_PCT_OF_SAVINGS", 0.10)
EXIT_PCTL = cget("EXIT_PERCENTILE", 5)
AEP50, TARIFF, TARGET_LR, LOAD = 4600.0, 5.75, 0.65, 0.5
SAVINGS = AEP50 * TARIFF
COEFS = [-0.002, -0.003, -0.004, -0.005]     # change in output per degC (typical silicon: -0.3 to -0.5 %/degC)
BASE_COEF = -0.004

print("=" * 72 + "\nSTEP 7: TEMPERATURE CHECK (evidence only)\n" + "=" * 72)

# ---------- load data ----------
files = sorted(glob.glob(str(ROOT / "data" / "temp_2m_*.nc")))
if not files:
    raise SystemExit("No data/temp_2m_*.nc files found. Run 01b_download_temperature.py first.")
series = []
for f in files:
    ds = xr.open_dataset(f)
    da = ds["t2m"]
    tdim = "valid_time" if "valid_time" in da.dims else "time"
    other = [d for d in da.dims if d != tdim]
    s = da.mean(other).to_series() - 273.15
    s.index = pd.to_datetime(s.index)
    series.append(s)
    ds.close()
t = pd.concat(series).sort_index()
tday = t.groupby(t.index.normalize()).mean().rename("t_mid_c")
print(f"Temperature files: {len(files)} | readings: {len(t)} | days: {len(tday)}")

d = pd.read_csv(ROOT / "outputs" / "daily.csv")
datecol = next((c for c in d.columns if c.lower() in ("date", "time", "day", "valid_time")), d.columns[0])
ghicol = next((c for c in d.columns if "ghi" in c.lower() or "ssrd" in c.lower()), None)
if ghicol is None:
    raise SystemExit(f"Cannot find the irradiance column in outputs/daily.csv. Columns: {list(d.columns)}")
d[datecol] = pd.to_datetime(d[datecol]).dt.normalize()
ghi = d.set_index(datecol)[ghicol].rename("ghi")
df = pd.concat([ghi, tday], axis=1, join="inner").dropna()
df["year"] = df.index.year
print(f"Days with both irradiance and temperature: {len(df)} (expected 7305) | irradiance column used: {ghicol}")

ai = pd.read_csv(ROOT / "outputs" / "annual_index.csv", index_col=0)
idx = ai["index_kwh_m2"].astype(float)
idx.index = idx.index.astype(int)
years = list(idx.index)
df = df[df["year"].isin(years)]

# ---------- temperature facts ----------
tyear = df.groupby("year")["t_mid_c"].mean().reindex(years)
tref = float(np.average(df["t_mid_c"], weights=df["ghi"]))
tanom = tyear - tyear.mean()
slope = np.polyfit(years, tyear.values, 1)[0] * 10
corr_ti = float(np.corrcoef(idx.values, tyear.values)[0, 1])
print(f"\nMidday temperature (11:30/14:30 IST): mean {tyear.mean():.1f} C | yearly std {tyear.std():.2f} C | "
      f"range {tyear.min():.1f} to {tyear.max():.1f} C | trend {slope:+.2f} C/decade")
print(f"GHI-weighted reference temperature: {tref:.1f} C")
print(f"Correlation, annual irradiance vs annual midday temperature: {corr_ti:+.2f} (n=20)")


# ---------- contract maths (same rules as scripts 04/05) ----------
def price(ix):
    ix = pd.Series(ix, dtype=float)
    mean = ix.mean()
    trig = TRIGGER * mean
    ex = float(np.percentile(ix, EXIT_PCTL))
    if ex >= trig:
        ex = trig - 0.01 * mean
    cap = CAP_PCT * SAVINGS
    pay = cap * np.clip((trig - ix) / (trig - ex), 0, 1)
    burn, sd = float(pay.mean()), float(pay.std())
    prem = math.ceil(max(burn / TARGET_LR, burn + LOAD * sd) / 10) * 10 if burn > 0 else 0
    return dict(trigger=trig, exit=ex, pay=pay, burn=burn, std=sd, premium=prem, paying=int((pay > 0).sum()))


base = price(idx)
print(f"\nSanity check, irradiance-only contract: trigger {base['trigger']:.1f} | exit {base['exit']:.1f} | "
      f"years paying {base['paying']} | burn Rs {base['burn']:.1f} | premium Rs {base['premium']}")
print("  (must match the premium printed by 05_task3_pricing.py)")

gen0 = idx / idx.mean() * AEP50
rows, store = [], {}
for g in COEFS:
    raw = (df["ghi"] * (1 + g * (df["t_mid_c"] - tref))).groupby(df["year"]).sum().reindex(years)
    gen = raw / raw.mean() * AEP50
    idx_c = gen / AEP50 * idx.mean()                     # temperature-aware index in kWh/m2 equivalents
    pc = price(idx_c)
    diff_pct = (gen - gen0) / AEP50 * 100
    pay_diff = (pc["pay"] - base["pay"]).abs()
    rows.append(dict(
        coef_pct_per_C=g * 100,
        cv_irradiance_only_pct=gen0.std() / gen0.mean() * 100,
        cv_with_temperature_pct=gen.std() / gen.mean() * 100,
        corr_with_irradiance_only=float(np.corrcoef(gen0, gen)[0, 1]),
        max_abs_yearly_diff_pct=float(diff_pct.abs().max()),
        years_paying_corrected=pc["paying"],
        years_decision_differs=int(((pc["pay"] > 0) != (base["pay"] > 0)).sum()),
        mean_abs_payout_diff_rs=float(pay_diff.mean()),
        burn_cost_rs=pc["burn"],
        premium_rs=pc["premium"],
        premium_change_pct=(pc["premium"] / base["premium"] - 1) * 100 if base["premium"] else np.nan,
    ))
    store[g] = (gen, diff_pct)

res = pd.DataFrame(rows)
pd.set_option("display.width", 220)
print("\nEffect of temperature on annual generation, by assumed temperature coefficient:")
print(res.round(2).to_string(index=False))

gen_b, diff_b = store[BASE_COEF]
worst = diff_b.abs().idxmax()
print(f"\nBase case (coefficient {BASE_COEF*100:.1f} %/C): temperature changes yearly generation by at most "
      f"{diff_b.abs().max():.2f}% of AEP50 (year {worst}); irradiance alone moves it by "
      f"{(gen0.std()/gen0.mean()*100):.2f}% (1 std dev).")
b = res[res.coef_pct_per_C == BASE_COEF * 100].iloc[0]
print(f"Correlation of the temperature-corrected series with the irradiance-only series: {b.corr_with_irradiance_only:.3f}")
print(f"If the contract were written on the temperature-corrected index: premium Rs {b.premium_rs:.0f} "
      f"vs Rs {base['premium']} ({b.premium_change_pct:+.1f}%), payout decision changes in {int(b.years_decision_differs)} of 20 years.")
print("READ-OUT: if the difference is small relative to the irradiance swings, keep the index irradiance-only "
      "and report this table as the justification; if it is large, say so in the report as a limitation.")

# ---------- save ----------
(ROOT / "outputs").mkdir(exist_ok=True)
(ROOT / "figures").mkdir(exist_ok=True)
res.to_csv(ROOT / "outputs" / "task1_temperature_check.csv", index=False)
pd.DataFrame({"year": years, "midday_temp_c": tyear.values, "irradiance_kwh_m2": idx.values,
              "gen_irradiance_only_kwh": gen0.values, "gen_with_temp_kwh": gen_b.values,
              "diff_pct_of_aep50": diff_b.values}).to_csv(ROOT / "outputs" / "temperature_annual.csv", index=False)
with open(ROOT / "outputs" / "temperature_check.json", "w") as fh:
    json.dump(dict(mean_midday_temp_c=float(tyear.mean()), temp_std_c=float(tyear.std()),
                   trend_c_per_decade=float(slope), corr_irradiance_temp=corr_ti,
                   base_coef_pct_per_c=BASE_COEF * 100, max_abs_yearly_diff_pct=float(diff_b.abs().max()),
                   base_premium_rs=base["premium"], premium_with_temp_rs=float(b.premium_rs),
                   decision_changes_years=int(b.years_decision_differs)), fh, indent=2)

fig, ax = plt.subplots(1, 2, figsize=(11, 4))
ax[0].scatter(tanom.values, (idx / idx.mean() * 100 - 100).values)
for y in years:
    ax[0].annotate(str(y)[2:], (tanom[y], idx[y] / idx.mean() * 100 - 100), fontsize=7)
ax[0].set_xlabel("Midday temperature anomaly (C)")
ax[0].set_ylabel("Irradiance anomaly (% of mean)")
ax[0].set_title(f"Hot years vs sunny years (corr {corr_ti:+.2f})")
ax[1].plot(years, gen0.values, marker="o", label="Irradiance only")
ax[1].plot(years, gen_b.values, marker="s", label=f"With temperature ({BASE_COEF*100:.1f} %/C)")
ax[1].set_xlabel("Year")
ax[1].set_ylabel("Proxy generation (kWh)")
ax[1].set_title("Effect of temperature on annual generation")
ax[1].legend()
fig.tight_layout()
fig.savefig(ROOT / "figures" / "fig_task1_temperature.png", dpi=150)
print("\nSaved: outputs/task1_temperature_check.csv, temperature_annual.csv, temperature_check.json, figures/fig_task1_temperature.png")
