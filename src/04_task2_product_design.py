"""
Step 4 - Task 2: product definition. Trigger, exit, tick and cap are derived from the choices in config.py.

Outputs: outputs/product_spec.json, outputs/product_spec.md, figures/fig_task2_payout_curve.png
"""
import numpy as np
import matplotlib.pyplot as plt

import config as C
from utils import banner, load_annual, make_design, payout, save_json, savefig


def main():
    banner("STEP 4 (TASK 2): PRODUCT DESIGN")
    ann = load_annual()
    I = ann["index_kwh_m2"].values
    years = ann.index.values
    cap = C.CAP_PCT_OF_SAVINGS * C.ANNUAL_SAVINGS_P50
    d = make_design(I, C.TRIGGER_PCT_OF_MEAN, C.EXIT_PERCENTILE, cap, C.MIN_BAND_PCT_OF_MEAN)
    mean_i, trig, ex = d["mean_index"], d["trigger"], d["exit"]

    loss_at = lambda x: max(0.0, 1.0 - x / mean_i) * C.ANNUAL_SAVINGS_P50
    loss_trig, loss_exit = loss_at(trig), loss_at(ex)
    pay_hist = payout(I, trig, ex, cap)
    n_trig = int((pay_hist > 0).sum())
    freq_exit = float((I <= ex).mean())

    print("Annual savings at P50 = %.0f kWh x Rs %.2f = Rs %.2f" % (C.AEP50_KWH, C.TARIFF, C.ANNUAL_SAVINGS_P50))
    print("Index = annual surface solar radiation downwards (kWh/m2), mean of surrounding ERA5-Land cells")
    print("20-year mean index        : %.1f kWh/m2" % mean_i)
    print("Trigger (%.0f%% of mean)    : %.1f kWh/m2" % (C.TRIGGER_PCT_OF_MEAN * 100, trig))
    print("Exit (P%d of 20 years)      : %.1f kWh/m2 (%.1f%% of mean)%s"
          % (C.EXIT_PERCENTILE, ex, ex / mean_i * 100, "  <- FALLBACK APPLIED" if d["fallback_used"] else ""))
    if d["fallback_used"]:
        print("  NOTE: the 5th percentile (%.1f) is too close to or above the trigger, so exit was set to trigger minus %.0f%% of the mean."
              % (d["exit_percentile_value"], C.MIN_BAND_PCT_OF_MEAN * 100))
        print("  In the report: state that 20 years of data are too few to separate a 95%% trigger from a P%d exit." % C.EXIT_PERCENTILE)
    print("Maximum payout            : Rs %.2f (%.0f%% of savings)" % (cap, C.CAP_PCT_OF_SAVINGS * 100))
    print("Tick value                : Rs %.1f per kWh/m2 shortfall  (= Rs %.1f per 1%% of mean index)"
          % (d["tick_rs_per_kwh_m2"], d["tick_rs_per_kwh_m2"] * 0.01 * mean_i))
    print("Years with payout > 0     : %d of %d | years at/below exit: %.0f%%" % (n_trig, len(I), freq_exit * 100))
    print("\nOver-compensation check (modelled loss = savings lost if generation falls with the index):")
    print("  At the trigger the modelled loss is Rs %.0f; at the exit it is Rs %.0f; the maximum payout is Rs %.0f."
          % (loss_trig, loss_exit, cap))
    ratio = cap / loss_exit if loss_exit > 0 else float("inf")
    print("  Maximum payout is %.1f x the modelled loss at the exit point." % ratio)
    print("  (A smaller CAP_PCT_OF_SAVINGS in config.py lowers this ratio and the premium.)")

    spec = dict(d)
    spec.update({
        "pincode": C.PINCODE, "lat": C.LAT, "lon": C.LON,
        "index_definition": "Annual (1 Jan-31 Dec) sum of ERA5-Land surface solar radiation downwards, kWh/m2, mean of surrounding grid cells",
        "trigger_pct_of_mean": C.TRIGGER_PCT_OF_MEAN, "exit_percentile": C.EXIT_PERCENTILE,
        "cap_pct_of_savings": C.CAP_PCT_OF_SAVINGS, "annual_savings_p50_rs": C.ANNUAL_SAVINGS_P50,
        "modelled_loss_at_trigger_rs": loss_trig, "modelled_loss_at_exit_rs": loss_exit,
        "cap_over_loss_at_exit": ratio, "years_with_payout": n_trig,
    })
    save_json(spec, C.OUT_DIR / "product_spec.json")

    md = []
    md.append("# Product specification (draft): Solar Yield Parametric Cover\n")
    md.append("- **Insured:** 3 kVA grid-connected rooftop solar system, pincode %d (Ahmedabad)" % C.PINCODE)
    md.append("- **Index:** annual (1 Jan - 31 Dec) total of ERA5-Land surface solar radiation downwards, in kWh/m2, averaged over the surrounding grid cells")
    md.append("- **Trigger:** %.1f kWh/m2 (%.0f%% of the 2005-2024 mean of %.1f kWh/m2)" % (trig, C.TRIGGER_PCT_OF_MEAN * 100, mean_i))
    md.append("- **Exit:** %.1f kWh/m2 (%s)" % (ex, "5th percentile of 2005-2024 annual values" if not d["fallback_used"] else "trigger minus 1%% of the mean (fallback)"))
    md.append("- **Payout:** linear between trigger and exit: Rs %.1f per kWh/m2 below the trigger" % d["tick_rs_per_kwh_m2"])
    md.append("- **Maximum payout:** Rs %.2f (%.0f%% of annual savings at P50 = Rs %.2f)" % (cap, C.CAP_PCT_OF_SAVINGS * 100, C.ANNUAL_SAVINGS_P50))
    md.append("- **Formula:** payout = min(Rs %.2f, max(0, %.1f x (%.1f - index)))" % (cap, d["tick_rs_per_kwh_m2"], trig))
    md.append("- **Settlement:** once the full year of ERA5-Land data is available; no claim filing, no loss adjustment")
    with open(C.OUT_DIR / "product_spec.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    xs = np.linspace(min(I.min(), ex) * 0.97, max(I.max(), trig) * 1.02, 300)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(xs, payout(xs, trig, ex, cap), color="#1f4e9c", lw=2)
    ax.scatter(I, pay_hist, color="#c0392b", zorder=3, label="2005-2024 years")
    for x, lab in ((trig, "trigger"), (ex, "exit")):
        ax.axvline(x, color="grey", ls="--")
        ax.text(x, cap * 1.02, lab, ha="center")
    ax.set_xlabel("Annual index (kWh/m2)")
    ax.set_ylabel("Payout (Rs)")
    ax.set_title("Payout function and historical years")
    ax.legend()
    savefig(fig, "fig_task2_payout_curve.png")
    print("\nSaved: outputs/product_spec.json, product_spec.md")


if __name__ == "__main__":
    main()
