import os
import sys
import time

# Ensure project root directory is on Python path for Streamlit Cloud Linux containers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import streamlit as st

# Page configuration
st.set_page_config(
    page_title="Crowdfunding Analytics Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Allow Pandas Styler to render large tables
pd.set_option('styler.render.max_elements', 50000000)

# Import Modular Component Architecture
from components.metrics import format_currency, format_number
from components.sidebar import render_sidebar_filters, render_sidebar_user_pill
from config.settings import SESSION_TIMEOUT_SECONDS
from config.styles import apply_custom_css
from core.auth import authenticate_user, change_user_password, init_user_db
from core.data_processor import load_data, process_and_upload_excel
from views.admin_view import render_admin_tab
from views.classification_view import render_classification_tab
from views.explorer_view import render_explorer_tab
from views.ltv_view import render_ltv_tab
from views.overview_view import render_overview_tab

# Apply Custom Glassmorphism Theme CSS
apply_custom_css()

# Initialize User Auth Database
init_user_db()

# ── Authentication Router & Session Inactivity Check ───────────────────────
def render_auth_screen():
    if st.session_state.get("authenticated_user"):
        last_active = st.session_state.get("last_activity_time", time.time())
        now = time.time()
        
        if (now - last_active) > SESSION_TIMEOUT_SECONDS:
            idle_mins = int((now - last_active) // 60)
            st.session_state.pop("authenticated_user", None)
            st.session_state.pop("last_activity_time", None)
            st.warning(f"🔒 **Session Expired:** You were automatically signed out after {idle_mins} minutes of inactivity. Please log in again.")
        else:
            st.session_state["last_activity_time"] = now
            return st.session_state["authenticated_user"]

    st.markdown("<br>", unsafe_allow_html=True)
    _c1, c2, _c3 = st.columns([2, 5, 2])
    with c2:
        st.markdown("""
        <div class="glass-panel" style="text-align: center; padding: 32px 28px; margin-top: 10px; border-left: 4px solid #38BDF8;">
            <div style="font-size: 2.2rem; font-weight: 800; margin-bottom: 6px;">🔒 Secure Access Control</div>
            <div style="color: #94A3B8; font-size: 0.95rem;">Please log in with your credentials to access the Crowdfunding Analytics Engine.</div>
        </div>
        """, unsafe_allow_html=True)

        auth_tab_login, auth_tab_change = st.tabs(["🔑 Sign In", "🔐 Change Password"])

        with auth_tab_login:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.form("login_form", clear_on_submit=False):
                login_identity = st.text_input("Email or Username", placeholder="e.g. superadmin@analytics.com", key="auth_login_identity")
                login_password = st.text_input("Password", type="password", placeholder="Enter your password...", key="auth_login_password")
                submit_login = st.form_submit_button("🚀 Log In to Dashboard", type="primary", use_container_width=True)

            if submit_login:
                if not login_identity.strip() or not login_password.strip():
                    st.error("Please enter both email/username and password.")
                else:
                    with st.spinner("Authenticating credentials..."):
                        user = authenticate_user(login_identity, login_password)
                        if user:
                            st.session_state["authenticated_user"] = user
                            st.session_state["last_activity_time"] = time.time()
                            st.rerun()
                        else:
                            st.error("❌ Invalid credentials or user not found. Please try again.")

        with auth_tab_change:
            st.markdown("<br>", unsafe_allow_html=True)
            st.caption("Change your password by providing your email/username and current password.")
            with st.form("change_pwd_form", clear_on_submit=False):
                ch_user = st.text_input("Email / Username", placeholder="e.g. admin@analytics.com", key="auth_tab_ch_user")
                ch_old_p = st.text_input("Current Password", type="password", placeholder="Current password...", key="auth_tab_ch_old_p")
                ch_new_p = st.text_input("New Password", type="password", placeholder="At least 6 characters...", key="auth_tab_ch_new_p")
                submit_change = st.form_submit_button("💾 Change Password Now", type="primary", use_container_width=True)

            if submit_change:
                if not ch_user.strip() or not ch_old_p or not ch_new_p:
                    st.warning("Please fill in all fields.")
                else:
                    with st.spinner("Updating password..."):
                        succeeded, feedback = change_user_password(ch_user.strip(), ch_old_p, ch_new_p)
                        if succeeded:
                            st.success(feedback)
                        else:
                            st.error(feedback)

    st.stop()

# Gated App Entry Point
user_session = render_auth_screen()

# Render Sidebar Account Status
render_sidebar_user_pill(user_session)

# Load Primary Dataset Cache
if "df_raw" not in st.session_state:
    with st.spinner("⚡ Loading Crowdfunding Analytics Engine..."):
        st.session_state["df_raw"] = load_data()

df_raw = st.session_state["df_raw"]

# Empty Database Onboarding UI
if df_raw.empty:
    st.title("⚡ Crowdfunding Analytics Engine")
    st.info("Welcome! Your database is currently empty. Please upload your campaign export files to get started.")
    uploaded_files = st.file_uploader("📂 Upload Export File(s)", type=["csv", "xlsx"], accept_multiple_files=True)
    if uploaded_files:
        if st.button("🚀 Process & Load Dashboard", type="primary", use_container_width=True):
            with st.spinner("Processing files..."):
                for uf in uploaded_files:
                    process_and_upload_excel(uf)
                st.session_state.pop("df_raw", None)
                st.rerun()
    st.stop()

# Render Active Sidebar Filters Panel
df = render_sidebar_filters(df_raw)
col_amount = "Total Online Donations Net Amount in Settled Currency"
if col_amount not in df.columns:
    col_amount = "Donation Amount in Project Currency (May be approx.)"
if col_amount not in df.columns:
    col_amount = "Donation Amount (in Donation Currency)"

col_campaign = "Campaign Name"
col_community = "Community Name"
col_heading = "Heading"
col_date = "Created Date (UTC)"

# Dashboard Main Header
st.title("⚡ Crowdfunding Analytics Engine")
st.markdown("Unified Intelligence & Lifetime Donor Value Platform")
st.markdown("<br>", unsafe_allow_html=True)

# Top KPI Metric Row (Glassmorphism Cards View)
m1, m2, m3, m4, m5, m6 = st.columns(6)
total_raised = df[col_amount].sum() if (not df.empty and col_amount in df.columns) else 0
total_txns = len(df)
avg_donation = df[col_amount].mean() if total_txns > 0 else 0
top_cat = df[col_heading].mode()[0] if (not df.empty and col_heading in df.columns and not df[col_heading].dropna().empty) else "N/A"
recurring_pct = (df["Payment Frequency"] == "Recurring Payment").mean() * 100 if (total_txns > 0 and "Payment Frequency" in df.columns) else 0
top_donor_seg = df["Lifetime Donor Classification"].mode()[0] if (not df.empty and "Lifetime Donor Classification" in df.columns and not df["Lifetime Donor Classification"].dropna().empty) else "N/A"

with m1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label"><span>Total Raised</span> <span>💰</span></div>
        <div class="metric-value">{format_currency(total_raised)}</div>
        <div class="metric-sub">{total_txns:,} donations</div>
    </div>
    """, unsafe_allow_html=True)

with m2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label"><span>Transactions</span> <span>📊</span></div>
        <div class="metric-value">{format_number(total_txns)}</div>
        <div class="metric-sub">Completed records</div>
    </div>
    """, unsafe_allow_html=True)

with m3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label"><span>Avg Donation</span> <span>💵</span></div>
        <div class="metric-value">{format_currency(avg_donation)}</div>
        <div class="metric-sub">Per transaction</div>
    </div>
    """, unsafe_allow_html=True)

with m4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label"><span>Recurring %</span> <span>🔄</span></div>
        <div class="metric-value">{recurring_pct:.1f}%</div>
        <div class="metric-sub">Repeat donor ratio</div>
    </div>
    """, unsafe_allow_html=True)

with m5:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label"><span>Top Donor Tier</span> <span>👑</span></div>
        <div class="metric-value" style="font-size: 1.25rem;">{top_donor_seg}</div>
        <div class="metric-sub">Largest tier segment</div>
    </div>
    """, unsafe_allow_html=True)

with m6:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label"><span>Top Category</span> <span>🏷️</span></div>
        <div class="metric-value" style="font-size: 1.25rem;">{str(top_cat)[:16]}</div>
        <div class="metric-sub">Most active category</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Main Tab Router ──────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Overview", 
    "👑 Lifetime LTV", 
    "🏷️ Campaign Classifications", 
    "📋 Data Explorer", 
    "⚙️ Admin & Data"
])

with tab1:
    render_overview_tab(df, col_amount, col_campaign, col_heading, col_date, currency_symbol="£")

with tab2:
    render_ltv_tab(df, col_amount, currency_symbol="£")

with tab3:
    render_classification_tab(user_session)

with tab4:
    render_explorer_tab(df, df_raw, user_session, col_amount, col_campaign, col_community)

with tab5:
    render_admin_tab(df_raw, user_session)
