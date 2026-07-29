"""
Central configuration for PP PropertyLens.
Import from here instead of hard-coding paths or numbers anywhere else.
"""

from pathlib import Path

# ------------------------------------------------------------------ paths
ROOT = Path(__file__).parent.parent

BRONZE_DIR = ROOT / "data" / "bronze"
SILVER_DIR = ROOT / "data" / "silver"
GOLD_DIR = ROOT / "data" / "gold"
GEO_DIR = ROOT / "data" / "geo"
CONFIG_DIR = ROOT / "config"
MODEL_DIR = ROOT / "models"
FIGURE_DIR = ROOT / "outputs" / "figures"
REPORT_DIR = ROOT / "outputs" / "reports"

RE_HTML_DIR = BRONZE_DIR / "realestate" / "html"
K24_HTML_DIR = BRONZE_DIR / "khmer24" / "html"

RE_RAW_JSON = BRONZE_DIR / "realestate" / "raw_listings.json"
K24_RAW_JSON = BRONZE_DIR / "khmer24" / "raw_listings.json"

CLEANED_CSV = SILVER_DIR / "cleaned_listings.csv"
MODEL_READY_CSV = GOLD_DIR / "model_ready.csv"

DISTRICT_MAPPING = CONFIG_DIR / "district_mapping.csv"
LANDMARKS = CONFIG_DIR / "landmarks.csv"

# --------------------------------------------------------------- scraping
REQUEST_DELAY_SECONDS = 2.5      # be polite - do not lower this
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# --------------------------------------------------------------- cleaning
# A listing is treated as RENT (not sale) below this price
SALE_PRICE_FLOOR_USD = 5_000
# Sanity bounds - anything outside is inspected manually, not silently dropped
MIN_SIZE_M2 = 15
MAX_SIZE_M2 = 800
OUTLIER_LOW_PCT = 0.01
OUTLIER_HIGH_PCT = 0.99

# Duplicate detection tolerances
DUP_SIZE_TOLERANCE_M2 = 2.0
DUP_PRICE_TOLERANCE_PCT = 0.03

# --------------------------------------------------------------- modelling
TARGET = "log_price"
TEST_SIZE = 0.20
RANDOM_STATE = 42
N_FOLDS = 5                       # for K-fold target encoding
MIN_LISTINGS_PER_DISTRICT = 30    # below this -> grouped as "Other"
