import streamlit as st


# =========================================================
# SECTION HEADER
# =========================================================

def section_header(
    title,
    subtitle=None,
    icon=None,
):
    prefix = f"{icon} " if icon else ""
    st.markdown(
        f'<div class="pp-section-header">'
        f"<h2>{prefix}{title}</h2>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if subtitle:
        st.caption(subtitle)


# =========================================================
# HERO BANNER
# =========================================================

def hero_banner(title, description, caption=None):
    caption_html = ""
    if caption:
        caption_html = f"<p>{caption}</p>"

    st.markdown(
        f'<div class="pp-hero">'
        f"<h1>{title}</h1>"
        f"<p>{description}</p>"
        f"{caption_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


# =========================================================
# METRIC CARDS ROW
# =========================================================

def metric_cards(
    items,
    columns=None,
):
    """Render a row of metric cards.

    items: list of dicts with keys:
        - label: str
        - value: str
        - icon: str (optional, material icon name)
    """
    n = len(items)
    cols = columns or st.columns(n, gap="medium")

    for col, item in zip(cols, items):
        icon_html = ""
        if item.get("icon"):
            icon_html = (
                f'<span class="pp-metric-icon">'
                f"{item['icon']}"
                f"</span>"
            )

        with col:
            st.markdown(
                f'<div class="pp-metric-card">'
                f"{icon_html}"
                f'<div class="pp-metric-label">'
                f"{item['label']}"
                f"</div>"
                f'<div class="pp-metric-value">'
                f"{item['value']}"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# =========================================================
# LARGE METRIC CARDS (2-3 columns)
# =========================================================

def metric_cards_large(items, gap="large"):
    n = len(items)
    cols = st.columns(n, gap=gap)

    for col, item in zip(cols, items):
        icon_html = ""
        if item.get("icon"):
            icon_html = (
                f'<span class="pp-metric-icon">'
                f"{item['icon']}"
                f"</span>"
            )

        with col:
            st.markdown(
                f'<div class="pp-metric-card">'
                f"{icon_html}"
                f'<div class="pp-metric-label">'
                f"{item['label']}"
                f"</div>"
                f'<div class="pp-metric-value pp-metric-value-lg">'
                f"{item['value']}"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# =========================================================
# PRICE DISPLAY (centered main price)
# =========================================================

def price_display(
    price,
    label="ESTIMATED ASKING PRICE",
    subtitle=None,
):
    subtitle_html = ""
    if subtitle:
        subtitle_html = (
            f'<div class="pp-price-sub">{subtitle}</div>'
        )

    st.markdown(
        f'<div class="pp-price-main">'
        f'<div class="pp-price-label">{label}</div>'
        f'<div class="pp-price-value">'
        f"${price:,.0f}"
        f"</div>"
        f"{subtitle_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


# =========================================================
# PRICE RANGE DISPLAY
# =========================================================

def price_range_display(lower, upper):
    st.markdown(
        f'<div class="pp-range-wrapper">'
        f'<div class="pp-range-title">Estimated Price Range</div>'
        f'<div class="pp-range-row">'
        f'<div class="pp-range-box">'
        f'<div class="pp-range-label">Lower</div>'
        f'<div class="pp-range-value">${lower:,.0f}</div>'
        f'</div>'
        f'<div class="pp-range-arrow">→</div>'
        f'<div class="pp-range-box">'
        f'<div class="pp-range-label">Upper</div>'
        f'<div class="pp-range-value">${upper:,.0f}</div>'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# =========================================================
# IMPACT BADGE
# =========================================================

def impact_badge(level):
    level_lower = level.lower()
    if level_lower == "strong":
        cls = "pp-badge-red"
    elif level_lower == "moderate":
        cls = "pp-badge-amber"
    elif level_lower == "small":
        cls = "pp-badge-green"
    else:
        cls = "pp-badge-blue"

    return (
        f'<span class="pp-badge {cls}">'
        f"{level}"
        f"</span>"
    )


# =========================================================
# PROPERTY DETAIL ITEM
# =========================================================

def detail_item(icon, label, value):
    return (
        f'<div class="pp-detail-item">'
        f'<span class="pp-detail-icon">'
        f"{icon}"
        f"</span>"
        f"<div>"
        f'<div class="pp-detail-label">{label}</div>'
        f'<div class="pp-detail-value">{value}</div>'
        f"</div>"
        f"</div>"
    )


# =========================================================
# DISCLAIMER
# =========================================================

def disclaimer(text):
    st.markdown(
        f'<div class="pp-disclaimer">'
        f"ℹ️ {text}"
        f"</div>",
        unsafe_allow_html=True,
    )


# =========================================================
# STEP CARD (for methodology)
# =========================================================

def step_card(number, title, description):
    return (
        f'<div class="pp-step-card">'
        f'<div class="pp-step-number">{number}</div>'
        f'<div class="pp-step-title">{title}</div>'
        f'<div class="pp-step-desc">{description}</div>'
        f"</div>"
    )


# =========================================================
# RECOMMENDATION CARD
# =========================================================

def recommendation_card(
    accent_class,
    title,
    district,
    metrics,
):
    """Build a recommendation card HTML string.

    accent_class: one of pp-rec-blue, pp-rec-green, pp-rec-violet, pp-rec-amber
    metrics: list of (label, value) tuples
    """
    metrics_html = "".join(
        f'<div style="margin-top:0.3rem;">'
        f'<span style="font-size:0.75rem;color:#64748B;">'
        f"{label}: "
        f"</span>"
        f'<span style="font-size:0.9rem;font-weight:600;color:#1E293B;">'
        f"{value}"
        f"</span>"
        f"</div>"
        for label, value in metrics
    )

    return (
        f'<div class="pp-rec-card {accent_class}">'
        f'<div style="font-size:0.7rem;font-weight:600;'
        f"text-transform:uppercase;letter-spacing:0.06em;"
        f'color:#64748B;margin-bottom:0.35rem;">'
        f"{title}"
        f"</div>"
        f'<div style="font-size:1.2rem;font-weight:700;'
        f"color:#0F172A;margin-bottom:0.5rem;\">"
        f"{district}"
        f"</div>"
        f"{metrics_html}"
        f"</div>"
    )
