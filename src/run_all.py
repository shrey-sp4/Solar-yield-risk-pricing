"""
Run the whole analysis in order (steps 2-6). Each script's console output is saved to outputs/logs/.

    python run_all.py                 # steps 2-6 (data already in data/)
    python run_all.py --download      # also runs step 1 first (CDS download, slow)
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = [
    "02_prepare_data.py",
    "03_task1_index_selection.py",
    "04_task2_product_design.py",
    "05_task3_pricing.py",
    "06_task4_critique.py",
]


def check_packages():
    missing = []
    for mod in ("numpy", "pandas", "scipy", "matplotlib", "xarray", "netCDF4"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        sys.exit("Missing packages: %s\nRun:  python -m pip install cdsapi xarray netCDF4 pandas numpy scipy matplotlib"
                 % ", ".join(missing))


def main():
    check_packages()
    logs = ROOT / "outputs" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")

    if "--download" in sys.argv:
        print(">>> Running 01_download.py (this can take an hour)")
        r = subprocess.run([sys.executable, "01_download.py"], cwd=ROOT, env=env)
        if r.returncode != 0:
            sys.exit("01_download.py failed. Fix the error above and re-run.")

    for s in SCRIPTS:
        print("\n>>> Running %s" % s)
        t0 = time.time()
        r = subprocess.run([sys.executable, s], cwd=ROOT, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print(r.stdout)
        if r.stderr.strip():
            print(r.stderr)
        (logs / (s.replace(".py", "") + ".txt")).write_text(r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr.strip() else ""),
                                                           encoding="utf-8")
        if r.returncode != 0:
            sys.exit("\n%s FAILED (exit code %d). Copy the message above and send it to me." % (s, r.returncode))
        print("<<< %s finished in %.1fs" % (s, time.time() - t0))

    print("\nALL STEPS COMPLETED. Results: outputs/ (tables, logs), figures/ (PNG). Next: python make_zip.py")


if __name__ == "__main__":
    main()
