# PP PropertyLens

PP PropertyLens is a Streamlit application for exploring advertised condominium and penthouse prices in Phnom Penh. It combines public listing data, a machine-learning price estimator, uncertainty estimates, market exploration, and model validation in one interface.

## What You Can Do

- **Estimate a property price** from property type, size, bedrooms, bathrooms, floor level, and district.
- **See an uncertainty range** with an 80% conformal prediction interval.
- **Understand each estimate** through SHAP-based factor explanations.
- **Explore the market** by property type, district, asking-price range, and budget.
- **Review model quality** through test metrics, global feature importance, and real-world validation results.
- **Read the methodology** behind collection, cleaning, recovery, geocoding, modelling, and validation.

The Streamlit sidebar provides these views: the main estimator, **Budget Advisor**, **Market Insights**, **Model Performance**, and **About & Methodology**.

## Data Summary

The current Gold dataset contains **2,673 deduplicated listings** from six public sources:

| Source | Listings |
| --- | ---: |
| realestate.com.kh | 844 |
| harbor-property.com | 753 |
| khpropertyhub.com | 675 |
| camrealtyservice.com | 199 |
| aps.com.kh | 109 |
| khmer24.com | 93 |
| **Total** | **2,673** |

The dataset contains 2,482 condos and 191 penthouses. Prices range from $20,000 to $5,000,000, with a mean listing price of approximately $170,818. These are advertised prices, not confirmed transaction prices.

## Model

The application uses the trained pipeline in `models/propertylens_xgboost_final.joblib`. Its input features are:

- Property size in square metres
- Bedrooms
- Bathrooms
- Unit floor
- District
- Property type

The final test results recorded in the model metadata are:

| Metric | Result |
| --- | ---: |
| RMSE | $122,245.87 |
| MAE | $53,075.18 |
| MAPE | 26.08% |
| R² | 0.5529 |
| Log RMSE | 0.3374 |
| Log R² | 0.8164 |

The model was trained on 2,137 rows, calibrated on 268 rows, and evaluated on a final test set of 268 rows. The nominal interval level is 80%; observed validation coverage was 77.61%.

## Repository Structure

```text
app.py                  Streamlit prediction page
pages/                  Market, methodology, and model-performance pages
src/                    Scrapers, cleaning, recovery, and prediction code
config/                 Settings, district mappings, landmarks, and URLs
data/bronze/            Source-level raw listing data
data/silver/            Cleaned, recovered, and deduplicated data
data/gold/              Final analytical datasets and summaries
data/model/             Global SHAP feature importance
data/qa/                Real-world validation results
models/                 Trained models and model metadata
outputs/reports/        Cleaning, audit, and inspection reports
scripts/                Model, QA, and utility scripts
notebooks/              EDA, feature engineering, and location notebooks
```

## Quick Start

Python 3.11 or newer is recommended. Create and activate a virtual environment, then install the dependencies.

### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt streamlit
playwright install chromium
```

### macOS/Linux or Git Bash

```bash
python -m venv venv
source venv/Scripts/activate
python -m pip install -r requirements.txt streamlit
playwright install chromium
```

For macOS/Linux, use `source venv/bin/activate` instead.

If PowerShell blocks script activation, enable it for the current user or activate the environment from a Command Prompt with `venv\\Scripts\\activate.bat`.

## Run the Application

From the project root, with the virtual environment active:

```bash
streamlit run app.py
```

The application expects these generated assets to be present:

- `models/propertylens_xgboost_final.joblib`
- `models/propertylens_xgboost_final_metadata.json`
- `data/gold/property_listings_geocoded.csv`

Open the local URL printed by Streamlit, usually `http://localhost:8501`.

## Data Pipeline

The repository contains the full collection and transformation workflow. Scraping requires network access and may need adjustments when source websites change. Run source collection before cleaning, and rebuild derived datasets in order.

### Collection and cleaning

```bash
python src/scrape_realestate.py
python src/scrape_khmer24.py
python src/scrape_agencies.py
python src/cleaning/clean_realestate.py
python src/cleaning/clean_khmer24.py
python src/cleaning/clean_harbor.py
python src/cleaning/clean_khpropertyhub.py
python src/cleaning/clean_camrealty.py
python src/cleaning/clean_aps.py
python src/cleaning/merge_silver_sources.py
python src/cleaning/build_gold_dataset.py
```

The repository also includes utilities for source verification, field inspection, location recovery, geocoding, cross-source deduplication, model prediction tests, SHAP generation, and real-world QA. Review the scripts and reports in `outputs/reports/` before rerunning collection or rebuilding derived datasets.

### Existing data layers

- `data/bronze/`: source-level raw listing data.
- `data/silver/`: cleaned, recovered, reviewed, and deduplicated data.
- `data/gold/`: final datasets used by the application and analysis.
- `data/geo/`: geocoding outputs and coordinate validation files.
- `data/qa/`: real-world validation inputs and results.

Do not treat advertised prices as confirmed transaction prices. Rebuilding the datasets can change the summary statistics and model results reported below.

## Limitations

- Estimates describe advertised asking prices and are not official valuations.
- The project focuses on condo and penthouse listings in Phnom Penh.
- Listing coverage and data quality vary by source.
- Some records have missing district, bathroom, floor, project, or coordinate information.
- The model is intended for exploratory price estimation, not financial, legal, or investment decisions.

## Data Sources

- realestate.com.kh
- harbor-property.com
- khpropertyhub.com
- camrealtyservice.com
- aps.com.kh
- khmer24.com


Only publicly visible listing information is collected. Requests are throttled, and personal contact data is not stored as part of the analytical dataset.

## Author

CHHO Sengmeng 
Data Scientist (Intern) - Data Insight Cambodia, 
Institute of Technology of Cambodia (ITC), Department of AMS
