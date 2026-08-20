from pathlib import Path
import json

import altair as alt
import pandas as pd
import streamlit as st


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Model Performance | PP PropertyLens",
    page_icon="🤖",
    layout="wide",
)


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

METADATA_PATH = (
    PROJECT_ROOT
    / "models"
    / "propertylens_xgboost_final_metadata.json"
)

QA_RESULTS_PATH = (
    PROJECT_ROOT
    / "data"
    / "qa"
    / "real_world_validation_results.csv"
)

SHAP_PATH = (
    PROJECT_ROOT
    / "data"
    / "model"
    / "global_shap_importance.csv"
)


# =========================================================
# LOAD FINAL MODEL METADATA
# =========================================================

@st.cache_data
def load_metadata():

    with open(
        METADATA_PATH,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


metadata = load_metadata()


# =========================================================
# LOAD REAL-WORLD QA
# =========================================================

@st.cache_data
def load_qa_results():

    if not QA_RESULTS_PATH.exists():

        return None

    return pd.read_csv(
        QA_RESULTS_PATH
    )


qa_df = load_qa_results()




# =========================================================
# LOAD SHAP VALUES

@st.cache_data
def load_global_shap():

    if not SHAP_PATH.exists():

        return None

    return pd.read_csv(
        SHAP_PATH
    )


shap_df = load_global_shap()


# =========================================================
# MODEL COMPARISON
# =========================================================
#
# These are validation-set results from the final
# 70 / 10 / 10 / 10 workflow.
#

model_comparison = pd.DataFrame(
    [
        {
            "Model":
                "Linear Regression",

            "RMSE":
                134816.18,

            "MAE":
                53659.83,

            "MAPE":
                32.95,

            "R2":
                0.6772,

            "Log_RMSE":
                0.3996,

            "Log_MAE":
                0.3086,

            "Log_R2":
                0.7576,
        },

        {
            "Model":
                "Random Forest",

            "RMSE":
                106100.19,

            "MAE":
                44822.06,

            "MAPE":
                26.97,

            "R2":
                0.8001,

            "Log_RMSE":
                0.3488,

            "Log_MAE":
                0.2578,

            "Log_R2":
                0.8154,
        },

        {
            "Model":
                "XGBoost",

            "RMSE":
                107444.12,

            "MAE":
                43293.55,

            "MAPE":
                27.67,

            "R2":
                0.7950,

            "Log_RMSE":
                0.3479,

            "Log_MAE":
                0.2589,

            "Log_R2":
                0.8163,
        },
    ]
)


# =========================================================
# HEADER
# =========================================================

st.title(
    "🤖 Model Performance"
)

st.write(
    "See how the machine-learning models were compared "
    "and how the final PP PropertyLens model performed "
    "on unseen property listings."
)

st.divider()


# =========================================================
# FINAL MODEL
# =========================================================

st.subheader(
    "Selected Model"
)


with st.container(
    border=True
):

    model_col1, model_col2, model_col3 = (
        st.columns(3)
    )


    with model_col1:

        st.metric(
            "Final Model",
            "XGBoost",
        )


    with model_col2:

        st.metric(
            "Training Rows",
            f"{metadata['training_rows']:,}",
        )


    with model_col3:

        st.metric(
            "Prediction Target",
            "Asking Price",
        )


st.info(
    "XGBoost was selected because it achieved the "
    "lowest validation Log RMSE and the highest "
    "validation Log R² among the three models, while "
    "also showing a smaller train–validation gap than "
    "Random Forest."
)


# =========================================================
# MODEL COMPARISON
# =========================================================

st.subheader(
    "Model Comparison"
)

st.caption(
    "All three models were trained using the same training "
    "data and compared on the same validation set."
)


# =========================================================
# FRIENDLY COMPARISON TABLE
# =========================================================

comparison_display = (
    model_comparison[
        [
            "Model",
            "RMSE",
            "MAE",
            "MAPE",
            "Log_RMSE",
            "Log_R2",
        ]
    ]
    .copy()
)


comparison_display = (
    comparison_display.rename(
        columns={
            "RMSE":
                "RMSE",

            "MAE":
                "MAE",

            "MAPE":
                "MAPE (%)",

            "Log_RMSE":
                "Log RMSE",

            "Log_R2":
                "Log R²",
        }
    )
)


st.dataframe(
    comparison_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "RMSE":
            st.column_config.NumberColumn(
                format="$%.0f",
            ),

        "MAE":
            st.column_config.NumberColumn(
                format="$%.0f",
            ),

        "MAPE (%)":
            st.column_config.NumberColumn(
                format="%.2f%%",
            ),

        "Log RMSE":
            st.column_config.NumberColumn(
                format="%.4f",
            ),

        "Log R²":
            st.column_config.NumberColumn(
                format="%.4f",
            ),
    },
)


