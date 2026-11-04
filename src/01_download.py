"""
Step 1 (optional if data/ already holds the 5 daily files): download ERA5-Land daily SSRD + precipitation.

Method: ERA5-Land accumulations reset at 00:00 UTC, so the 00:00 value of day D+1 is the total of day D.
One timestamp per day therefore gives daily totals and keeps the request small.

Your CDS key must be in  C:\\Users\\<you>\\.cdsapirc  (already set up). The key is never written to any project file.
"""
import os
import sys
from pathlib import Path

import config as C


def block_file(y0, y1):
    return C.DATA_DIR / ("daily_ssrd_tp_%d-%d.nc" % (y0, y1))


def block_done(y0, y1):
    f = block_file(y0, y1)
    if f.exists() and f.stat().st_size > 1000:
        return True
    # fallback layout: one file per year
    return all(block_file(y, y).exists() and block_file(y, y).stat().st_size > 1000
               for y in range(y0, y1 + 1))


def request(client, years, target):
    tmp = Path(str(target) + ".part")
    client.retrieve(
        "reanalysis-era5-land",
        {
            "variable": ["surface_solar_radiation_downwards", "total_precipitation"],
            "year": [str(y) for y in years],
            "month": ["%02d" % m for m in range(1, 13)],
            "day": ["%02d" % d for d in range(1, 32)],
            "time": ["00:00"],
            "area": C.AREA,
            "data_format": "netcdf",
            "download_format": "unarchived",
        },
        str(tmp),
    )
    tmp.replace(target)
    print("  done:", target.name)


def main():
    try:
        import cdsapi
    except ImportError:
        sys.exit("cdsapi is not installed. Run:  python -m pip install cdsapi")

    rc = Path.home() / ".cdsapirc"
    if not rc.exists() and not os.environ.get("CDSAPI_KEY"):
        sys.exit("CDS key file not found at %s.\nCreate it with your personal token (see the earlier instructions)." % rc)

    todo = [(y0, y1) for (y0, y1) in C.DOWNLOAD_BLOCKS if not block_done(y0, y1)]
    for (y0, y1) in C.DOWNLOAD_BLOCKS:
        if (y0, y1) not in todo:
            print("exists:", block_file(y0, y1).name)
    if not todo:
        print("All files already present. Nothing to download.")
        return

    client = cdsapi.Client()
    for (y0, y1) in todo:
        print("Requesting %d-%d (queue time can be 10-20 min)..." % (y0, y1))
        try:
            request(client, list(range(y0, y1 + 1)), block_file(y0, y1))
        except Exception as e:  # noqa
            msg = str(e).lower()
            if "too large" in msg or "cost limits" in msg:
                print("  block too large, splitting into single years...")
                for y in range(y0, y1 + 1):
                    if not (block_file(y, y).exists() and block_file(y, y).stat().st_size > 1000):
                        request(client, [y], block_file(y, y))
            else:
                raise
    print("Download finished.")


if __name__ == "__main__":
    main()
