"""
PP PropertyLens - Project Setup Script
======================================
Run ONCE at the start of the project to create the full folder structure
and starter config files.

Usage:
    python setup_project.py

Run this from inside your project root folder (pp-propertylens/).
Safe to re-run: it never overwrites files that already exist.
"""

import os
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

# ---------------------------------------------------------------- folders
FOLDERS = [
    "config",
    "data/bronze/realestate/html",
    "data/bronze/khmer24/html",
    "data/silver",
    "data/gold",
    "data/geo",
    "src",
    "notebooks",
    "models",
    "backend",
    "frontend",
    "outputs/figures",
    "outputs/reports",
    "docs",
]

# ---------------------------------------------------------------- files
GITIGNORE = """# Python
venv/
__pycache__/
*.pyc
.ipynb_checkpoints/

# Data - too large for git, and raw HTML is huge
data/bronze/
data/silver/
data/gold/

# Trained models
models/*.pkl

# Node
node_modules/
dist/

# Environment
.env
"""

REQUIREMENTS = """pandas
numpy
scikit-learn
xgboost
shap
beautifulsoup4
requests
playwright
matplotlib
seaborn
flask
flask-cors
joblib
rapidfuzz
geopy
jupyter
"""

SETTINGS = '''"""
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
'''

DISTRICT_MAPPING_CSV = """raw_name,standard_name
BKK1,Boeung Keng Kang 1
BKK 1,Boeung Keng Kang 1
Boeung Keng Kang I,Boeung Keng Kang 1
Boeng Keng Kang 1,Boeung Keng Kang 1
BKK2,Boeung Keng Kang 2
BKK3,Boeung Keng Kang 3
Toul Kork,Toul Kork
Tuol Kouk,Toul Kork
Toul Kouk,Toul Kork
Daun Penh,Daun Penh
Doun Penh,Daun Penh
Chamkarmon,Chamkarmon
Chamkar Mon,Chamkarmon
Chamcar Mon,Chamkarmon
Sen Sok,Sen Sok
Sensok,Sen Sok
Russey Keo,Russey Keo
Ruessei Kaev,Russey Keo
Chroy Changvar,Chroy Changvar
Chrouy Changvar,Chroy Changvar
Meanchey,Meanchey
Mean Chey,Meanchey
Por Senchey,Pur Senchey
Pur Senchey,Pur Senchey
Dangkao,Dangkao
Dangkor,Dangkao
Prek Pnov,Prek Pnov
Chbar Ampov,Chbar Ampov
Kamboul,Kamboul
Tonle Bassac,Tonle Bassac
Boeung Trabek,Boeung Trabek
Toul Tom Poung,Toul Tom Poung
Tuol Tumpung,Toul Tom Poung
"""

LANDMARKS_CSV = """name,lat,lon,category
BKK1 Center,11.5449,104.9210,prime_district
Central Market,11.5695,104.9210,commercial
Riverside (Sisowath Quay),11.5680,104.9320,leisure
Independence Monument,11.5564,104.9282,landmark
AEON Mall 1,11.5464,104.9370,mall
AEON Mall 2,11.5178,104.8925,mall
Russian Market,11.5427,104.9182,commercial
Phnom Penh International Airport,11.5466,104.8441,transport
Royal Palace,11.5637,104.9310,landmark
Olympic Stadium,11.5533,104.9145,landmark
"""

README = """# PP PropertyLens

Phnom Penh condominium price analytics and prediction.

**One line:** collect real Phnom Penh condo listings, use machine learning to
predict fair prices, and show it all on an interactive city map.

---

## Status

- [ ] Week 1-2  Data collection (scraping)
- [ ] Week 3    Cleaning and deduplication
- [ ] Week 4    Exploratory data analysis
- [ ] Week 5    Feature engineering
- [ ] Week 6    Model training and evaluation
- [ ] Week 7    Flask API and React dashboard
- [ ] Week 8    Report, screenshots, demo

## Setup

```bash
python -m venv venv
source venv/Scripts/activate      # Git Bash on Windows
pip install -r requirements.txt
playwright install chromium
```

## Pipeline

Data moves through three layers and is never edited in place.

```
bronze  ->  silver  ->  gold  ->  model
(raw)      (clean)    (features)
```

```bash
python src/scrape_realestate.py    # bronze
python src/scrape_khmer24.py       # bronze
python src/clean.py                # bronze -> silver
python src/deduplicate.py          # silver
python src/features.py             # silver -> gold
python src/train_model.py          # gold  -> models/
python src/evaluate.py
python src/explain.py

python backend/app.py              # terminal 1
cd frontend && npm run dev         # terminal 2
```

## Results

_To be filled in after Week 6._

| Model | RMSE | MAPE | R2 |
|---|---|---|---|
| District median (baseline) | | | |
| Linear Regression | | | |
| Random Forest | | | |
| XGBoost | | | |

## Known limitations

- The dataset contains **asking prices**, not final transaction prices.
  In the current market, condos often sell 10-15% below the listed price.
  The model therefore predicts a fair *listing* value, useful as a
  negotiation benchmark, not a certified valuation.
- Scope is condominiums and apartments for sale in Phnom Penh only.
  Land, borey houses, villas, and commercial property are excluded.
- Some listings lack exact coordinates; the district centroid is used as a
  fallback and flagged via `coord_precision`.

## Data sources

- realestate.com.kh (public listing pages)
- Khmer24.com (public listing pages)
- OpenStreetMap (ODbL) - landmark coordinates and khan boundaries

Only publicly visible pages are collected. No personal data (agent names,
phone numbers, emails) is stored. Requests are throttled to avoid burdening
the source websites. Academic, non-commercial use.

## Author

CHHO Sengmeng - Institute of Technology of Cambodia (ITC), Department of AMS
"""

INIT_PY = '"""PP PropertyLens source package."""\n'


def write(path: Path, content: str) -> None:
    """Write a file only if it does not already exist."""
    if path.exists():
        print(f"  skip (exists)  {path.relative_to(ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  created        {path.relative_to(ROOT)}")


def main() -> None:
    print(f"\nSetting up PP PropertyLens in: {ROOT}\n")

    print("Folders:")
    for folder in FOLDERS:
        p = ROOT / folder
        existed = p.exists()
        p.mkdir(parents=True, exist_ok=True)
        # keep empty data folders in git
        if folder.startswith(("data/", "models", "outputs/")):
            gk = p / ".gitkeep"
            if not gk.exists():
                gk.write_text("", encoding="utf-8")
        print(f"  {'ok            ' if existed else 'created       '} {folder}/")

    print("\nFiles:")
    write(ROOT / ".gitignore", GITIGNORE)
    write(ROOT / "requirements.txt", REQUIREMENTS)
    write(ROOT / "README.md", README)
    write(ROOT / "config" / "settings.py", SETTINGS)
    write(ROOT / "config" / "district_mapping.csv", DISTRICT_MAPPING_CSV)
    write(ROOT / "config" / "landmarks.csv", LANDMARKS_CSV)
    write(ROOT / "src" / "__init__.py", INIT_PY)

    print("\nDone.\n")
    print("Next steps:")
    print("  1. git init && git add . && git commit -m 'Initial project structure'")
    print("  2. Create an empty repo on GitHub, then:")
    print("     git remote add origin <your-repo-url>")
    print("     git branch -M main && git push -u origin main")
    print("  3. Open realestate.com.kh in Chrome, press F12, and note which HTML")
    print("     tags hold price, size, bedrooms, and district.")
    print("  4. Start writing src/scrape_realestate.py\n")


if __name__ == "__main__":
    main()