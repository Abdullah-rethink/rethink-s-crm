import pandas as pd
import streamlit as st

from config.settings import DONOR_TIER_ORDER
from core.auth import change_user_password
from core.auth_bridge import clear_local_storage_auth


def render_sidebar_user_pill(user_session):
    """Renders user account status badge, sign out button, and password manager expander."""
    role_badge = "⚡ SUPER ADMIN" if user_session.get("role") == "super_admin" else "👤 ADMIN"
    user_display = user_session.get('email', user_session.get('username', 'User'))
    
    st.sidebar.markdown(f"""
    <div style="background: rgba(30, 41, 59, 0.7); padding: 10px 14px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.08); margin-bottom: 12px;">
        <div style="color: #94A3B8; font-size: 0.75rem; font-weight: 700; text-transform: uppercase;">Authenticated Account</div>
        <div style="color: #F8FAFC; font-weight: 800; font-size: 0.9rem; text-overflow: ellipsis; overflow: hidden;">{user_display}</div>
        <div style="margin-top: 4px;"><span class="header-badge" style="margin: 0; font-size: 0.65rem; padding: 2px 8px;">{role_badge}</span></div>
    </div>
    """, unsafe_allow_html=True)

    if st.sidebar.button("🚪 Sign Out", key="sidebar_sign_out_btn", use_container_width=True):
        clear_local_storage_auth()
        if "session_user" in st.query_params:
            del st.query_params["session_user"]
        st.session_state.pop("authenticated_user", None)
        st.session_state.pop("last_activity_time", None)
        st.rerun()

    with st.sidebar.expander("🔐 Account Security & Password"):
        with st.form("sidebar_pwd_form", clear_on_submit=False):
            sb_old_pwd = st.text_input("Current Password", type="password", key="sb_change_old_pwd")
            sb_new_pwd = st.text_input("New Password", type="password", key="sb_change_new_pwd")
            submit_sb_pwd = st.form_submit_button("Update Password", use_container_width=True)

        if submit_sb_pwd:
            if not sb_old_pwd or not sb_new_pwd:
                st.warning("Please enter current and new password.")
            else:
                with st.spinner("Updating password..."):
                    ok, msg = change_user_password(user_display, sb_old_pwd, sb_new_pwd)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

