# PP PropertyLens

PP PropertyLens is a Streamlit data application for exploring advertised condominium and penthouse prices in Phnom Penh and generating data-based asking-price estimates.

The project covers the full workflow from public listing collection and cleaning to exploratory market analysis, machine-learning prediction, model explanation, and validation.

## Current Features

- **Property Price Estimate**: estimate an asking price from property type, size, bedrooms, bathrooms, floor level, and district.
- **Uncertainty range**: display a central estimate and an 80% conformal prediction interval.
- **Prediction explanation**: show the factors with the greatest influence on each estimate using SHAP-based explanations.
- **Market Insights**: filter and visualise asking-price patterns by property type, district, and price range.
- **Model Performance**: review model metrics, global feature importance, and real-world validation results.
- **About & Methodology**: describe the data, processing workflow, model, and project limitations.

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

## Setup

Create and activate a virtual environment, then install the dependencies:

```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
playwright install chromium
```

On Windows PowerShell, activate the environment with:

```powershell
.\venv\Scripts\Activate.ps1
```

## Run the Application

From the project root:

```bash
streamlit run app.py
```

The application requires the trained model files in `models/` and the Gold listing data in `data/gold/`.

## Data Pipeline

The main collection and cleaning scripts are:

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

Additional utilities are available for source verification, field inspection, location recovery, geocoding, model prediction tests, SHAP generation, and real-world QA. Review the scripts and reports before rerunning collection or rebuilding derived datasets.

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
