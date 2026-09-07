import gradio as gr
import joblib
import numpy as np
import pandas as pd
import json
from huggingface_hub import hf_hub_download

# =========================================================
# LOAD MODEL FROM HUGGING FACE
# =========================================================

MODEL_REPO = "chhosengmeng/pp-propertylens-model"

model_path = hf_hub_download(
    repo_id=MODEL_REPO,
    filename="propertylens_xgboost_final.joblib"
)

metadata_path = hf_hub_download(
    repo_id=MODEL_REPO,
    filename="propertylens_xgboost_final_metadata.json"
)

model = joblib.load(model_path)

with open(metadata_path, "r") as f:
    metadata = json.load(f)

Q_HAT = float(metadata["q_hat"])

# =========================================================
# GET VALID CATEGORIES
# =========================================================

preprocessor = model.named_steps["preprocessor"]
cat_pipeline = preprocessor.named_transformers_["cat"]
onehot_encoder = cat_pipeline.named_steps["onehot"]
category_values = onehot_encoder.categories_

VALID_DISTRICTS = [v for v in category_values[0] if str(v) != "Unknown"]
VALID_PROPERTY_TYPES = list(category_values[1])

# =========================================================
# PREDICTION FUNCTION
# =========================================================

def predict_price(property_type, district, size_m2, bedrooms, bathrooms, unit_floor):

    property_data = pd.DataFrame([{
        "size_m2": size_m2,
        "bedrooms": np.nan if bedrooms == "Not provided" else float(bedrooms),
        "bathrooms": np.nan if bathrooms == "Not provided" else float(bathrooms),
        "unit_floor": np.nan if unit_floor == "Not provided" else float(unit_floor),
        "district": np.nan if district == "Not provided" else district,
        "property_type": property_type,
    }])

    predicted_log_price = model.predict(property_data)[0]
    estimated_price = float(np.expm1(predicted_log_price))
    lower_price = float(np.expm1(predicted_log_price - Q_HAT))
    upper_price = float(np.expm1(predicted_log_price + Q_HAT))

    return {
        "estimated_price_usd": round(estimated_price, 2),
        "lower_price_usd": round(max(0, lower_price), 2),
        "upper_price_usd": round(upper_price, 2),
    }

# =========================================================
# GRADIO INTERFACE
# =========================================================

demo = gr.Interface(
    fn=predict_price,
    inputs=[
        gr.Dropdown(choices=VALID_PROPERTY_TYPES, label="Property Type", value="Condo"),
        gr.Dropdown(choices=["Not provided"] + VALID_DISTRICTS, label="District", value="Not provided"),
        gr.Number(label="Property Size (m²)", value=70, minimum=1),
        gr.Dropdown(choices=["Not provided"] + [str(i) for i in range(0, 11)], label="Bedrooms", value="2"),
        gr.Dropdown(choices=["Not provided"] + [str(i) for i in range(0, 11)], label="Bathrooms", value="2"),
        gr.Dropdown(choices=["Not provided"] + [str(i) for i in range(0, 101)], label="Floor Level", value="10"),
    ],
    outputs=gr.JSON(label="Price Estimate"),
    title="PP PropertyLens API",
    description="Estimate property prices in Phnom Penh using machine learning.",
)

if __name__ == "__main__":
    demo.launch()
