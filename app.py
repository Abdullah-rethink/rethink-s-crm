import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import threading
from utils import (
    load_data, apply_custom_css, format_currency, format_number, 
    PLOTLY_COLORS, DONOR_TIER_ORDER, process_and_upload_excel, purge_all_data,
    get_classification_matrix, save_classification_matrix, update_source_tag,
    get_givebright_classification_matrix, save_givebright_classification_matrix,
    import_givebright_classifications_file, delete_single_dataset,
    sync_donor_classifications_to_matrix, get_cloud_sync_status, PARQUET_PATH,
    DATABASE_URL, LOCAL_DB_PATH
)

# Allow Pandas Styler to render large tables (up to 2M cells)
pd.set_option("styler.render.max_elements", 2_000_000)

st.set_page_config(
    page_title="Crowdfunding Analytics Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply sleek modern UI styling
apply_custom_css()

# Global Plotly Theme Settings for a cleaner dark mode look
import plotly.io as pio
pio.templates["custom_dark"] = pio.templates["plotly_dark"]
pio.templates["custom_dark"].layout.update(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Plus Jakarta Sans", color="#94A3B8"),
    xaxis=dict(showgrid=False, zeroline=False),
    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=False),
)
pio.templates.default = "custom_dark"

# Header Section
st.markdown('<div class="header-badge">⚡ Multi-Source Crowdfunding Analytics</div>', unsafe_allow_html=True)
st.title("Crowdfunding Analytics Dashboard")
st.markdown("Explore campaign performance, donor classification, payment frequency (recurring vs. one-time), and fundraising growth across your LaunchGood & GiveBright datasets.")

st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

# ── Cloud Sync Status Banner ──────────────────────────────────────────────────
_sync_status = get_cloud_sync_status()
if _sync_status is not None:
    if not _sync_status.get("success", True):
        st.error(
            f"⚠️ **Cloud Sync Failed** — Last operation: `{_sync_status.get('operation','?')}` "
            f"at {_sync_status.get('timestamp','?')}  \n"
            f"Error: `{_sync_status.get('error','Unknown error')}`  \n"
            f"**Your data is safely saved locally (Parquet + SQLite). "
            f"Click Retry below or re-save any record to re-attempt cloud sync.**"
        )
        if st.button("🔄 Retry Cloud Sync Now", key="retry_cloud_sync_btn"):
            with st.spinner("Syncing all data to Supabase cloud..."):
                import io, psycopg2
                from utils import DATABASE_URL, _write_sync_status
                try:
                    df_retry = pd.read_parquet(PARQUET_PATH)
                    buf = io.StringIO()
                    df_retry.to_csv(buf, index=False, header=False, sep='\t', na_rep='')
                    buf.seek(0)
                    _conn = psycopg2.connect(DATABASE_URL)
                    _cur = _conn.cursor()
                    _cur.execute('DROP TABLE IF EXISTS "donations";')
                    _cols_def = ', '.join([f'"{c}" TEXT' for c in df_retry.columns])
                    _cur.execute(f'CREATE TABLE "donations" ({_cols_def});')
                    _conn.commit()
                    _tc = ', '.join([f'"{c}"' for c in df_retry.columns])
                    _cur.copy_expert(f"COPY \"donations\" ({_tc}) FROM STDIN WITH (FORMAT csv, DELIMITER '\t', NULL '');", buf)
                    _conn.commit()
                    _cur.close()
                    _conn.close()
                    _write_sync_status(True, "manual retry")
                    st.success("✅ Cloud sync successful! All data is now up to date in Supabase.")
                    st.rerun()
                except Exception as _retry_err:
                    _write_sync_status(False, "manual retry", str(_retry_err))
                    st.error(f"Retry failed: {_retry_err}")
    else:
        st.caption(f"☁️ Cloud sync: ✅ `{_sync_status.get('operation','?')}` — {_sync_status.get('timestamp','?')}")

# Sidebar Configuration & Filters
st.sidebar.header("🎯 Dataset & Global Filters")


# Data Loading from Database / Parquet Cache
if "df_raw" not in st.session_state:
    st.session_state["df_raw"] = load_data()
df_raw = st.session_state["df_raw"]

# Empty State Onboarding Screen
if df_raw.empty:
    st.info("📭 **No data loaded in database yet.** Drag and drop your LaunchGood or GiveBright export file below to initialize your dashboard.")
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    
    subheader_text = "📁 Quick Data Onboarding"
    st.subheader(subheader_text)
    up_col1, up_col2 = st.columns([6, 4])
    with up_col1:
        uploaded_files = st.file_uploader("Choose Campaign Export File(s) (.xlsx, .csv)", type=["xlsx", "csv"], accept_multiple_files=True, key="onboarding_file_uploader")
        platform_choice = st.radio("Platform Adapter", options=["📁 Auto-Detect", "⚡ LaunchGood", "🎁 GiveBright"], horizontal=True, key="onboarding_platform_choice")
    with up_col2:
        source_label_input = st.text_input("Dataset Tag / Name (Optional)", placeholder="e.g. Master Dataset, GiveBright 2026", key="onboarding_source_label")
        st.caption("Tag this dataset to easily distinguish or combine multiple file uploads in the sidebar.")
    
    if uploaded_files:
        if st.button("🚀 Process & Load Dashboard", type="primary", use_container_width=True, key="onboarding_process_btn"):
            src_arg = source_label_input.strip() if source_label_input.strip() else None
            plt_arg = "auto"
            if "GiveBright" in platform_choice:
                plt_arg = "givebright"
            elif "LaunchGood" in platform_choice:
                plt_arg = "launchgood"
                
            with st.spinner(f"⚙️ Standardizing schema & processing {len(uploaded_files)} file(s)..."):
                try:
                    total_loaded = 0
                    for idx, uf in enumerate(uploaded_files):
                        file_mode = "replace" if idx == 0 else "append"
                        tag_name = src_arg if (src_arg and len(uploaded_files) == 1) else (f"{src_arg} ({uf.name})" if src_arg else None)
                        n = process_and_upload_excel(uf, source_name=tag_name, upload_mode=file_mode, platform=plt_arg)
                        total_loaded += n
                    st.session_state.pop("df_raw", None)
                    st.success(f"✅ Successfully loaded and enriched {total_loaded:,} records across {len(uploaded_files)} file(s)! Launching dashboard...")
                    st.rerun()
                except Exception as e:
                    st.error(f"Upload failed: {e}")
    st.stop()

# One-time database column/value alignment migration
if not df_raw.empty:
    modified = False
    # Ensure Settled Net is present
    if "Total Online Donations Net Amount in Settled Currency" not in df_raw.columns and "Donation Amount in Project Currency (May be approx.)" in df_raw.columns:
        df_raw["Total Online Donations Net Amount in Settled Currency"] = df_raw["Donation Amount in Project Currency (May be approx.)"]
        modified = True
    elif "Total Online Donations Net Amount in Settled Currency" in df_raw.columns:
        gb_mask = (df_raw["Platform"] == "GiveBright") & (df_raw["Total Online Donations Net Amount in Settled Currency"].isna())
        if gb_mask.any():
            df_raw.loc[gb_mask, "Total Online Donations Net Amount in Settled Currency"] = df_raw.loc[gb_mask, "Donation Amount in Project Currency (May be approx.)"]
            modified = True
            
    if modified:
        from utils import PARQUET_PATH, LOCAL_DB_PATH
        import sqlite3
        df_raw.to_parquet(PARQUET_PATH, index=False)
        conn = sqlite3.connect(LOCAL_DB_PATH)
        df_raw.to_sql("donations", con=conn, if_exists="replace", index=False)
        conn.close()

