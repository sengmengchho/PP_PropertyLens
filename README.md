# PP PropertyLens

PP PropertyLens is a Streamlit application for exploring advertised condominium and penthouse asking prices in Phnom Penh.

It combines public property-listing data, machine-learning price estimation, uncertainty ranges, market exploration, budget-based comparison, model validation, and explainability in one interface.

> **Important:** PP PropertyLens estimates advertised asking prices. It is not an official property valuation and should not be used as financial, legal, or investment advice.

---

## Features

### 🏠 Price Estimator

Estimate an advertised asking price using:

- Property type
- Property size
- Bedrooms
- Bathrooms
- Floor level
- District

The estimator provides:

- Estimated asking price
- Estimated price range
- Main influencing factors
- Missing-information warnings
- Property summary

The estimated range is generated using split-conformal calibration with a nominal 80% interval level.

Individual prediction explanations use XGBoost's native feature-contribution calculation, based on TreeSHAP-style contributions.

---

### 📊 Market Insights

Explore the Phnom Penh condo and penthouse market using filters for:

- Property type
- District
- Asking-price range

The dashboard includes:

- Number of listings
- Lowest asking price
- Median asking price
- Highest asking price
- Median property size
- District coverage
- Most common price ranges
- District price comparisons
- Price per m² analysis
- Asking-price distributions
- Bedroom and bathroom characteristics

Small samples are handled separately to avoid presenting weak market-level conclusions.

---

### 💰 Budget Advisor

Explore what different budgets can access in the current listing dataset.

The Budget Advisor shows:

- Number of listings within budget
- Median affordable asking price
- Highest matching listing
- Market coverage
- Budget position
- Typical property characteristics near the selected budget
- Property-type comparisons
- Areas to compare
- District availability
- Listings closest to the selected budget

The Budget Advisor is descriptive decision support based on advertised listings. It is not an investment recommendation.

---

### 🤖 Model Performance

Review the performance and validation of the final machine-learning model.

The page includes:

- Model comparison
- Validation results
- Final held-out test performance
- Estimated price-range performance
- Global feature importance
- Real-world listing QA
- Explanations of evaluation metrics

---

### ℹ️ About & Methodology

Review the full project methodology, including:

- Data collection
- Cleaning
- Manual review
- Cross-source deduplication
- Location recovery
- Feature engineering
- Model development
- Validation strategy
- Uncertainty estimation
- Explainability
- Project limitations

---

## Data Summary

The final Gold dataset contains **2,673 deduplicated property listings** collected from six public property-listing sources.

| Source | Listings |
| --- | ---: |
| realestate.com.kh | 844 |
| harbor-property.com | 753 |
| khpropertyhub.com | 675 |
| camrealtyservice.com | 199 |
| aps.com.kh | 109 |
| khmer24.com | 93 |
| **Total** | **2,673** |

### Property Types

| Property Type | Listings |
| --- | ---: |
| Condo | 2,482 |
| Penthouse | 191 |

The dataset contains advertised asking prices ranging from approximately **$20,000 to $5,000,000**.

The mean advertised asking price is approximately **$170,818**, while the median is approximately **$95,000**.

These are advertised listing prices, not confirmed transaction prices.

---

## Machine-Learning Model

The application uses the final trained pipeline:

```text
models/propertylens_xgboost_final.joblib
```

Model metadata is stored in:

```text
models/propertylens_xgboost_final_metadata.json
```

### Input Features

The final model uses six features:

| Feature | Description |
| --- | --- |
| `size_m2` | Property size in square metres |
| `bedrooms` | Number of bedrooms |
| `bathrooms` | Number of bathrooms |
| `unit_floor` | Unit floor level |
| `district` | Phnom Penh district |
| `property_type` | Condo or Penthouse |

Missing numeric values are handled by the preprocessing pipeline, and missing categorical location values can be represented as unknown.

The model predicts:

```text
log(1 + advertised asking price)
```

The predicted value is then converted back to USD.

---

## Model Development

Three model families were compared:

- Linear Regression
- Random Forest
- XGBoost

The final selected model is **XGBoost**.