def render_sidebar_filters(df_raw):
    """
    Renders global interactive filter controls in the Streamlit sidebar.
    Returns filtered DataFrame copy.
    """
    if df_raw.empty:
        return df_raw

    df = df_raw.copy()
    col_campaign = "Campaign Name"
    col_community = "Community Name"
    col_heading = "Heading"
    col_subheading = "Sub-Heading"
    col_date = "Created Date (UTC)"

    # Reset Filters Button
    if st.sidebar.button("🔄 Reset All Filters", use_container_width=True):
        st.rerun()

    # Sidebar Group 1: Payment Frequency & Donor Tier
    st.sidebar.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    st.sidebar.subheader("💳 Payment & Classification")

    freq_options = ["All Payment Types", "Recurring Payment", "One-Time Payment"]
    selected_freq = st.sidebar.selectbox("Filter by Payment Frequency", freq_options)
    if selected_freq != "All Payment Types" and "Payment Frequency" in df.columns:
        df = df[df["Payment Frequency"] == selected_freq]

    donor_tier_options = ["All Classifications"] + DONOR_TIER_ORDER
    selected_tier = st.sidebar.selectbox("Filter by Lifetime LTV Tier", donor_tier_options)
    if selected_tier != "All Classifications" and "Lifetime Donor Classification" in df.columns:
        df = df[df["Lifetime Donor Classification"] == selected_tier]

    # Sidebar Group 2: Data Source & Categories
    st.sidebar.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    st.sidebar.subheader("📁 Data Source & Category")

    if "Source" in df.columns and not df["Source"].dropna().empty:
        sources = sorted([str(s) for s in df["Source"].dropna().unique() if str(s).strip() != ""])
        if sources:
            source_options = ["All Sources (Combined)"] + sources + ["Custom Combined (Multiselect)..."]
            selected_source_mode = st.sidebar.selectbox("Filter by Source", source_options)
            
            if selected_source_mode == "All Sources (Combined)":
                pass
            elif selected_source_mode == "Custom Combined (Multiselect)...":
                selected_sources = st.sidebar.multiselect("Select Sources", options=sources, default=sources)
                if selected_sources:
                    df = df[df["Source"].isin(selected_sources)]
                else:
                    df = df.iloc[0:0]
            else:
                df = df[df["Source"] == selected_source_mode]

    if col_heading in df.columns:
        headings_all = sorted({str(c).strip() for c in df[col_heading].dropna() if str(c).strip() != ""})
        headings = ["All Headings"] + headings_all
        selected_heading = st.sidebar.selectbox("Filter by Heading", headings)
        if selected_heading != "All Headings":
            df = df[df[col_heading].astype(str).str.strip() == selected_heading]

    if col_subheading in df.columns:
        subheadings_all = sorted({str(c).strip() for c in df[col_subheading].dropna() if str(c).strip() != ""})
        subheadings = ["All Sub-Headings"] + subheadings_all
        selected_subheading = st.sidebar.selectbox("Filter by Sub-Heading", subheadings)
        if selected_subheading != "All Sub-Headings":
            df = df[df[col_subheading].astype(str).str.strip() == selected_subheading]

    if "Country" in df.columns:
        countries_all = sorted({str(c).strip() for c in df["Country"].dropna() if str(c).strip() != ""})
        proj_countries = ["All Project Countries"] + countries_all
        selected_proj_country = st.sidebar.selectbox("Filter by Project Country", proj_countries)
        if selected_proj_country != "All Project Countries":
            df = df[df["Country"].astype(str).str.contains(selected_proj_country, case=False, regex=False, na=False)]

    if "Code" in df.columns:
        codes_all = sorted({str(c).strip() for c in df["Code"].dropna() if str(c).strip() != ""})
        codes = ["All Codes"] + codes_all
        selected_code = st.sidebar.selectbox("Filter by Code", codes)
        if selected_code != "All Codes":
            df = df[df["Code"].astype(str).str.strip() == selected_code]

    if "Zakat Eligibility" in df.columns:
        z_all = sorted({str(c).strip() for c in df["Zakat Eligibility"].dropna() if str(c).strip() != ""})
        z_options = ["All Zakat Status"] + z_all
        selected_zakat = st.sidebar.selectbox("Filter by Zakat Eligibility", z_options)
        if selected_zakat != "All Zakat Status":
            df = df[df["Zakat Eligibility"].astype(str).str.strip() == selected_zakat]

    # Sidebar Group 3: Date Range & Location
    st.sidebar.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    st.sidebar.subheader("📅 Date Range & Location")

    if col_date in df.columns and not df[col_date].dropna().empty:
        try:
            dates = pd.to_datetime(df[col_date], errors='coerce').dropna()
            if not dates.empty:
                min_date = dates.min().date()
                max_date = dates.max().date()
                all_time = st.sidebar.checkbox("All Time", value=True, key="date_all_time")
                if not all_time:
                    date_range = st.sidebar.date_input("Date Range (UTC)", value=(min_date, max_date))
                    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
                        start_d, end_d = date_range
                        df = df[(dates.dt.date >= start_d) & (dates.dt.date <= end_d)]
        except Exception:
            pass

    if "Billing Country" in df.columns:
        b_countries = ["All Donor Countries"] + sorted([str(c) for c in df["Billing Country"].dropna().unique() if str(c).strip() != ""])
        selected_country = st.sidebar.selectbox("Filter by Donor Billing Country", b_countries)
        if selected_country != "All Donor Countries":
            df = df[df["Billing Country"] == selected_country]

    search_term = st.sidebar.text_input("🔍 Search Campaign / Community", "")
    if search_term.strip() and col_campaign in df.columns:
        term = search_term.strip().lower()
        match_mask = df[col_campaign].astype(str).str.lower().str.contains(term, na=False)
        if col_community in df.columns:
            match_mask = match_mask | df[col_community].astype(str).str.lower().str.contains(term, na=False)
        df = df[match_mask]

    # Active Filter Match Pill
    pct_shown = (len(df) / len(df_raw) * 100) if len(df_raw) > 0 else 0
    st.sidebar.markdown(f"""
    <div style="background: rgba(30, 41, 59, 0.7); padding: 10px 14px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.08); text-align: center; margin-top: 10px;">
        <span style="color: #94A3B8; font-size: 0.8rem; font-weight: 600;">ACTIVE FILTER MATCH</span><br>
        <span style="color: #38BDF8; font-size: 1.1rem; font-weight: 800;">{len(df):,}</span> 
        <span style="color: #64748B; font-size: 0.85rem;">/ {len(df_raw):,} ({pct_shown:.1f}%)</span>
    </div>
    """, unsafe_allow_html=True)

    return df