# Detect and set currency symbol
currency_symbol = "£"  # Default
if not df_raw.empty:
    if "Settlement Currency" in df_raw.columns:
        active_curr = df_raw["Settlement Currency"].dropna().unique()
        if len(active_curr) == 1:
            curr_code = str(active_curr[0]).upper()
            if curr_code == "USD":
                currency_symbol = "$"
            elif curr_code == "CAD":
                currency_symbol = "C$"
            elif curr_code == "GBP":
                currency_symbol = "£"
            else:
                currency_symbol = curr_code + " "
        elif len(active_curr) > 1:
            currency_symbol = "Mixed "
    elif "Donation Currency (DC)" in df_raw.columns:
        active_curr = df_raw["Donation Currency (DC)"].dropna().unique()
        if len(active_curr) == 1:
            curr_code = str(active_curr[0]).upper()
            if curr_code == "USD":
                currency_symbol = "$"
            elif curr_code == "CAD":
                currency_symbol = "C$"
            elif curr_code == "GBP":
                currency_symbol = "£"
            else:
                currency_symbol = curr_code + " "
        elif len(active_curr) > 1:
            currency_symbol = "Mixed "

st.session_state["currency_symbol"] = currency_symbol

# Reset Filters Button
if not df_raw.empty:
    if st.sidebar.button("🔄 Reset All Filters", use_container_width=True):
        st.rerun()


# Work on a filtered copy
df = df_raw.copy()

# Column names resolution
col_amount = "Total Online Donations Net Amount in Settled Currency"
if col_amount not in df.columns:
    col_amount = "Donation Amount in Project Currency (May be approx.)"
if col_amount not in df.columns:
    col_amount = "Donation Amount (in Donation Currency)"
col_campaign = "Campaign Name"
col_community = "Community Name"
col_heading = "Heading"
col_subheading = "Sub-Heading"
col_date = "Created Date (UTC)"

# Sidebar Filters Group 1: Payment Frequency & Donor Tier
st.sidebar.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
st.sidebar.subheader("💳 Payment & Classification")

freq_options = ["All Payment Types", "Recurring Payment", "One-Time Payment"]
selected_freq = st.sidebar.selectbox("Filter by Payment Frequency", freq_options)
if selected_freq != "All Payment Types":
    df = df[df["Payment Frequency"] == selected_freq]

donor_tier_options = ["All Classifications"] + DONOR_TIER_ORDER
selected_tier = st.sidebar.selectbox("Filter by Lifetime LTV Tier", donor_tier_options)
if selected_tier != "All Classifications":
    df = df[df["Lifetime Donor Classification"] == selected_tier]

# Sidebar Filters Group 2: Data Source & Categories
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
    headings_all = sorted(list(set(str(c).strip() for c in df[col_heading].dropna() if str(c).strip() != "")))
    headings = ["All Headings"] + headings_all
    selected_heading = st.sidebar.selectbox("Filter by Heading", headings)
    if selected_heading != "All Headings":
        df = df[df[col_heading].astype(str).str.strip() == selected_heading]

if col_subheading in df.columns:
    subheadings_all = sorted(list(set(str(c).strip() for c in df[col_subheading].dropna() if str(c).strip() != "")))
    subheadings = ["All Sub-Headings"] + subheadings_all
    selected_subheading = st.sidebar.selectbox("Filter by Sub-Heading", subheadings)
    if selected_subheading != "All Sub-Headings":
        df = df[df[col_subheading].astype(str).str.strip() == selected_subheading]

if "Country" in df.columns:
    countries_all = sorted(list(set(str(c).strip() for c in df["Country"].dropna() if str(c).strip() != "")))
    proj_countries = ["All Project Countries"] + countries_all
    selected_proj_country = st.sidebar.selectbox("Filter by Project Country", proj_countries)
    if selected_proj_country != "All Project Countries":
        df = df[df["Country"].astype(str).str.contains(selected_proj_country, case=False, regex=False, na=False)]

if "Code" in df.columns:
    codes_all = sorted(list(set(str(c).strip() for c in df["Code"].dropna() if str(c).strip() != "")))
    codes = ["All Codes"] + codes_all
    selected_code = st.sidebar.selectbox("Filter by Code", codes)
    if selected_code != "All Codes":
        df = df[df["Code"].astype(str).str.strip() == selected_code]

if "Zakat Eligibility" in df.columns:
    z_all = sorted(list(set(str(c).strip() for c in df["Zakat Eligibility"].dropna() if str(c).strip() != "")))
    z_options = ["All Zakat Status"] + z_all
    selected_zakat = st.sidebar.selectbox("Filter by Zakat Eligibility", z_options)
    if selected_zakat != "All Zakat Status":
        df = df[df["Zakat Eligibility"].astype(str).str.strip() == selected_zakat]

# Sidebar Filters Group 3: Date & Location
st.sidebar.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
st.sidebar.subheader("📅 Date Range & Location")

if col_date and col_date in df.columns and not df[col_date].dropna().empty:
    min_date = df[col_date].min().date()
    max_date = df[col_date].max().date()
    
    all_time = st.sidebar.checkbox("All Time", value=True, key="date_all_time")
    if not all_time:
        date_range = st.sidebar.date_input("Date Range (UTC)", value=(min_date, max_date))
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start_d, end_d = date_range
            df = df[(df[col_date].dt.date >= start_d) & (df[col_date].dt.date <= end_d)]

if "Billing Country" in df.columns:
    countries = ["All Donor Countries"] + sorted([str(c) for c in df["Billing Country"].dropna().unique() if str(c).strip() != ""])
    selected_country = st.sidebar.selectbox("Filter by Donor Billing Country", countries)
    if selected_country != "All Donor Countries":
        df = df[df["Billing Country"] == selected_country]

search_term = st.sidebar.text_input("🔍 Search Campaign / Community", "")
if search_term.strip():
    term = search_term.strip().lower()
    match_mask = df[col_campaign].str.lower().str.contains(term, na=False)
    if col_community in df.columns:
        match_mask = match_mask | df[col_community].str.lower().str.contains(term, na=False)
    df = df[match_mask]

# Sidebar Status Pill
pct_shown = (len(df) / len(df_raw) * 100) if len(df_raw) > 0 else 0
st.sidebar.markdown(f"""
<div style="background: rgba(30, 41, 59, 0.7); padding: 10px 14px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.08); text-align: center; margin-top: 10px;">
    <span style="color: #94A3B8; font-size: 0.8rem; font-weight: 600;">ACTIVE FILTER MATCH</span><br>
    <span style="color: #38BDF8; font-size: 1.1rem; font-weight: 800;">{len(df):,}</span> 
    <span style="color: #64748B; font-size: 0.85rem;">/ {len(df_raw):,} ({pct_shown:.1f}%)</span>
</div>
""", unsafe_allow_html=True)