# =========================================================
# MODEL COMPARISON CHARTS
# =========================================================

chart_col1, chart_col2 = st.columns(
    2,
    gap="large",
)


# ---------------------------------------------------------
# LOG RMSE
# ---------------------------------------------------------

with chart_col1:

    st.markdown(
        "#### Validation Log RMSE"
    )

    st.caption(
        "Lower is better."
    )


    log_rmse_chart = (
        alt.Chart(
            model_comparison
        )
        .mark_bar(
            cornerRadiusTopLeft=5,
            cornerRadiusTopRight=5,
        )
        .encode(
            x=alt.X(
                "Model:N",
                title=None,
            ),

            y=alt.Y(
                "Log_RMSE:Q",
                title="Log RMSE",
                scale=alt.Scale(
                    zero=False
                ),
            ),

            tooltip=[
                alt.Tooltip(
                    "Model:N",
                    title="Model",
                ),

                alt.Tooltip(
                    "Log_RMSE:Q",
                    title="Log RMSE",
                    format=".4f",
                ),
            ],
        )
        .properties(
            height=350,
        )
    )


    st.altair_chart(
        log_rmse_chart,
        use_container_width=True,
    )


# ---------------------------------------------------------
# MAPE
# ---------------------------------------------------------

with chart_col2:

    st.markdown(
        "#### Validation MAPE"
    )

    st.caption(
        "Lower is better."
    )


    mape_chart = (
        alt.Chart(
            model_comparison
        )
        .mark_bar(
            cornerRadiusTopLeft=5,
            cornerRadiusTopRight=5,
        )
        .encode(
            x=alt.X(
                "Model:N",
                title=None,
            ),

            y=alt.Y(
                "MAPE:Q",
                title="MAPE (%)",
                scale=alt.Scale(
                    zero=False
                ),
            ),

            tooltip=[
                alt.Tooltip(
                    "Model:N",
                    title="Model",
                ),

                alt.Tooltip(
                    "MAPE:Q",
                    title="MAPE",
                    format=".2f",
                ),
            ],
        )
        .properties(
            height=350,
        )
    )


    st.altair_chart(
        mape_chart,
        use_container_width=True,
    )


st.caption(
    "Random Forest achieved slightly better validation "
    "MAPE and raw RMSE, while XGBoost achieved the best "
    "Log RMSE and Log R². Because the model was trained "
    "to predict log-transformed asking price, the log-space "
    "metrics were important in the final model selection."
)


st.divider()


# =========================================================
# FINAL TEST PERFORMANCE
# =========================================================

st.subheader(
    "Final Test Performance"
)

st.caption(
    "After model selection, the final XGBoost model was "
    "evaluated on a separate test set that was not used "
    "for model fitting or calibration."
)


final_metrics = (
    metadata[
        "final_test_metrics"
    ]
)


test_col1, test_col2, test_col3, test_col4 = (
    st.columns(4)
)


with test_col1:

    st.metric(
        "MAPE",
        (
            f"{final_metrics['mape_percent']:.2f}%"
        ),
    )


with test_col2:

    st.metric(
        "MAE",
        (
            f"${final_metrics['mae_usd']:,.0f}"
        ),
    )


with test_col3:

    st.metric(
        "Log RMSE",
        (
            f"{final_metrics['log_rmse']:.3f}"
        ),
    )


with test_col4:

    st.metric(
        "Log R²",
        (
            f"{final_metrics['log_r2']:.3f}"
        ),
    )


# =========================================================
# SECONDARY METRICS
# =========================================================

with st.expander(
    "See additional technical metrics"
):

    tech_col1, tech_col2, tech_col3 = (
        st.columns(3)
    )


    with tech_col1:

        st.metric(
            "RMSE",
            (
                f"${final_metrics['rmse_usd']:,.0f}"
            ),
        )


    with tech_col2:

        st.metric(
            "Raw Price R²",
            (
                f"{final_metrics['r2_usd']:.3f}"
            ),
        )


    with tech_col3:

        st.metric(
            "Log MAE",
            (
                f"{final_metrics['log_mae']:.3f}"
            ),
        )


# =========================================================
# SIMPLE EXPLANATION
# =========================================================

st.info(
    "On the final test set, the model's asking-price "
    "estimates differed from the advertised prices by "
    "about 26% on average when measured using MAPE. "
    "Performance is generally stronger for common market "
    "properties and less certain for very high-value "
    "luxury listings."
)


