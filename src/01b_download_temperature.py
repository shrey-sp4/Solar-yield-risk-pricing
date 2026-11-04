"""Download ERA5-Land 2 m temperature at 11:30 and 14:30 IST (= 06:00 and 09:00 UTC).
Only missing 5-year blocks are downloaded. Safe to stop and re-run."""
from pathlib import Path
import cdsapi
import xarray as xr

DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)
AREA = [23.13, 72.46, 22.93, 72.66]          # N, W, S, E (same box as the irradiance download)
BLOCKS = [(2005, 2009), (2010, 2014), (2015, 2019), (2020, 2024)]
TIMES = ["06:00", "09:00"]


def fetch(client, years, times, target):
    tmp = target.with_suffix(".part")
    client.retrieve("reanalysis-era5-land", {
        "variable": ["2m_temperature"],
        "year": [str(y) for y in years],
        "month": [f"{m:02d}" for m in range(1, 13)],
        "day": [f"{d:02d}" for d in range(1, 32)],
        "time": times,
        "area": AREA,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }, str(tmp))
    tmp.replace(target)


def main():
    client = cdsapi.Client()
    for a, b in BLOCKS:
        final = DATA / f"temp_2m_{a}-{b}.nc"
        if final.exists() and final.stat().st_size > 10000:
            print(f"skip {final.name} (already downloaded)")
            continue
        years = range(a, b + 1)
        print(f"requesting {a}-{b} (both times) ...", flush=True)
        try:
            fetch(client, years, TIMES, final)
        except Exception as e:
            print(f"  combined request failed ({str(e)[:120]}); retrying one time at a time", flush=True)
            parts = []
            for t in TIMES:
                p = DATA / f"temp_part_{a}-{b}_{t[:2]}.nc"
                if not p.exists():
                    fetch(client, years, [t], p)
                parts.append(p)
            dsets = [xr.open_dataset(p).load() for p in parts]
            tdim = "valid_time" if "valid_time" in dsets[0].dims else "time"
            xr.concat(dsets, dim=tdim).sortby(tdim).to_netcdf(final)
            for d in dsets:
                d.close()
            for p in parts:
                p.unlink()
        print(f"  saved {final.name}", flush=True)
    print("TEMPERATURE DOWNLOAD COMPLETE")


if __name__ == "__main__":
    main()