# --- KEY METRICS CARDS ---
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
        <div class="metric-value" style="color: {'#34D399' if recurring_pct > 20 else '#F8FAFC'};">{recurring_pct:.1f}%</div>
        <div class="metric-sub">Repeat donor ratio</div>
    </div>
    """, unsafe_allow_html=True)

with m5:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label"><span>Top Donor Tier</span> <span>👑</span></div>
        <div class="metric-value" style="font-size:1.15rem; line-height:1.4; padding-top: 4px;">{top_donor_seg}</div>
        <div class="metric-sub">Largest tier segment</div>
    </div>
    """, unsafe_allow_html=True)

with m6:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label"><span>Top Category</span> <span>🏷️</span></div>
        <div class="metric-value" style="font-size:1.15rem; line-height:1.4; padding-top: 4px;">{top_cat[:18]}</div>
        <div class="metric-sub">Most active category</div>
    </div>
    """, unsafe_allow_html=True)

# Unassigned Campaign Alert Banner
if not df.empty and "Heading" in df.columns:
    unassigned_count = (df["Heading"] == "Unassigned").sum()
    if unassigned_count > 0:
        st.warning(f"⚠️ **{unassigned_count:,} records** have unassigned campaign classifications. Head to the **🏷️ Campaign Classifications** tab to assign their Headings, Countries, and Zakat Eligibility.")

st.markdown("<br>", unsafe_allow_html=True)

# --- PERSISTENT SESSION STATE TAB NAVIGATION ---
TAB_OPTIONS = [
    "📈 Overview", 
    "👑 Lifetime LTV & Frequency", 
    "🔥 Campaigns & Headings",
    "🌍 Geography & Payment Insights",
    "🏷️ Campaign Classifications",
    "📋 Data Explorer & Export",
    "⚙️ Admin & Data Management"
]

if "active_dashboard_tab" not in st.session_state:
    st.session_state["active_dashboard_tab"] = TAB_OPTIONS[0]

selected_tab = st.radio(
    "Navigation Tabs",
    options=TAB_OPTIONS,
    index=TAB_OPTIONS.index(st.session_state["active_dashboard_tab"]) if st.session_state["active_dashboard_tab"] in TAB_OPTIONS else 0,
    horizontal=True,
    label_visibility="collapsed",
    key="active_dashboard_tab"
)

def render_classification_tab():
    st.header("🏷️ Campaign Classification Manager (Source of Truth)")
    st.markdown("This matrix is your **source of truth** for mapping (`Campaign Name`, `Community Name`) ➔ `Heading`, `Sub-Heading`, `Country`, `Code`, and `Zakat Eligibility`. Select a platform below to view or edit its rules:")
    
    matrix_platform = st.radio("Platform Matrix", options=["⚡ LaunchGood Matrix", "🎁 GiveBright Matrix"], horizontal=True, key="matrix_platform_toggle")
    
    state_key = f"matrix_df_{matrix_platform}"
    
    # Always re-read fresh from DB (which reads from live Parquet) so donor edits reflect instantly.
    # Only preserve in-memory state when the user has applied pending bulk edits (not yet saved).
    if st.session_state.get("prev_matrix_platform") != matrix_platform:
        # Platform switched — clear any pending unsaved edits for old platform
        st.session_state.pop(state_key, None)
        st.session_state["prev_matrix_platform"] = matrix_platform

    if state_key not in st.session_state:
        # No pending bulk edits → always fetch fresh from DB
        if matrix_platform == "⚡ LaunchGood Matrix":
            matrix_df = get_classification_matrix()
        else:
            matrix_df = get_givebright_classification_matrix()
    else:
        # User has pending in-memory bulk edits — use them, but show a warning
        matrix_df = st.session_state[state_key]
        st.info("⚠️ You have pending unsaved classification changes. Click **Save & Apply Rules Now** below to persist them, or click **Discard Changes** to reload from the database.")
        if st.button("🔄 Discard Changes & Reload from Database", key="discard_pending_matrix_changes"):
            st.session_state.pop(state_key, None)
            st.rerun()

    unassigned_count = (matrix_df["Heading"] == "Unassigned").sum() if "Heading" in matrix_df.columns else 0

    
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        st.metric("Total Tracked Campaigns", f"{len(matrix_df):,}")
    with col_c2:
        st.metric("Fully Classified Campaigns", f"{len(matrix_df) - unassigned_count:,}")
    with col_c3:
        st.metric("Unassigned Campaigns", f"{unassigned_count:,}")
        
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    
    # ── Export & Import Row ───────────────────────────────────────────
    ex1, ex2 = st.columns([1, 1])
    with ex1:
        csv_matrix = matrix_df.to_csv(index=False).encode('utf-8')
        fname_export = "launchgood_classifications.csv" if matrix_platform == "⚡ LaunchGood Matrix" else "givebright_classifications.csv"
        st.download_button(
            f"⬇️ Export {matrix_platform} Matrix (CSV)",
            csv_matrix,
            fname_export,
            "text/csv",
            use_container_width=True
        )
    with ex2:
        uploaded_matrix = st.file_uploader(f"📂 Import {matrix_platform} File (CSV/Excel)", type=["csv", "xlsx"], key="matrix_file_uploader")
        if uploaded_matrix is not None:
            if st.button("🚀 Bulk Load Classifications", use_container_width=True):
                try:
                    if matrix_platform == "⚡ LaunchGood Matrix":
                        if uploaded_matrix.name.endswith(".csv"):
                            imp_df = pd.read_csv(uploaded_matrix)
                        else:
                            imp_df = pd.read_excel(uploaded_matrix)
                        n_saved = save_classification_matrix(imp_df)
                    else:
                        n_saved = import_givebright_classifications_file(uploaded_matrix)
                    st.session_state.pop(state_key, None)
                    st.success(f"✅ Successfully loaded {n_saved:,} {matrix_platform} campaign classifications!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Import failed: {e}")
                    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # ── Filtering Controls ──────────────────────────────────────────
    st.subheader("🔍 Filter & Search Rules")
    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        search_term = st.text_input("Search Campaign / Community Name", placeholder="Type to filter...", key=f"mat_search_{matrix_platform}")
    with f_col2:
        avail_headings = ["All", "Unassigned"] + sorted(list(set(matrix_df["Heading"].dropna().astype(str).str.strip())))
        avail_headings = list(dict.fromkeys(avail_headings))
        filter_heading = st.selectbox("Filter by Heading", avail_headings, key=f"mat_f_head_{matrix_platform}")
    with f_col3:
        avail_zakat = ["All", "Unassigned", "Zakat", "Non-Zakat"]
        filter_zakat = st.selectbox("Filter by Zakat Eligibility", avail_zakat, key=f"mat_f_zak_{matrix_platform}")

    # Build mask
    mask = pd.Series(True, index=matrix_df.index)
    if search_term.strip():
        term = search_term.strip().lower()
        c_mask = matrix_df["Campaign Name"].astype(str).str.lower().str.contains(term, na=False)
        if "Community Name" in matrix_df.columns:
            c_mask = c_mask | matrix_df["Community Name"].astype(str).str.lower().str.contains(term, na=False)
        mask = mask & c_mask
        
    if filter_heading != "All":
        mask = mask & (matrix_df["Heading"].astype(str).str.strip() == filter_heading)
        
    if filter_zakat != "All":
        mask = mask & (matrix_df["Zakat Eligibility"].astype(str).str.strip() == filter_zakat)
        
    filtered_indices = matrix_df[mask].index
    filtered_count = len(filtered_indices)
    
    # ── Bulk Edit Tool ──────────────────────────────────────────────
    with st.expander("⚡ Bulk Edit Filtered Rows", expanded=False):
        st.markdown(f"Apply new values to all **{filtered_count:,} matching rows** currently filtered below:")
        b_col1, b_col2, b_col3, b_col4 = st.columns(4)
        with b_col1:
            bulk_heading = st.text_input("New Heading", placeholder="e.g. Infrastructure", key=f"bulk_h_{matrix_platform}")
        with b_col2:
            bulk_subheading = st.text_input("New Sub-Heading", placeholder="e.g. Clean Water", key=f"bulk_sh_{matrix_platform}")
        with b_col3:
            bulk_country = st.text_input("New Country", placeholder="e.g. Gaza", key=f"bulk_c_{matrix_platform}")
        with b_col4:
            bulk_zakat = st.selectbox("New Zakat Eligibility", ["Leave Unchanged", "Zakat", "Non-Zakat", "Unassigned"], key=f"bulk_z_{matrix_platform}")
            
        if st.button("⚡ Apply Bulk Values to Filtered Rows", use_container_width=True, key=f"bulk_apply_btn_{matrix_platform}"):
            matrix_df_copy = matrix_df.copy()
            for idx in filtered_indices:
                if bulk_heading.strip():
                    matrix_df_copy.at[idx, "Heading"] = bulk_heading.strip()
                if bulk_subheading.strip():
                    matrix_df_copy.at[idx, "Sub-Heading"] = bulk_subheading.strip()
                if bulk_country.strip():
                    matrix_df_copy.at[idx, "Country"] = bulk_country.strip()
                if bulk_zakat != "Leave Unchanged":
                    matrix_df_copy.at[idx, "Zakat Eligibility"] = bulk_zakat
            st.session_state[state_key] = matrix_df_copy
            st.success(f"✅ Applied changes to {filtered_count} rows in-memory! Click 'Save & Apply Rules Now' below to save to database.")
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader(f"📝 Edit {matrix_platform} Rules Inline")
    st.caption("Double-click any cell below to edit Heading, Sub-Heading, Country, Code, or Zakat Eligibility.")
    
    edited_filtered_df = st.data_editor(
        matrix_df[mask],
        use_container_width=True,
        num_rows="dynamic",
        key=f"data_editor_{matrix_platform}_filtered"
    )
    
    # Recombine unfiltered rows with edited filtered rows
    other_rows = matrix_df[~mask]
    full_updated_df = pd.concat([other_rows, edited_filtered_df], ignore_index=True)
    
    if st.button(f"💾 Save & Apply {matrix_platform} Rules Now", type="primary", use_container_width=True):
        with st.spinner("Saving classification matrix & updating database..."):
            if matrix_platform == "⚡ LaunchGood Matrix":
                n_saved = save_classification_matrix(full_updated_df)
            else:
                n_saved = save_givebright_classification_matrix(full_updated_df)
            st.session_state.pop(state_key, None)
            st.session_state.pop("df_raw", None)
            st.success(f"✅ Saved {n_saved:,} campaign rules! Dashboard metrics re-calculated.")
            st.rerun()

def render_admin_tab():
    st.header("⚙️ Admin & Database Management")
    st.markdown("Manage your dataset, clear current data, or upload new LaunchGood or GiveBright campaign export files (`.xlsx`, `.csv`).")
    
    # System Status Widget
    st.subheader("📊 System & Storage Engine Status")
    s_col1, s_col2, s_col3 = st.columns(3)
    
    with s_col1:
        st.markdown(f"""
        <div class="glass-panel" style="padding: 16px;">
            <div style="color: #94A3B8; font-weight: 700; font-size: 0.8rem; text-transform: uppercase;">Total Loaded Records</div>
            <div style="color: #38BDF8; font-size: 1.8rem; font-weight: 800;">{len(df_raw):,}</div>
            <div style="color: #64748B; font-size: 0.8rem;">Ready for instant queries</div>
        </div>
        """, unsafe_allow_html=True)
        
    with s_col2:
        import os
        from utils import PARQUET_PATH, LOCAL_DB_PATH
        pq_exists = os.path.exists(PARQUET_PATH)
        pq_size = f"{os.path.getsize(PARQUET_PATH) / (1024*1024):.1f} MB" if pq_exists else "N/A"
        st.markdown(f"""
        <div class="glass-panel" style="padding: 16px;">
            <div style="color: #94A3B8; font-weight: 700; font-size: 0.8rem; text-transform: uppercase;">Parquet Cache Engine</div>
            <div style="color: {'#34D399' if pq_exists else '#F43F5E'}; font-size: 1.8rem; font-weight: 800;">{'⚡ Active' if pq_exists else 'Disabled'}</div>
            <div style="color: #64748B; font-size: 0.8rem;">File size: {pq_size}</div>
        </div>
        """, unsafe_allow_html=True)

    with s_col3:
        db_exists = os.path.exists(LOCAL_DB_PATH)
        db_size = f"{os.path.getsize(LOCAL_DB_PATH) / (1024*1024):.1f} MB" if db_exists else "N/A"
        st.markdown(f"""
        <div class="glass-panel" style="padding: 16px;">
            <div style="color: #94A3B8; font-weight: 700; font-size: 0.8rem; text-transform: uppercase;">SQLite Local Storage</div>
            <div style="color: {'#34D399' if db_exists else '#F43F5E'}; font-size: 1.8rem; font-weight: 800;">{'🗄️ Ready' if db_exists else 'Empty'}</div>
            <div style="color: #64748B; font-size: 0.8rem;">File size: {db_size}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    # Data Upload Section
    col_u1, col_u2 = st.columns([6, 4])
    with col_u1:
        st.subheader("📁 Upload New Dataset(s)")
        uploaded_files = st.file_uploader("Choose Campaign Export File(s) (.xlsx, .csv)", type=["xlsx", "csv"], accept_multiple_files=True, key="admin_file_uploader")
        platform_choice = st.radio("Platform Adapter", options=["📁 Auto-Detect", "⚡ LaunchGood", "🎁 GiveBright"], horizontal=True, key="admin_platform_choice")
    with col_u2:
        st.subheader("⚙️ Dataset Settings")
        source_label_input = st.text_input(
            "🏷️ Custom Data Source Tag (Optional)",
            placeholder="e.g. GiveBright Batch 1, Ramadan 2025",
            help="Leave blank to use each file's name automatically as its Data Source tag."
        )
        upload_mode_choice = st.radio(
            "Upload Action",
            options=["Replace existing database", "Append / Merge into existing database"],
            index=1 if not df_raw.empty else 0,
            help="Choose 'Append' to merge new data alongside existing records (default), or 'Replace' to wipe and start fresh."
        )
        
    if uploaded_files:
        if st.button("🚀 Process & Save to Database", type="primary", use_container_width=True):
            user_mode = "replace" if "Replace" in upload_mode_choice else "append"
            src_arg = source_label_input.strip() if source_label_input.strip() else None
            plt_arg = "auto"
            if "GiveBright" in platform_choice:
                plt_arg = "givebright"
            elif "LaunchGood" in platform_choice:
                plt_arg = "launchgood"
                
            with st.spinner(f"Processing {len(uploaded_files)} file(s), calculating LTV & Payment Frequency, and saving..."):
                try:
                    total_rows = 0
                    for idx, uf in enumerate(uploaded_files):
                        curr_mode = user_mode if idx == 0 else "append"
                        tag_name = src_arg if (src_arg and len(uploaded_files) == 1) else (f"{src_arg} - {uf.name}" if src_arg else None)
                        
                        rows = process_and_upload_excel(
                            uf, 
                            source_name=tag_name,
                            upload_mode=curr_mode,
                            platform=plt_arg
                        )
                        total_rows += rows
                    
                    st.session_state.pop("df_raw", None)
                    st.success(f"✅ Successfully processed and merged {total_rows:,} total rows across {len(uploaded_files)} file(s)!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error during upload: {e}")

    # Source Tag Management (Human Error Correction & Single Dataset Deletion)
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    st.subheader("🏷️ Data Source Tag Manager (Rename & Delete Individual Datasets)")
    st.markdown("Manage uploaded dataset batches below. Select a dataset tag to **rename it** or **delete only that specific dataset** without affecting other data:")
    
    if not df_raw.empty and "Source" in df_raw.columns:
        source_counts = df_raw["Source"].value_counts().reset_index()
        source_counts.columns = ["Source Tag", "Record Count"]
        
        src_col1, src_col2 = st.columns([6, 4])
        with src_col1:
            st.dataframe(source_counts, use_container_width=True, hide_index=True)
        with src_col2:
            old_tag_choice = st.selectbox("Select Dataset Tag", options=source_counts["Source Tag"].tolist(), key="select_tag_admin")
            new_tag_input = st.text_input("New Corrected Tag Name", placeholder="e.g. Ramadan 2025", key="rename_tag_admin")
            
            btn_act1, btn_act2 = st.columns(2)
            with btn_act1:
                if st.button("✏️ Rename Tag", type="secondary", use_container_width=True):
                    if old_tag_choice and new_tag_input.strip():
                        n_updated = update_source_tag(old_tag_choice, new_tag_input.strip())
                        st.session_state.pop("df_raw", None)
                        st.success(f"✅ Updated {n_updated:,} records from '{old_tag_choice}' ➔ '{new_tag_input.strip()}'!")
                        st.rerun()
                    else:
                        st.warning("Please type a new tag name.")
            with btn_act2:
                if st.button("🗑️ Delete Dataset", type="primary", use_container_width=True):
                    if old_tag_choice:
                        n_deleted = delete_single_dataset(old_tag_choice)
                        st.session_state.pop("df_raw", None)
                        st.success(f"✅ Successfully deleted dataset '{old_tag_choice}' ({n_deleted:,} records removed)!")
                        st.rerun()

    # Database Purge / Reset Section
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    with st.expander("⚠️ Danger Zone: Clear / Purge All Data"):
        st.warning("Clearing data will purge all tables from local SQLite, Parquet cache, and Supabase Cloud. You will need to upload an Excel file to view the dashboard again.")
        confirm_purge = st.checkbox("I understand and confirm I want to clear all loaded data", key="confirm_purge_check")
        if confirm_purge:
            if st.button("🗑️ Purge All Loaded Data Now", type="secondary"):
                with st.spinner("Purging all database tables and caches..."):
                    purge_all_data()
                    st.session_state.pop("df_raw", None)
                    st.success("Successfully purged all database tables and caches! Reloading...")
                    st.rerun()

