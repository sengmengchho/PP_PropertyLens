import streamlit as st


_APP_CSS = """
<style>

/* ===== GLOBAL TYPOGRAPHY & SPACING ===== */

section[data-testid="stMainBlockContainer"] {
    padding-top: 1rem;
}

h1 {
    font-size: 2rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    color: #0F172A !important;
    margin-bottom: 0.25rem !important;
}

h2 {
    font-size: 1.45rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em !important;
    color: #1E293B !important;
}

h3 {
    font-size: 1.15rem !important;
    font-weight: 600 !important;
    color: #334155 !important;
}


/* ===== PAGE INTRO ===== */

.pp-intro {
    font-size: 1.05rem;
    color: #475569;
    line-height: 1.6;
    margin-bottom: 0.25rem;
    max-width: 640px;
}

.pp-caption-top {
    font-size: 0.82rem;
    color: #94A3B8;
    margin-top: -0.5rem;
    margin-bottom: 1rem;
}


/* ===== HERO BANNER ===== */

.pp-hero {
    background: linear-gradient(135deg, #EFF6FF 0%, #F0F9FF 50%, #F5F3FF 100%);
    border: 1px solid #DBEAFE;
    border-radius: 14px;
    padding: 1.75rem 2rem;
    margin-bottom: 1.25rem;
}

.pp-hero h1 {
    margin-bottom: 0.3rem !important;
}

.pp-hero p {
    color: #64748B;
    margin: 0;
    font-size: 0.95rem;
}


/* ===== SECTION HEADER ===== */

.pp-section-header {
    border-bottom: 2px solid #E2E8F0;
    padding-bottom: 0.4rem;
    margin-top: 1.75rem;
    margin-bottom: 0.5rem;
}

.pp-section-header h2 {
    margin-bottom: 0 !important;
}


/* ===== METRIC CARD ===== */

.pp-metric-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 1.1rem 1.25rem;
    text-align: center;
    transition: box-shadow 0.15s ease;
    height: 100%;
}

.pp-metric-card:hover {
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.pp-metric-label {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #94A3B8;
    margin-bottom: 0.35rem;
}

.pp-metric-value {
    font-size: 1.55rem;
    font-weight: 700;
    color: #0F172A;
    line-height: 1.2;
}

.pp-metric-value-lg {
    font-size: 2.2rem;
}

.pp-metric-icon {
    font-size: 1.3rem;
    margin-bottom: 0.3rem;
    display: block;
}


/* ===== PRICE DISPLAY ===== */

.pp-price-main {
    text-align: center;
    padding: 1.5rem 1rem;
}

.pp-price-label {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94A3B8;
    margin-bottom: 0.25rem;
}

.pp-price-value {
    font-size: 2.6rem;
    font-weight: 700;
    color: #1D4ED8;
    letter-spacing: -0.02em;
    line-height: 1.1;
}

.pp-price-sub {
    font-size: 0.82rem;
    color: #94A3B8;
    margin-top: 0.3rem;
}


/* ===== RESULT CARD ===== */

.pp-result-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 1.25rem;
    text-align: center;
}

.pp-result-card .pp-price-value {
    font-size: 2rem;
}

.pp-result-card .pp-price-label {
    font-size: 0.7rem;
}

.pp-range-lower {
    border-left: 3px solid #2563EB;
}

.pp-range-upper {
    border-left: 3px solid #7C3AED;
}


/* ===== PRICE RANGE (clean) ===== */

.pp-range-wrapper {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 1.25rem 1.5rem;
    text-align: center;
}

.pp-range-title {
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748B;
    margin-bottom: 0.75rem;
}

.pp-range-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1.25rem;
}

.pp-range-box {
    flex: 1;
    max-width: 220px;
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 0.75rem 1rem;
}

.pp-range-label {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #94A3B8;
    margin-bottom: 0.15rem;
}

.pp-range-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #1E293B;
}

.pp-range-arrow {
    font-size: 1.3rem;
    color: #CBD5E1;
    flex-shrink: 0;
}


/* ===== FACTOR CARDS ===== */

.pp-factor-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 1rem 1.1rem;
    text-align: center;
    height: 100%;
}

.pp-factor-icon {
    font-size: 1.5rem;
    margin-bottom: 0.2rem;
}

.pp-factor-name {
    font-size: 0.78rem;
    font-weight: 600;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.2rem;
}

.pp-factor-value {
    font-size: 1.1rem;
    font-weight: 700;
    color: #0F172A;
}

.pp-factor-impact {
    font-size: 0.72rem;
    font-weight: 500;
    margin-top: 0.25rem;
}

.pp-impact-strong { color: #DC2626; }
.pp-impact-moderate { color: #D97706; }
.pp-impact-small { color: #16A34A; }
.pp-impact-minimal { color: #94A3B8; }


/* ===== PROPERTY DETAIL GRID ===== */

.pp-detail-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0;
}

.pp-detail-icon {
    font-size: 1.1rem;
    color: #64748B;
    width: 24px;
    text-align: center;
}

.pp-detail-label {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #94A3B8;
}

.pp-detail-value {
    font-size: 0.95rem;
    font-weight: 600;
    color: #1E293B;
}


/* ===== DISCLAIMER ===== */

.pp-disclaimer {
    border-top: 1px solid #E2E8F0;
    padding-top: 1rem;
    margin-top: 2rem;
    font-size: 0.78rem;
    color: #94A3B8;
    line-height: 1.5;
}


/* ===== BADGES ===== */

.pp-badge {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}

.pp-badge-blue {
    background: #EFF6FF;
    color: #2563EB;
    border: 1px solid #BFDBFE;
}

.pp-badge-green {
    background: #F0FDF4;
    color: #16A34A;
    border: 1px solid #BBF7D0;
}

.pp-badge-violet {
    background: #F5F3FF;
    color: #7C3AED;
    border: 1px solid #DDD6FE;
}

.pp-badge-amber {
    background: #FFFBEB;
    color: #D97706;
    border: 1px solid #FDE68A;
}

.pp-badge-red {
    background: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FECACA;
}


/* ===== RECOMMENDATION CARDS ===== */

.pp-rec-card {
    border-radius: 12px;
    padding: 1.25rem;
    height: 100%;
}

.pp-rec-blue {
    background: #F8FAFC;
    border: 1px solid #BFDBFE;
    border-top: 3px solid #2563EB;
}

.pp-rec-green {
    background: #F8FAFC;
    border: 1px solid #BBF7D0;
    border-top: 3px solid #16A34A;
}

.pp-rec-violet {
    background: #F8FAFC;
    border: 1px solid #DDD6FE;
    border-top: 3px solid #7C3AED;
}

.pp-rec-amber {
    background: #F8FAFC;
    border: 1px solid #FDE68A;
    border-top: 3px solid #D97706;
}


/* ===== PIPELINE STEP CARDS ===== */

.pp-step-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 1rem 1.1rem;
    height: 100%;
}

.pp-step-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: #2563EB;
    color: #FFFFFF;
    font-size: 0.78rem;
    font-weight: 700;
    margin-bottom: 0.4rem;
}

.pp-step-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: #1E293B;
}

.pp-step-desc {
    font-size: 0.82rem;
    color: #64748B;
    line-height: 1.45;
    margin-top: 0.2rem;
}


/* ===== COMPARISON TABLE HIGHLIGHT ===== */

.pp-highlight-row {
    background: #F0F9FF !important;
}


/* ===== ALTAIR CHART CONTAINER ===== */

.pp-chart-wrapper {
    background: #FFFFFF;
    border: 1px solid #F1F5F9;
    border-radius: 10px;
    padding: 0.75rem;
    margin-bottom: 0.5rem;
}

</style>
"""


def inject_global_css():
    """Inject the shared application CSS once per page load."""
    st.markdown(_APP_CSS, unsafe_allow_html=True)
