"""
Central configuration for the parametric solar insurance
Edit values HERE only. All other scripts read from this file.
"""
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"
FIG_DIR = ROOT / "figures"
PROMPTS_DIR = ROOT / "prompts"
REPORT_DIR = ROOT / "report"
for _d in (DATA_DIR, OUT_DIR, FIG_DIR):
    _d.mkdir(exist_ok=True)

# ------------------------------------------------------------- location
PINCODE = 380006                 # Ellisbridge / Ambawadi S.O., Ahmedabad
LAT, LON = 23.026, 72.562        # Ellisbridge S.O. centroid (verified from public geocoding sources)
# Download box [North, West, South, East]. Identical to the box already downloaded.
# ERA5-Land grid is 0.1 deg, so this box returns the grid cells surrounding the pincode
# (lat 23.0 / 23.1 and lon 72.5 / 72.6 = 4 cells).
AREA = [23.13, 72.46, 22.93, 72.66]

# --------------------------------------------------------------- period
START_YEAR, END_YEAR = 2005, 2024
# 1 Jan 2025 00:00 UTC holds the total of 31 Dec 2024, hence the 2025 file.
DOWNLOAD_BLOCKS = [(2005, 2009), (2010, 2014), (2015, 2019), (2020, 2024), (2025, 2025)]

# ------------------------------------------------- technical assumptions
CAPACITY_KVA = 3
PR = 0.80
AEP50_KWH = 4600                 # kWh / year (P50)
TARIFF = 5.75                    # Rs / kWh
INSTALL_COST = 250000            # Rs
ANNUAL_SAVINGS_P50 = AEP50_KWH * TARIFF   # = Rs 26,450

# ------------------------------------------------------- product design
TRIGGER_PCT_OF_MEAN = 0.99       # trigger = 99% of the 2005-2024 mean annual index
EXIT_PERCENTILE = 5              # exit    = 5th percentile of the 20 annual index values
CAP_PCT_OF_SAVINGS = 0.10        # max payout = 10% of annual savings at P50
MIN_BAND_PCT_OF_MEAN = 0.01      # safety: trigger - exit is never narrower than 1% of the mean

# -------------------------------------------------------------- pricing
TARGET_LOSS_RATIO = 0.65         # premium (method 1) = burn cost / 0.65
SD_LOADING_K = 0.5               # premium (method 2) = burn cost + 0.5 * std dev of annual payout
PREMIUM_ROUNDING = 10            # round recommended premium UP to nearest Rs 10
N_BOOTSTRAP = 10000
N_SIM = 200000
SEED = 42

# ----------------------------------------------------- Task 4 assumptions
N_CUSTOMERS = 10000
LOCAL_SD_PCT = 0.02              # ASSUMPTION: std dev of a rooftop's annual weather deviation from the grid index
LOCAL_SD_SENSITIVITY = [0.01, 0.02, 0.03, 0.05]
NONWEATHER_PROB = 0.05           # ASSUMPTION: share of customers hit per year by inverter/soiling/shading/outage
NONWEATHER_LOSS_RANGE = (0.10, 0.40)   # ASSUMPTION: generation lost in such an event (uniform)
MATERIAL_LOSS_PCT = 0.05         # a "material" loss = 5% of annual savings (Rs 1,322.50)