if selected_tab == "🏷️ Campaign Classifications":
    render_classification_tab()

elif selected_tab == "⚙️ Admin & Data Management":
    render_admin_tab()

# --- TAB 1: EXECUTIVE OVERVIEW ---
elif selected_tab == "📈 Overview":
    col_left, col_right = st.columns([6, 4])
    
    with col_left:
        st.subheader("📅 Donation Volume Timeline")
        if col_date and col_date in df.columns and not df[col_date].dropna().empty:
            df_time = df.set_index(col_date).resample('D')[col_amount].agg(['sum', 'count']).reset_index()
            df_time.columns = ['Date', 'Total Raised ($)', 'Transactions']
            
            fig_time = px.line(
                df_time, x='Date', y='Total Raised ($)',
                labels={'Total Raised ($)': 'Amount Raised ($)'},
                color_discrete_sequence=['#10B981']
            )
            fig_time.update_traces(line=dict(width=2.5))
            fig_time.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                hovermode='x unified',
                margin=dict(l=20, r=20, t=30, b=20),
                height=380
            )
            st.plotly_chart(fig_time, use_container_width=True)
        else:
            st.subheader("📊 Top 10 Headings by Volume")
            if col_heading in df.columns and not df[col_heading].dropna().empty:
                cat_agg = df.groupby(col_heading)[col_amount].sum().reset_index().sort_values(by=col_amount, ascending=False).head(10)
                fig_cat = px.bar(
                    cat_agg, x=col_amount, y=col_heading, orientation='h',
                    color=col_heading, color_discrete_sequence=PLOTLY_COLORS,
                    labels={col_amount: f'Total Raised ({currency_symbol})', col_heading: 'Heading'}
                )
                fig_cat.update_layout(
                    showlegend=False,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=20, r=20, t=30, b=20),
                    height=380,
                    yaxis=dict(autorange="reversed")
                )
                st.plotly_chart(fig_cat, use_container_width=True)

    with col_right:
        st.subheader("🔄 Recurring vs. One-Time Payments")
        freq_agg = df.groupby('Payment Frequency')[col_amount].agg(['count', 'sum']).reset_index()
        fig_freq = px.pie(
            freq_agg, values='sum', names='Payment Frequency',
            hole=0.45, color='Payment Frequency',
            color_discrete_map={
                'Recurring Payment': '#10B981',
                'One-Time Payment': '#3B82F6'
            }
        )
        fig_freq.update_traces(textposition='inside', textinfo='percent+label')
        fig_freq.update_layout(
            showlegend=False,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=10, r=10, t=20, b=20),
            height=380
        )
        st.plotly_chart(fig_freq, use_container_width=True)

    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🌙 Campaign Period Breakdown")
        if "Source" in df.columns:
            src_agg = df.groupby("Source").agg(
                Total_Raised=(col_amount, 'sum'),
                Transaction_Count=(col_amount, 'count')
            ).reset_index()
            
            fig_src = px.bar(
                src_agg, x="Source", y='Total_Raised',
                text_auto='.2s', color="Source",
                color_discrete_sequence=['#10B981', '#3B82F6', '#8B5CF6'],
                labels={'Total_Raised': f'Total Raised ({currency_symbol})', "Source": 'Campaign Period'}
            )
            fig_src.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
                height=300
            )
            st.plotly_chart(fig_src, use_container_width=True)
            
    with c2:
        st.subheader("🍩 Donation Volume by Sub-Heading")
        if col_subheading in df.columns and not df[col_subheading].dropna().empty:
            cat_pie = df.groupby(col_subheading)[col_amount].sum().reset_index().sort_values(by=col_amount, ascending=False)
            if len(cat_pie) > 6:
                top_6 = cat_pie.head(6)
                others_val = cat_pie.iloc[6:][col_amount].sum()
                cat_pie = pd.concat([top_6, pd.DataFrame([{col_subheading: 'Others', col_amount: others_val}])], ignore_index=True)
            
            fig_cat_pie = px.pie(
                cat_pie, values=col_amount, names=col_subheading,
                hole=0.4, color_discrete_sequence=PLOTLY_COLORS
            )
            fig_cat_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_cat_pie.update_layout(
                showlegend=False,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=300
            )
            st.plotly_chart(fig_cat_pie, use_container_width=True)