The model was selected primarily using validation performance on the log-transformed target.

### Final Data Split

The final dataset was divided into four partitions while preserving the Condo/Penthouse distribution.

| Split | Rows | Approx. Share |
| --- | ---: | ---: |
| Training | 1,869 | 70% |
| Validation | 268 | 10% |
| Calibration | 268 | 10% |
| Final Test | 268 | 10% |

After model selection, the selected XGBoost configuration was refitted using:

```text
Training + Validation = 2,137 listings
```

The calibration set was used for uncertainty-range calibration.

The final test set was used for the final held-out evaluation.

---

## Final Test Performance

| Metric | Result |
| --- | ---: |
| RMSE | $122,245.87 |
| MAE | $53,075.18 |
| MAPE | 26.08% |
| R² | 0.5529 |
| Log RMSE | 0.3374 |
| Log MAE | 0.2562 |
| Log R² | 0.8164 |

Because the model was trained on the log-transformed price target, log-scale metrics are especially useful when evaluating performance across properties with very different price levels.

Raw-dollar metrics can be strongly affected by a small number of high-value listings.

---

## Estimated Price Range

PP PropertyLens provides an estimated price range in addition to a central estimate.

The range is generated using split-conformal calibration.

| Metric | Result |
| --- | ---: |
| Nominal interval level | 80% |
| Final-test observed coverage | 77.61% |
| Median interval width | ~$82,768 |
| Mean interval width | ~$139,065 |

The estimated range represents model uncertainty and should not be interpreted as a guaranteed probability interval for every individual property.

---

## Global Feature Importance

Global feature importance was calculated using SHAP-based analysis during model evaluation.

Approximate relative importance:

| Feature | Relative Importance |
| --- | ---: |
| Property Size | 55.2% |
| Location / District | 16.4% |
| Bedrooms | 11.3% |
| Floor Level | 10.4% |
| Bathrooms | 4.0% |
| Property Type | 2.7% |

For the deployed Price Estimator, individual feature explanations are calculated directly using XGBoost native feature contributions.

This avoids requiring SHAP, Numba, and LLVM as runtime dependencies.

---

## Real-World QA

A small practical QA exercise was also conducted using 10 real property listings outside the main model-development workflow.

| QA Metric | Result |
| --- | ---: |
| Listings tested | 10 |
| Successful predictions | 10 |
| Median percentage error | 19.43% |
| Mean percentage error | 28.10% |
| Advertised price inside estimated range | 9 / 10 |

This QA sample is intended only as a practical sanity check.

The held-out final test set remains the primary model evaluation.

---

## Repository Structure

```text
pp-propertylens/
│
├── app.py
│
├── pages/
│   ├── Market_Insights.py
│   ├── Budget_Advisor.py
│   ├── Model_Performance.py
│   └── About_Methodology.py
│
├── src/
│   ├── prediction/
│   ├── cleaning/
│   └── scraping / utility modules
│
├── config/
│   └── mappings, URLs, landmarks, and settings
│
├── data/
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   ├── geo/
│   ├── model/
│   └── qa/
│
├── models/
│   ├── propertylens_xgboost_final.joblib
│   └── propertylens_xgboost_final_metadata.json
│
├── outputs/
│   └── reports/
│
├── scripts/
│   ├── generate_global_shap.py
│   ├── real_world_qa.py
│   └── utility scripts
│
├── notebooks/
│   └── EDA, modelling, and feature-engineering notebooks
│
├── requirements.txt
└── README.md
```

---

## Requirements

The deployed Streamlit application uses a lightweight runtime environment.

Main dependencies include:

```text
streamlit
pandas
numpy
scikit-learn
xgboost
joblib
altair
```

The production application does not require SHAP, Numba, Jupyter, Playwright, or other data-collection dependencies at runtime.

---

## Quick Start

Python 3.11 or newer is recommended.

### Windows PowerShell

Create the environment:

```powershell
python -m venv venv
```

Activate it:

```powershell
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

### Windows Git Bash

```bash
python -m venv venv
source venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

### macOS / Linux

