import streamlit as st


def apply_custom_css():
    """
    Inject modern glassmorphism, card view, and theme CSS variables into Streamlit.
    """
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
        
        :root {
            --bg-color: #0B0F17;
            --text-color: #F8FAFC;
            --secondary-text-color: #94A3B8;
            --panel-bg: rgba(15, 23, 42, 0.75);
            --panel-border: rgba(255, 255, 255, 0.08);
            --panel-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.5);
            --card-bg: rgba(30, 41, 59, 0.65);
            --card-border: rgba(255, 255, 255, 0.08);
            --card-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
            --badge-bg: rgba(56, 189, 248, 0.15);
            --badge-text: #38BDF8;
            --divider-color: rgba(255, 255, 255, 0.08);
        }

        html, body, [class*="css"] {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            color: var(--text-color);
        }

        .main {
            background-color: var(--bg-color);
        }
        
        /* ── Glassmorphism Section Panels ────────────────────────────────── */
        .glass-panel {
            background: var(--panel-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--panel-border);
            border-radius: 16px;
            box-shadow: var(--panel-shadow);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .glass-panel:hover {
            border-color: rgba(56, 189, 248, 0.3);
            box-shadow: 0 14px 35px rgba(0, 0, 0, 0.4);
        }
        
        /* ── Glassmorphism KPI Metric Cards View ──────────────────────────── */
        .metric-card {
            background: rgba(30, 41, 59, 0.65);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 18px 20px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }
        .metric-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, #38BDF8, #8B5CF6);
            opacity: 0.8;
        }
        .metric-card:hover {
            transform: translateY(-4px);
            border-color: rgba(56, 189, 248, 0.4);
            box-shadow: 0 16px 32px rgba(56, 189, 248, 0.15);
        }
        .metric-label {
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #94A3B8;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .metric-value {
            font-size: 1.75rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: #F8FAFC;
            background: linear-gradient(135deg, #F8FAFC 30%, #CBD5E1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .metric-sub {
            font-size: 0.78rem;
            color: #64748B;
            margin-top: 4px;
            font-weight: 500;
        }
        
        .header-badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 12px;
            border-radius: 9999px;
            background: var(--badge-bg);
            color: var(--badge-text);
            font-weight: 700;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            margin-bottom: 12px;
            border: 1px solid rgba(56, 189, 248, 0.2);
        }

        .custom-divider {
            margin: 28px 0;
            border: none;
            height: 1px;
            background: var(--divider-color);
        }

        div[data-testid="stExpander"] {
            background: rgba(30, 41, 59, 0.6) !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            border-radius: 14px !important;
            overflow: hidden !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3) !important;
            backdrop-filter: blur(12px) !important;
        }
        div[data-testid="stExpander"] summary {
            font-weight: 700 !important;
            color: #F8FAFC !important;
        }

        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

def style_donor_classifications(df_input):
    """
    Applies custom background color badges to Lifetime Donor Classification
    and Transaction Donor Classification columns for gorgeous visual distinction.
    """
    if df_input.empty:
        return df_input

    def _color_tier(val):
        s_val = str(val).strip()
        if "Super High" in s_val:
            return "background-color: rgba(236, 72, 153, 0.35); color: #F472B6; font-weight: 700; border-radius: 6px;"
        elif "High" in s_val:
            return "background-color: rgba(245, 158, 11, 0.35); color: #FBBF24; font-weight: 700; border-radius: 6px;"
        elif "Medium Low" in s_val:
            return "background-color: rgba(56, 189, 248, 0.35); color: #38BDF8; font-weight: 700; border-radius: 6px;"
        elif "Medium" in s_val:
            return "background-color: rgba(16, 185, 129, 0.35); color: #34D399; font-weight: 700; border-radius: 6px;"
        elif "Low End" in s_val:
            return "background-color: rgba(148, 163, 184, 0.30); color: #CBD5E1; font-weight: 700; border-radius: 6px;"
        return ""

    styler = df_input.style
    float_cols = df_input.select_dtypes(include=['float', 'float64']).columns
    if len(float_cols) > 0:
        styler = styler.format("{:.2f}", subset=float_cols, na_rep="")

    target_cols = [c for c in ["Lifetime Donor Classification", "Transaction Donor Classification"] if c in df_input.columns]
    if target_cols:
        styler = styler.map(_color_tier, subset=target_cols)
    return styler
