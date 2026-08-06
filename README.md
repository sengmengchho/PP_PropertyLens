# PP PropertyLens

PP PropertyLens is a Phnom Penh property data project that collects public condo listings, cleans and standardises them, and prepares the data for pricing analysis and a future prediction app.

## Project Snapshot

Current focus: Phnom Penh condominiums for sale.

What is already in place:

- Public listing sources have been identified, verified, and scraped.
- Raw data has been inspected source by source.
- The bronze-to-silver cleaning pipeline is implemented and documented.
- A cleaned dataset and duplicate log have already been produced.
- Supporting recon, audit, and inspection reports are saved in `outputs/reports/`.

## Completed Work

### 1. Source discovery and scraping

- Site recon and source verification were completed for the target property websites.
- Scrapers exist for the main sources in `src/`, including realestate.com.kh and Khmer24.
- Additional agency sources are also present in the project structure for later consolidation.

### 2. Raw data inspection

- Source-specific inspection scripts were run for raw listing files.
- The realestate.com.kh raw dataset inspection completed successfully and produced a detailed report.
- The Khmer24 inspection and decision-audit reports are also saved for review.

### 3. Cleaning and deduplication

- The bronze-to-silver cleaning pipeline is implemented in `src/clean.py`.
- Districts are standardised, missing fields are recovered where possible, and duplicates are removed.
- Cleaning output and a written report are available in `data/silver/` and `outputs/reports/`.

### 4. Current cleaned-data summary

- Collected from all sources: 3,476 records
- After scope filtering and validation: 2,931 records
- Unique properties after deduplication: 2,463 records
- Main excluded rows: rentals, outside Phnom Penh, missing or impossible price/size values, and duplicates

## Repository Structure

```text
config/      Project settings, district mappings, landmark data
data/        Bronze, silver, and geo datasets
docs/        Supporting notes and documentation
outputs/     Reports, audits, recon results, and figures
src/         Scrapers, recon scripts, cleaning scripts, and utilities
```

## How To Run

Set up the environment:

```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
playwright install chromium
```

Run the main pipeline steps:

```bash
python src/scrape_realestate.py
python src/scrape_khmer24.py
python src/clean.py
```

If you want to generate the realestate inspection report on Windows, use:

```bash
PYTHONIOENCODING=utf-8 python src/cleaning/inspect_realestate.py > outputs/reports/realestate_cleaning_inspection.txt
```

## What Comes Next

1. Exploratory data analysis on the cleaned silver dataset.
2. Feature engineering, including location and property features.
3. Model training and evaluation with a baseline and comparison models.
4. Build the API and dashboard for price lookup and visualization.
5. Prepare the final report, screenshots, and demo materials.

## Known Limitations

- The dataset contains asking prices, not final transaction prices.
- The project scope is condominiums and apartments for sale in Phnom Penh only.
- Some listings still lack exact coordinates, so district-level fallback logic is used.

## Data Sources

- realestate.com.kh
- Khmer24.com
- OpenStreetMap landmark and boundary data

Only publicly visible pages are collected. No personal contact data is stored. Requests are throttled to avoid burdening the source websites.

## Author

CHHO Sengmeng - Institute of Technology of Cambodia (ITC), Department of AMS