```bash
python -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Run the Application

From the project root:

```bash
streamlit run app.py
```

Streamlit will print a local URL such as:

```text
http://localhost:8501
```

If port 8501 is already in use, Streamlit may automatically use another port such as 8502.

---

## Required Application Assets

The application expects the following generated files to be available:

```text
models/propertylens_xgboost_final.joblib

models/propertylens_xgboost_final_metadata.json

data/gold/property_listings_geocoded.csv

data/model/global_shap_importance.csv

data/qa/real_world_validation_results.csv
```

These assets support the estimator, market dashboards, model-performance page, and QA results.

---

## Data Pipeline

The project follows a layered data workflow:

```text
Public Listing Sources
        ↓
Bronze
Raw source-level data
        ↓
Silver
Cleaning and standardization
        ↓
Manual Review
        ↓
Location Recovery
        ↓
Cross-Source Deduplication
        ↓
Gold
Final analytical dataset
        ↓
EDA / Feature Engineering
        ↓
Machine-Learning Model
        ↓
Streamlit Application
```

### Data Layers

#### Bronze

```text
data/bronze/
```

Raw source-level listing data.

#### Silver

```text
data/silver/
```

Cleaned, standardized, reviewed, recovered, and deduplicated data.

#### Gold

```text
data/gold/
```

Final analytical datasets used for modelling and the Streamlit application.

#### Geo

```text
data/geo/
```

Location-recovery and coordinate-validation outputs.

#### QA

```text
data/qa/
```

Real-world QA inputs and results.

---

## Data Collection

The repository also contains scripts for collecting data from the six listing sources.

Examples include:

```bash
python src/scrape_realestate.py
python src/scrape_khmer24.py
python src/scrape_agencies.py
```

Cleaning scripts include:

```bash
python src/cleaning/clean_realestate.py
python src/cleaning/clean_khmer24.py
python src/cleaning/clean_harbor.py
python src/cleaning/clean_khpropertyhub.py
python src/cleaning/clean_camrealty.py
python src/cleaning/clean_aps.py
python src/cleaning/merge_silver_sources.py
python src/cleaning/build_gold_dataset.py
```

The lightweight production `requirements.txt` is designed for running the Streamlit application.

Additional development or scraping dependencies may be required to rerun the complete data-collection pipeline.

Source websites can also change their structure over time, so scraping logic may require maintenance.

---

## Limitations

PP PropertyLens has several important limitations:

- The target represents advertised asking prices, not completed transaction prices.
- The project focuses only on Condo and Penthouse listings in Phnom Penh.
- Listing availability and data quality vary across sources.
- Some listings contain missing bedroom, bathroom, floor, district, project, or coordinate information.
- Exact geographic coordinates are available for only a limited subset of listings.
- The model uses six production features and therefore cannot directly capture every property characteristic.
- Important unobserved characteristics may include building reputation, condition, furnishing, facilities, view, parking, renovation quality, urgency, and negotiation.
- Penthouses and ultra-luxury properties are much less common in the dataset than Condos.
- The final test set contains limited representation of properties above $1 million.
- Because the split is performed at listing level, some similarity between properties from the same building or project may remain across partitions.
- Estimated price ranges describe uncertainty but are not guarantees for individual properties.

---

## Responsible Use

PP PropertyLens is designed for:

- Market exploration
- Educational analysis
- Data-science experimentation
- Advertised asking-price comparison
- Preliminary property research

It should **not** be used as:

- An official property valuation
- A guaranteed selling-price prediction
- Financial advice
- Investment advice
- Legal advice

Users should combine the results with professional property inspection, local market knowledge, transaction evidence, and qualified valuation advice when making important property decisions.

---

## Data Sources

Public listing information was collected from:

- realestate.com.kh
- harbor-property.com
- khpropertyhub.com
- camrealtyservice.com
- aps.com.kh
- khmer24.com

The analytical workflow focuses on property-listing attributes required for market analysis and modelling.

---

## Author

**CHHO Sengmeng**

Data Scientist Intern  
**Data Insight Cambodia**

Student  
**Institute of Technology of Cambodia (ITC)**  
Department of Applied Mathematics and Statistics