# --- TAB 2: DONOR CLASSIFICATION & FREQUENCY ---
elif selected_tab == "👑 Lifetime LTV & Frequency":
    st.header("👑 Lifetime Donor Value (LTV) & Frequency Analysis")
    
    # 5 Tier Summary Cards
    st.markdown("##### 🏆 Revenue & Transaction Breakdown by Lifetime Tier")
    t1, t2, t3, t4, t5 = st.columns(5)
    tier_classes = [
        ("Low End", f"< {currency_symbol}200", "Low End", "#3B82F6", "tier-low", t1),
        ("Medium Low", f"{currency_symbol}200-{currency_symbol}600", "Medium Low", "#10B981", "tier-medlow", t2),
        ("Medium", f"{currency_symbol}600-{currency_symbol}1K", "Medium", "#F59E0B", "tier-med", t3),
        ("High", f"{currency_symbol}1K-{currency_symbol}3K", "High", "#F97316", "tier-high", t4),
        ("Super High", f"> {currency_symbol}3,000", "Super High", "#EC4899", "tier-super", t5)
    ]
    
    tier_agg_map = df.groupby('Lifetime Donor Classification', observed=False)[col_amount].agg(['count', 'sum']).to_dict('index') if not df.empty else {}
    tot_sum = df[col_amount].sum() if not df.empty else 1
    
    for title, rule, tier_key, color, css_class, col_obj in tier_classes:
        t_data = tier_agg_map.get(tier_key, {'count': 0, 'sum': 0})
        cnt = t_data.get('count', 0)
        vol = t_data.get('sum', 0)
        share = (vol / tot_sum * 100) if tot_sum > 0 else 0
        with col_obj:
            st.markdown(f"""
            <div class="tier-card {css_class}">
                <div style="color: {color}; font-weight: 800; font-size: 0.95rem;">{title}</div>
                <div style="color: #64748B; font-size: 0.75rem; font-weight: 600;">{rule}</div>
                <div style="font-size: 1.35rem; font-weight: 800; color: #F8FAFC; margin: 4px 0;">{format_currency(vol)}</div>
                <div style="color: #94A3B8; font-size: 0.78rem;">{cnt:,} txns ({share:.1f}%)</div>
            </div>
            """, unsafe_allow_html=True)
            
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    
    col_d1, col_d2 = st.columns(2)
    
    with col_d1:
        st.subheader("🏷️ Transaction Count by Lifetime Tier")
        tier_counts = df['Lifetime Donor Classification'].value_counts().reindex(DONOR_TIER_ORDER).fillna(0).reset_index()
        tier_counts.columns = ['Classification', 'Count']
        
        fig_tier1 = px.bar(
            tier_counts, x='Classification', y='Count',
            color='Classification', color_discrete_sequence=PLOTLY_COLORS,
            labels={'Count': 'Number of Transactions', 'Classification': 'Lifetime Donor Tier'}
        )
        fig_tier1.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            showlegend=False,
            height=380
        )
        st.plotly_chart(fig_tier1, use_container_width=True)

    with col_d2:
        st.subheader("💰 Total Funds Raised by Lifetime Tier")
        tier_volume = df.groupby('Lifetime Donor Classification', observed=False)[col_amount].sum().reindex(DONOR_TIER_ORDER).fillna(0).reset_index()
        tier_volume.columns = ['Classification', f'Total Raised ({currency_symbol})']
        
        fig_tier2 = px.bar(
            tier_volume, x='Classification', y=f'Total Raised ({currency_symbol})',
            color='Classification', color_discrete_sequence=PLOTLY_COLORS,
            labels={f'Total Raised ({currency_symbol})': f'Total Raised ({currency_symbol})', 'Classification': 'Lifetime Donor Tier'}
        )
        fig_tier2.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            showlegend=False,
            height=380
        )
        st.plotly_chart(fig_tier2, use_container_width=True)

    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    
    st.subheader("🔄 Lifetime Tier vs. Payment Frequency Matrix")
    cross_df = df.groupby(['Lifetime Donor Classification', 'Payment Frequency'], observed=False)[col_amount].agg(['count', 'sum']).reset_index()
    cross_df.columns = ['Lifetime Donor Classification', 'Payment Frequency', 'Count', f'Total Raised ({currency_symbol})']
    
    col_c1, col_c2 = st.columns([6, 4])
    with col_c1:
        if not cross_df.empty:
            fig_cross = px.bar(
                cross_df, x='Lifetime Donor Classification', y=f'Total Raised ({currency_symbol})',
                color='Payment Frequency', barmode='group',
                color_discrete_sequence=PLOTLY_COLORS,
                text_auto='.2s'
            )
            fig_cross.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=400
            )
            st.plotly_chart(fig_cross, use_container_width=True)
        
    with col_c2:
        st.markdown("#### Summary Table by Lifetime Tier")
        summary_tbl = df.groupby('Lifetime Donor Classification', observed=False).agg(
            Transactions=(col_amount, 'count'),
            Total_Raised=(col_amount, 'sum'),
            Average_Donation=(col_amount, 'mean')
        ).reindex(DONOR_TIER_ORDER).reset_index()
        
        summary_tbl['Total_Raised'] = summary_tbl['Total_Raised'].fillna(0).apply(format_currency)
        summary_tbl['Avg_Donation'] = summary_tbl['Average_Donation'].fillna(0).apply(lambda x: f"{currency_symbol}{x:,.2f}")
        summary_tbl['Transactions'] = summary_tbl['Transactions'].fillna(0).apply(lambda x: f"{int(x):,}")
        
        st.dataframe(summary_tbl, use_container_width=True, hide_index=True)

