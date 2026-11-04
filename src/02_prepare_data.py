"""
Step 2: build the daily and annual tables from the downloaded ERA5-Land files.

Outputs (outputs/):
  daily.csv               daily GHI (kWh/m2, mean of surrounding cells) and rain (mm)
  daily_ghi_by_cell.csv   daily GHI for every grid cell
  annual_index.csv        ANNUAL INDEX (kWh/m2/year) per year: pooled mean, each cell, plus annual rain
  data_summary.json
"""
import sys

import numpy as np
import pandas as pd
import xarray as xr

import config as C
from utils import banner, save_json


def coord_names(da):
    t = next((n for n in ("valid_time", "time") if n in da.dims), None)
    la = next((n for n in ("latitude", "lat") if n in da.dims), None)
    lo = next((n for n in ("longitude", "lon") if n in da.dims), None)
    if t is None or la is None or lo is None:
        raise ValueError("Unexpected dimensions %s (need time, latitude, longitude)" % (list(da.dims),))
    return t, la, lo


def read_var(path, var):
    """Return (times, lats, lons, values[t, lat, lon]) for one variable of one NetCDF file."""
    with xr.open_dataset(path) as ds:
        if var not in ds.variables:
            raise KeyError("Variable '%s' not found in %s. Variables present: %s"
                           % (var, path.name, list(ds.data_vars)))
        da = ds[var]
        if "expver" in da.dims:                 # ERA5T/ERA5 mixture: take whichever is non-missing
            da = da.mean("expver", skipna=True)
        if "number" in da.dims:
            da = da.isel(number=0, drop=True)
        t, la, lo = coord_names(da)
        da = da.transpose(t, la, lo)
        times = pd.to_datetime(da[t].values)
        lats = np.round(da[la].values.astype(float), 3)
        lons = np.round(da[lo].values.astype(float), 3)
        vals = da.values.astype("float64")
    return times, lats, lons, vals


def build_frame(pattern, var):
    files = sorted(C.DATA_DIR.glob(pattern))
    if not files:
        sys.exit("No files matching data/%s. Run 01_download.py first." % pattern)
    frames = []
    for f in files:
        times, lats, lons, vals = read_var(f, var)
        cols = ["%.1fN_%.1fE" % (la, lo) for la in lats for lo in lons]
        arr = vals.reshape(len(times), -1)
        frames.append(pd.DataFrame(arr, index=times, columns=cols))
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]
    if not (df.index.hour == 0).all():
        sys.exit("Some timestamps are not 00:00 UTC in %s files. The daily-total method needs 00:00 only." % pattern)
    return df


def validate_accumulation(raw_ssrd_cellmean):
    """Optional check against the hourly January-2005 test file, if it is still in data/."""
    f = C.DATA_DIR / "era5land_2005_m01-01.nc"
    if not f.exists():
        print("  (accumulation check skipped: hourly test file not found - not a problem)")
        return
    try:
        times, lats, lons, vals = read_var(f, "ssrd")
        hourly = pd.Series(vals.reshape(len(times), -1).mean(axis=1), index=times)
        t0 = pd.Timestamp("2005-01-02 00:00")
        before = hourly.get(pd.Timestamp("2005-01-01 23:00"))
        total = hourly.get(t0)
        after = hourly.get(pd.Timestamp("2005-01-02 01:00"))
        daily_val = raw_ssrd_cellmean.get(t0)
        if None in (before, total, after, daily_val):
            print("  (accumulation check skipped: needed timestamps not present)")
            return
        ok1 = abs(total - daily_val) / max(abs(daily_val), 1.0) < 1e-3
        ok2 = before <= total * 1.0001
        ok3 = after < 0.2 * total
        print("  Accumulation check (Jan 2005 hourly vs daily file):")
        print("    23:00 value = %.0f J/m2, 00:00 value = %.0f J/m2, next 01:00 value = %.0f J/m2" % (before, total, after))
        print("    00:00 equals daily-file value: %s | rises to 00:00: %s | resets after 00:00: %s" % (ok1, ok2, ok3))
        if ok1 and ok2 and ok3:
            print("    RESULT: PASS - the 00:00 UTC value is the previous day's total.")
        else:
            print("    RESULT: CHECK - values not as expected (this does not stop the pipeline).")
    except Exception as e:  # noqa
        print("  (accumulation check skipped: %s)" % e)


