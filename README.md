# PP PropertyLens

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