# --- TAB 3: CAMPAIGNS & CATEGORIES ---
elif selected_tab == "🔥 Campaigns & Headings":
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            st.subheader("🏆 Top 15 Campaigns by Funds Raised")
            top_camp = df.groupby(col_campaign)[col_amount].sum().reset_index().sort_values(by=col_amount, ascending=False).head(15)
            
            fig_top_camp = px.bar(
                top_camp, x=col_amount, y=col_campaign, orientation='h',
                color=col_amount, color_continuous_scale='Viridis',
                labels={col_amount: f'Total Raised ({currency_symbol})', col_campaign: 'Campaign'}
            )
            fig_top_camp.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                coloraxis_showscale=False,
                yaxis=dict(autorange="reversed"),
                height=500,
                margin=dict(l=10, r=10, t=30, b=10)
            )
            st.plotly_chart(fig_top_camp, use_container_width=True)

        with col_c2:
            st.subheader("🤝 Top 15 Communities by Volume")
            top_comm = df.groupby(col_community)[col_amount].sum().reset_index().sort_values(by=col_amount, ascending=False).head(15)
            
            fig_top_comm = px.bar(
                top_comm, x=col_amount, y=col_community, orientation='h',
                color=col_amount, color_continuous_scale='Tealgrn',
                labels={col_amount: f'Total Raised ({currency_symbol})', col_community: 'Community'}
            )
            fig_top_comm.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                coloraxis_showscale=False,
                yaxis=dict(autorange="reversed"),
                height=500,
                margin=dict(l=10, r=10, t=30, b=10)
            )
            st.plotly_chart(fig_top_comm, use_container_width=True)