def main():
    banner("STEP 2: PREPARE DATA")
    ssrd_raw = build_frame("daily_ssrd_tp_*.nc", "ssrd")
    tp_raw = build_frame("daily_ssrd_tp_*.nc", "tp")
    print("Files read. Grid cells found: %d -> %s" % (ssrd_raw.shape[1], list(ssrd_raw.columns)))

    validate_accumulation(ssrd_raw.mean(axis=1))

    # 00:00 UTC of day D+1 holds the total of day D
    ghi = ssrd_raw / 3.6e6                    # J/m2 -> kWh/m2
    rain = tp_raw * 1000.0                    # m -> mm
    ghi.index = ghi.index - pd.Timedelta(days=1)
    rain.index = rain.index - pd.Timedelta(days=1)
    ghi = ghi.clip(lower=0.0)
    rain = rain.clip(lower=0.0)

    expected = pd.date_range("%d-01-01" % C.START_YEAR, "%d-12-31" % C.END_YEAR, freq="D")
    missing = expected.difference(ghi.index)
    if len(missing) > 0:
        sys.exit("Missing %d days (first %s, last %s). Some download blocks are absent or incomplete.\n"
                 "Run:  python 01_download.py   and then re-run this script."
                 % (len(missing), missing[0].date(), missing[-1].date()))
    ghi = ghi.loc[expected]
    rain = rain.loc[expected]

    ghi = ghi.dropna(axis=1, how="all")
    rain = rain[ghi.columns]
    if ghi.isna().any().any() or rain.isna().any().any():
        sys.exit("NaN values found inside the study period. Re-download the affected block (delete its file in data/).")

    # location sanity: the pincode point must lie inside the grid-cell box
    lats = sorted({float(c.split("N_")[0]) for c in ghi.columns})
    lons = sorted({float(c.split("N_")[1].replace("E", "")) for c in ghi.columns})
    inside = (min(lats) <= C.LAT <= max(lats)) and (min(lons) <= C.LON <= max(lons))
    print("Pincode %d point: %.3fN, %.3fE | cell lats %s | cell lons %s | point inside cell box: %s"
          % (C.PINCODE, C.LAT, C.LON, lats, lons, inside))
    if not inside:
        sys.exit("The downloaded cells do not surround the pincode point. Check AREA in config.py and re-download.")

    daily = pd.DataFrame({"ghi_kwh_m2": ghi.mean(axis=1), "rain_mm": rain.mean(axis=1)})
    daily.index.name = "date"
    daily.to_csv(C.OUT_DIR / "daily.csv", encoding="utf-8")
    ghi.index.name = "date"
    ghi.to_csv(C.OUT_DIR / "daily_ghi_by_cell.csv", encoding="utf-8")

    ann_cells = ghi.groupby(ghi.index.year).sum()
    ann_cells.columns = ["cell_" + c for c in ann_cells.columns]
    ann = pd.DataFrame({"index_kwh_m2": ann_cells.mean(axis=1)})
    ann = pd.concat([ann, ann_cells], axis=1)
    ann["rain_mm_total"] = rain.mean(axis=1).groupby(rain.index.year).sum()
    ann["n_days"] = ghi.groupby(ghi.index.year).size()
    ann.index.name = "year"
    ann.to_csv(C.OUT_DIR / "annual_index.csv", encoding="utf-8")

    mean_i = float(ann["index_kwh_m2"].mean())
    print("\nDaily rows: %d (expected %d)" % (len(daily), len(expected)))
    print("Mean daily GHI: %.2f kWh/m2/day | mean annual GHI: %.0f kWh/m2/year" % (daily["ghi_kwh_m2"].mean(), mean_i))
    print("Annual rain (mean): %.0f mm" % ann["rain_mm_total"].mean())
    print("\nAnnual index table (kWh/m2/year):")
    print(ann[["index_kwh_m2", "rain_mm_total", "n_days"]].round(1).to_string())
    if not (1500 <= mean_i <= 2600):
        print("\nWARNING: mean annual GHI %.0f is outside the usual 1500-2600 range for India. Check units." % mean_i)

    save_json({"cells": list(ghi.columns), "n_days": int(len(daily)), "mean_annual_index_kwh_m2": mean_i,
               "point_inside_cell_box": bool(inside)}, C.OUT_DIR / "data_summary.json")
    print("\nSaved: outputs/daily.csv, daily_ghi_by_cell.csv, annual_index.csv, data_summary.json")


if __name__ == "__main__":
    main()