st.divider()


# =========================================================
# PREDICTION RANGE PERFORMANCE
# =========================================================

st.subheader(
    "Estimated Price Range Performance"
)

st.caption(
    "PropertyLens provides an estimated price range in "
    "addition to one central asking-price estimate."
)


interval_data = (
    metadata[
        "interval_validation"
    ]
)


interval_col1, interval_col2, interval_col3 = (
    st.columns(3)
)


with interval_col1:

    st.metric(
        "Target Range",
        (
            f"{metadata['interval_level']:.0%}"
        ),
    )


with interval_col2:

    st.metric(
        "Observed Test Coverage",
        (
            f"{interval_data['observed_coverage']:.2%}"
        ),
    )


with interval_col3:

    st.metric(
        "Median Range Width",
        (
            f"${interval_data['median_width_usd']:,.0f}"
        ),
    )


st.info(
    "The range was designed as an 80% estimated range. "
    "On the final test data, about 78% of advertised asking "
    "prices fell inside their model-generated ranges. "
    "This is why PropertyLens shows both a central estimate "
    "and a range instead of presenting one number as exact."
)


# =========================================================
# TECHNICAL INTERVAL INFO
# =========================================================

with st.expander(
    "See prediction-range technical details"
):

    st.write(
        f"Calibration rows: "
        f"**{metadata['calibration_rows']:,}**"
    )

    st.write(
        f"Conformal q-hat: "
        f"**{metadata['q_hat']:.4f}**"
    )

    st.write(
        f"Mean interval width: "
        f"**${interval_data['mean_width_usd']:,.0f}**"
    )


st.divider()



# =========================================================
# GLOBAL FEATURE IMPORTANCE
# =========================================================

st.divider()

st.subheader(
    "Global Feature Importance"
)

st.caption(
    "Shows which property characteristics had the "
    "strongest overall influence on the final XGBoost "
    "model across a representative sample of listings."
)


if (
    shap_df is not None
    and not shap_df.empty
):

    shap_chart_df = (
        shap_df
        .sort_values(
            "mean_abs_shap",
            ascending=True,
        )
        .copy()
    )


    # =====================================================
    # BAR CHART
    # =====================================================

    shap_chart = (
        alt.Chart(
            shap_chart_df
        )
        .mark_bar(
            cornerRadiusEnd=5
        )
        .encode(
            y=alt.Y(
                "display_name:N",
                sort=None,
                title=None,
            ),

            x=alt.X(
                "relative_importance:Q",
                title=(
                    "Relative Importance (%)"
                ),
                axis=alt.Axis(
                    format=".0f",
                ),
            ),

            tooltip=[
                alt.Tooltip(
                    "display_name:N",
                    title="Feature",
                ),

                alt.Tooltip(
                    "relative_importance:Q",
                    title=(
                        "Relative Importance"
                    ),
                    format=".1f",
                ),

                alt.Tooltip(
                    "mean_abs_shap:Q",
                    title=(
                        "Mean |SHAP|"
                    ),
                    format=".4f",
                ),
            ],
        )
        .properties(
            height=380,
        )
    )


    st.altair_chart(
        shap_chart,
        use_container_width=True,
    )


    # =====================================================
    # TOP FACTORS
    # =====================================================

    top_features = (
        shap_df
        .sort_values(
            "mean_abs_shap",
            ascending=False,
        )
        .head(3)
        .reset_index(
            drop=True
        )
    )


    factor_cols = st.columns(
        len(top_features)
    )


    icons = {
        "Property Size":
            "📐",

        "Bedrooms":
            "🛏️",

        "Bathrooms":
            "🚿",

        "Floor Level":
            "🏢",

        "Location (District)":
            "📍",

        "Property Type":
            "🏠",
    }


    for column, (_, row) in zip(
        factor_cols,
        top_features.iterrows(),
    ):

        feature_name = (
            row[
                "display_name"
            ]
        )

        icon = icons.get(
            feature_name,
            "📊",
        )


        with column:

            with st.container(
                border=True
            ):

                st.markdown(
                    f"### {icon} "
                    f"{feature_name}"
                )

                st.metric(
                    "Relative Importance",
                    (
                        f"{row['relative_importance']:.1f}%"
                    ),
                )


    # =====================================================
    # EXPLANATION
    # =====================================================

    most_important = (
        shap_df
        .sort_values(
            "mean_abs_shap",
            ascending=False,
        )
        .iloc[0][
            "display_name"
        ]
    )


    st.info(
        f"{most_important} had the strongest overall "
        "influence on the model's predictions in this "
        "analysis. Other features also contribute, so "
        "PropertyLens considers all six inputs together "
        "when estimating an asking price."
    )


    # =====================================================
    # TECHNICAL DETAILS
    # =====================================================

    with st.expander(
        "What does SHAP importance mean?"
    ):

        st.write(
            """
            SHAP helps explain how much each feature
            influences the machine-learning model.

            For global importance, the absolute SHAP
            values are averaged across many property
            listings.

            A larger value means that the feature tends
            to have a stronger effect on the model's
            predictions overall.

            Global importance does not mean that the
            feature always increases the predicted price.
            Its effect can be different for different
            properties.
            """
        )