# --- TAB 4: GEOGRAPHY & PAYMENT INSIGHTS ---
elif selected_tab == "🌍 Geography & Payment Insights":
    if "Billing Country" in df.columns or "Payment Type" in df.columns:
        d1, d2 = st.columns(2)
        with d1:
            st.subheader("🌍 Top Donor Countries")
            if "Billing Country" in df.columns:
                ctry_df = df['Billing Country'].value_counts().reset_index().head(12)
                ctry_df.columns = ['Country', 'Donations']
                fig_ctry = px.bar(
                    ctry_df, x='Donations', y='Country', orientation='h',
                    color='Donations', color_continuous_scale='Blues',
                    labels={'Donations': 'Number of Donors', 'Country': 'Billing Country'}
                )
                fig_ctry.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    coloraxis_showscale=False,
                    yaxis=dict(autorange="reversed"),
                    height=400
                )
                st.plotly_chart(fig_ctry, use_container_width=True)
        with d2:
            st.subheader("💳 Payment Methods")
            if "Payment Type" in df.columns:
                pm_df = df['Payment Type'].value_counts().reset_index()
                pm_df.columns = ['Payment Method', 'Count']
                fig_pm = px.pie(
                    pm_df, values='Count', names='Payment Method',
                    hole=0.4, color_discrete_sequence=PLOTLY_COLORS
                )
                fig_pm.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=400)
                st.plotly_chart(fig_pm, use_container_width=True)

