"""Shared helpers. No editing needed."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as C

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def banner(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def save_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=_json_default)


def load_json(path):
    path = Path(path)
    if not path.exists():
        sys.exit("Missing file: %s\nRun the earlier scripts first (python run_all.py)." % path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_annual():
    p = C.OUT_DIR / "annual_index.csv"
    if not p.exists():
        sys.exit("Missing %s. Run 02_prepare_data.py first." % p)
    return pd.read_csv(p, index_col="year")


def payout(index, trigger, exit_, cap):
    """Linear, capped payout: 0 at/above trigger, cap at/below exit."""
    index = np.asarray(index, dtype=float)
    frac = np.clip((trigger - index) / (trigger - exit_), 0.0, 1.0)
    return cap * frac


def make_design(index_values, trigger_pct, exit_pct, cap_rs, min_band_pct):
    """Derive trigger / exit / tick from the historical annual index values."""
    I = np.asarray(index_values, dtype=float)
    mean_i = float(I.mean())
    trigger = trigger_pct * mean_i
    exit_raw = float(np.percentile(I, exit_pct))
    min_band = min_band_pct * mean_i
    fallback = exit_raw > trigger - min_band
    exit_ = trigger - min_band if fallback else exit_raw
    return {
        "mean_index": mean_i,
        "trigger": float(trigger),
        "exit_percentile_value": exit_raw,
        "exit": float(exit_),
        "fallback_used": bool(fallback),
        "cap": float(cap_rs),
        "tick_rs_per_kwh_m2": float(cap_rs / (trigger - exit_)),
    }


def savefig(fig, name):
    path = C.FIG_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  saved figure:", path.name)