else:

    st.warning(
        "Global SHAP results have not been generated yet. "
        "Run scripts/generate_global_shap.py first."
    )


# =========================================================
# REAL-WORLD QA
# =========================================================

st.subheader(
    "Real-World QA"
)

st.caption(
    "A small practical check using real property listings "
    "outside the main model-development workflow."
)


if (
    qa_df is not None
    and not qa_df.empty
):

    successful_qa = (
        qa_df[
            qa_df[
                "status"
            ] == "success"
        ]
        .copy()
        if "status" in qa_df.columns
        else qa_df.copy()
    )


    if not successful_qa.empty:

        qa_col1, qa_col2, qa_col3, qa_col4 = (
            st.columns(4)
        )


        with qa_col1:

            st.metric(
                "Listings Tested",
                (
                    f"{len(successful_qa):,}"
                ),
            )


        with qa_col2:

            st.metric(
                "Median Error",
                (
                    f"{successful_qa['percentage_error'].median():.2f}%"
                ),
            )


        with qa_col3:

            st.metric(
                "Mean Error",
                (
                    f"{successful_qa['percentage_error'].mean():.2f}%"
                ),
            )


        with qa_col4:

            inside_rate = (
                successful_qa[
                    "inside_range"
                ]
                .astype(bool)
                .mean()
                * 100
            )

            st.metric(
                "Inside Estimated Range",
                (
                    f"{inside_rate:.0f}%"
                ),
            )


        st.info(
            "This QA sample is a practical sanity check, "
            "not the main statistical evaluation. "
            "The final held-out test set remains the primary "
            "measure of model performance."
        )


        # =================================================
        # QA DETAILS
        # =================================================

        qa_display = (
            successful_qa[
                [
                    "listing_name",
                    "advertised_price_usd",
                    "estimated_price_usd",
                    "percentage_error",
                    "inside_range",
                ]
            ]
            .copy()
        )


        qa_display = (
            qa_display.rename(
                columns={
                    "listing_name":
                        "Listing",

                    "advertised_price_usd":
                        "Advertised Price",

                    "estimated_price_usd":
                        "PropertyLens Estimate",

                    "percentage_error":
                        "Error (%)",

                    "inside_range":
                        "Inside Range",
                }
            )
        )


        with st.expander(
            "See real-world QA examples"
        ):

            st.dataframe(
                qa_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Advertised Price":
                        st.column_config.NumberColumn(
                            format="$%.0f",
                        ),

                    "PropertyLens Estimate":
                        st.column_config.NumberColumn(
                            format="$%.0f",
                        ),

                    "Error (%)":
                        st.column_config.NumberColumn(
                            format="%.2f%%",
                        ),

                    "Inside Range":
                        st.column_config.CheckboxColumn(),
                },
            )


else:

    st.info(
        "Real-world QA results are not available."
    )


st.divider()


# =========================================================
# HOW TO READ THE METRICS
# =========================================================

st.subheader(
    "How to Read These Metrics"
)


with st.expander(
    "Explain the metrics in simple language"
):

    st.markdown(
        """
        **MAE — Mean Absolute Error**

        Shows the average dollar difference between the
        model estimate and the advertised asking price.

        **MAPE — Mean Absolute Percentage Error**

        Shows the average percentage difference between
        the estimate and advertised price.

        **RMSE — Root Mean Squared Error**

        Gives more weight to large prediction errors.
        It can become large when a few expensive luxury
        properties are difficult to predict.

        **Log RMSE**

        Measures prediction error after prices are
        transformed to a logarithmic scale. This helps
        evaluate properties across a very wide range
        of asking prices.

        **R²**

        Measures how much of the variation in prices
        is explained by the model. Higher values are
        generally better.
        """
    )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Model performance is based on advertised property "
    "listing data and should not be interpreted as an "
    "official property valuation accuracy guarantee."
)