elif selected_tab == "📋 Data Explorer & Export":
    st.subheader("📋 Donor Records Table")
    st.markdown("Full donor-level data with classification, payment frequency, category, email, and more.")

    # ── Column groups the user can toggle ──────────────────────────────────
    DONOR_IDENTITY_COLS = [c for c in [
        "First Name", "Last Name", "Display Name", "Email",
        "Anonymous or Public", "Billing Country"
    ] if c in df.columns]

    DONATION_COLS = [c for c in [
        col_amount,
        "Total LTV",
        "Lifetime Donor Classification",
        "Transaction Donor Classification",
        "Payment Frequency",
        "Donation Currency (DC)",
        "Zakat (yes or no)",
        "Gift Aid (yes or no)",
    ] if c in df.columns]

    CAMPAIGN_COLS = [c for c in [
        col_campaign,
        col_community,
        col_heading,
        col_subheading,
        "Country",
        "Code",
        "Zakat Eligibility",
        "Source",
        "Project Impact Location",
        "Payment Type",
    ] if c in df.columns]

    DATE_COLS = [c for c in [
        "Created Date (UTC)",
        "Donation ID",
        "Status",
    ] if c in df.columns]

    ALL_DEFAULT = DONOR_IDENTITY_COLS + DONATION_COLS + CAMPAIGN_COLS + DATE_COLS

    # ── Controls row ────────────────────────────────────────────────────────
    ctrl1, ctrl2, ctrl3 = st.columns([4, 3, 3])

    with ctrl1:
        quick_search = st.text_input(
            "🔍 Quick Search (name / email / campaign)",
            placeholder="Type to filter rows…"
        )

    with ctrl2:
        col_group = st.selectbox(
            "Column Preset",
            ["Donor + Donation + Campaign (Default)", "Donor Identity Only", "Donation Details Only", "Campaign Details Only", "All Columns"]
        )

    with ctrl3:
        max_rows = st.selectbox("Rows to Display", [50, 100, 250, 500, 1000, "All"], index=1)

    # Column preset logic
    if col_group == "Donor Identity Only":
        visible_cols = DONOR_IDENTITY_COLS + [c for c in ["Lifetime Donor Classification", "Total LTV", "Payment Frequency"] if c in df.columns]
    elif col_group == "Donation Details Only":
        visible_cols = DONATION_COLS + DATE_COLS
    elif col_group == "Campaign Details Only":
        visible_cols = CAMPAIGN_COLS + DATE_COLS
    elif col_group == "All Columns":
        visible_cols = list(df.columns)
    else:
        visible_cols = [c for c in ALL_DEFAULT if c in df.columns]

    # Apply quick search
    full_df_for_search = df.copy()

    if quick_search.strip():
        term = quick_search.strip().lower()
        search_cols = [c for c in ["First Name", "Last Name", "Display Name", "Email", col_campaign, col_community] if c in full_df_for_search.columns]
        mask = pd.Series(False, index=full_df_for_search.index)
        for sc in search_cols:
            mask = mask | full_df_for_search[sc].astype(str).str.lower().str.contains(term, na=False)
        display_df = full_df_for_search.loc[mask].copy()
    else:
        display_df = full_df_for_search.copy()

    total_matching = len(display_df)

    # Apply row limit
    if max_rows != "All":
        display_df_show = display_df.head(int(max_rows))
    else:
        display_df_show = display_df

    # ── Summary stats bar ───────────────────────────────────────────────────
    s1, s2, s3, s4, s5 = st.columns(5)
    with s1:
        st.metric("Matching Records", f"{total_matching:,}")
    with s2:
        if col_amount in df.columns:
            shown_total = display_df_show[col_amount].sum() if col_amount in display_df_show.columns else 0
            st.metric("Total Raised (shown)", format_currency(shown_total))
    with s3:
        if "Payment Frequency" in display_df_show.columns:
            rec_count = (display_df_show["Payment Frequency"] == "Recurring Payment").sum()
            st.metric("Recurring Donors", f"{rec_count:,}")
    with s4:
        if "Zakat (yes or no)" in display_df_show.columns:
            zakat_count = (display_df_show["Zakat (yes or no)"].str.lower() == "yes").sum()
            st.metric("Zakat Donations", f"{zakat_count:,}")
    with s5:
        if "Billing Country" in display_df_show.columns:
            unique_countries = display_df_show["Billing Country"].nunique()
            st.metric("Unique Countries", f"{unique_countries:,}")

    st.markdown("")

    # ── Column multiselect (advanced) ───────────────────────────────────────
    with st.expander("⚙️ Advanced: Manually Select Columns"):
        selected_cols_manual = st.multiselect(
            "Pick columns to show",
            options=list(df.columns),
            default=visible_cols,
            key="advanced_col_select"
        )
        final_cols = selected_cols_manual if selected_cols_manual else visible_cols
        
    # Force Donation ID to be present in final_cols for database index alignment
    if "Donation ID" not in final_cols and "Donation ID" in display_df_show.columns:
        final_cols = ["Donation ID"] + final_cols
        
    display_df_show = display_df_show[final_cols]

    # ── Bulk Edit matching records ──────────────────────────────────────────
    with st.expander("⚡ Bulk Edit Filtered Donor Records", expanded=False):
        st.markdown(f"Select column(s) to update for all **{total_matching:,} matching donor records** currently filtered:")
        
        editable_cols = sorted([str(c) for c in df_raw.columns if str(c).strip() != ""])
        
        be1, be2 = st.columns(2)
        with be1:
            st.markdown("**Field #1**")
            target_col_1 = st.selectbox("Select Target Column #1", ["-- Select Column --"] + editable_cols, key="bulk_target_col_1")
            val_1 = st.text_input("New Value for Column #1", placeholder="Type new value...", key="bulk_val_1")
            
        with be2:
            st.markdown("**Field #2 (Optional)**")
            target_col_2 = st.selectbox("Select Target Column #2", ["-- Select Column --"] + editable_cols, key="bulk_target_col_2")
            val_2 = st.text_input("New Value for Column #2", placeholder="Type new value...", key="bulk_val_2")
            
        if st.button("⚡ Apply Bulk Changes to Filtered Records", use_container_width=True, key="bulk_apply_donors_btn"):
            if target_col_1 == "-- Select Column --" and target_col_2 == "-- Select Column --":
                st.warning("Please select at least one column to update.")
            else:
                with st.spinner("Applying and saving changes..."):
                    from utils import PARQUET_PATH, LOCAL_DB_PATH
                    import sqlite3 as _sqlite3
                    df_raw_copy = df_raw.copy()
                    for idx in display_df.index:
                        if target_col_1 != "-- Select Column --" and val_1.strip():
                            df_raw_copy.at[idx, target_col_1] = val_1.strip()
                        if target_col_2 != "-- Select Column --" and val_2.strip():
                            df_raw_copy.at[idx, target_col_2] = val_2.strip()

                    # Persist immediately to Parquet + SQLite
                    df_raw_copy.to_parquet(PARQUET_PATH, index=False)
                    _conn = _sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                    df_raw_copy.to_sql("donations", con=_conn, if_exists="replace", index=False)
                    _conn.close()

                    # Sync to Supabase cloud in background
                    if DATABASE_URL and "postgres" in DATABASE_URL:
                        def _bulk_cloud_sync(data_df):
                            import io, psycopg2
                            try:
                                buf = io.StringIO()
                                data_df.to_csv(buf, index=False, header=False, sep='\t', na_rep='')
                                buf.seek(0)
                                conn = psycopg2.connect(DATABASE_URL)
                                cur = conn.cursor()
                                cur.execute('DROP TABLE IF EXISTS "donations";')
                                cols_def = ', '.join([f'"{c}" TEXT' for c in data_df.columns])
                                cur.execute(f'CREATE TABLE "donations" ({cols_def});')
                                conn.commit()
                                target_cols_sql = ', '.join([f'"{c}"' for c in data_df.columns])
                                copy_sql = f'COPY "donations" ({target_cols_sql}) FROM STDIN WITH (FORMAT csv, DELIMITER \'\\t\', NULL \'\');'
                                cur.copy_expert(sql=copy_sql, file=buf)
                                conn.commit()
                                cur.close()
                                conn.close()
                            except Exception as e:
                                print(f"Cloud bulk sync notice: {e}")
                        threading.Thread(target=_bulk_cloud_sync, args=(df_raw_copy,), daemon=True).start()

                    st.session_state["df_raw"] = df_raw_copy
                    sync_donor_classifications_to_matrix(df_raw_copy)
                    st.session_state.pop("matrix_df_⚡ LaunchGood Matrix", None)
                    st.session_state.pop("matrix_df_🎁 GiveBright Matrix", None)
                    st.session_state.pop("prev_matrix_platform", None)
                    st.cache_data.clear()
                    st.cache_resource.clear()
                st.success(f"✅ Saved {total_matching:,} updated records to database + cloud!")
                st.rerun()



    # ── The Main Data Table ─────────────────────────────────────────────────
    st.markdown(f"**Showing {len(display_df_show):,} of {total_matching:,} matching records**")
    st.caption("Double-click any cell below to edit donor information. The Donation ID index column is read-only for alignment safety.")

    # Set index to Donation ID for the editor
    display_df_show_editor = display_df_show.set_index("Donation ID") if "Donation ID" in display_df_show.columns else display_df_show

    edited_filtered_df = st.data_editor(
        display_df_show_editor,
        use_container_width=True,
        height=520,
        num_rows="dynamic",
        key="data_editor_donors_filtered"
    )

    # Align edits back
    if "Donation ID" in display_df_show.columns:
        original_ids = set(display_df_show_editor.index)
        current_ids = set(edited_filtered_df.index)
        deleted_ids = original_ids - current_ids
        
        # Build raw updated df from edits
        df_raw_indexed = df_raw.set_index("Donation ID")
        df_raw_indexed.update(edited_filtered_df)
        
        if deleted_ids:
            df_raw_indexed = df_raw_indexed.drop(index=list(deleted_ids))
            
        df_raw_updated = df_raw_indexed.reset_index()
    else:
        df_raw_updated = df_raw
        
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 Save Donor Changes Now", type="primary", use_container_width=True, key="save_donors_btn"):
        with st.spinner("Saving changes and updating database metrics..."):
            from utils import PARQUET_PATH, LOCAL_DB_PATH
            import sqlite3
            df_raw_updated.to_parquet(PARQUET_PATH, index=False)
            
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            df_raw_updated.to_sql("donations", con=conn, if_exists="replace", index=False)
            conn.close()
            
            # Sync donor classification changes into campaign matrices
            sync_donor_classifications_to_matrix(df_raw_updated)
            st.session_state.pop("matrix_df_⚡ LaunchGood Matrix", None)
            st.session_state.pop("matrix_df_🎁 GiveBright Matrix", None)
            st.session_state.pop("prev_matrix_platform", None)
            
            # Sync to cloud
            if DATABASE_URL and "postgres" in DATABASE_URL:
                def sync_to_cloud_fast(data_df):
                    import io, psycopg2
                    try:
                        buf = io.StringIO()
                        data_df.to_csv(buf, index=False, header=False, sep='\t', na_rep='')
                        buf.seek(0)
                        conn = psycopg2.connect(DATABASE_URL)
                        cur = conn.cursor()
                        cur.execute('DROP TABLE IF EXISTS "donations";')
                        cols_def = ', '.join([f'"{c}" TEXT' for c in data_df.columns])
                        cur.execute(f'CREATE TABLE "donations" ({cols_def});')
                        conn.commit()
                        target_cols = ', '.join([f'"{c}"' for c in data_df.columns])
                        copy_sql = f'COPY "donations" ({target_cols}) FROM STDIN WITH (FORMAT csv, DELIMITER \'\t\', NULL \'\');'
                        cur.copy_expert(sql=copy_sql, file=buf)
                        conn.commit()
                        cur.close()
                        conn.close()
                    except Exception as e:
                        print(f"Cloud DB sync notice: {e}")
                threading.Thread(target=sync_to_cloud_fast, args=(df_raw_updated,), daemon=True).start()
                
            st.session_state["df_raw"] = df_raw_updated
            st.cache_data.clear()
            st.cache_resource.clear()
            st.success("✅ Successfully saved donor changes and re-calculated metrics!")
            st.rerun()

    # ── Export Buttons ───────────────────────────────────────────────────────
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    ex1, ex2 = st.columns(2)
    with ex1:
        csv_show = display_df_show.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download Shown Rows (CSV)", csv_show, "launchgood_shown_data.csv", "text/csv", use_container_width=True)
    with ex2:
        csv_all = display_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download All Filtered Records (CSV)", csv_all, "launchgood_all_filtered_data.csv", "text/csv", use_container_width=True)


