
import pandas as pd
import streamlit as st

from config.settings import LOCAL_DB_PATH, PARQUET_PATH
from config.styles import style_donor_classifications
from core.data_processor import sync_donor_classifications_to_matrix

DONOR_IDENTITY_COLS = ["Donation ID", "First Name", "Last Name", "Display Name", "Email", "Phone", "Billing Address Line 1", "Billing City", "Billing State", "Billing Post Code", "Billing Country"]
DONATION_COLS = ["Donation ID", "Donation Amount in Project Currency (May be approx.)", "Donation Currency (DC)", "Donation Amount (in Donation Currency)", "Payment Frequency", "Zakat (yes or no)", "Settlement Currency", "Total Online Donations Net Amount in Settled Currency", "Source", "Platform"]
CAMPAIGN_COLS = ["Donation ID", "Campaign Name", "Community Name", "Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
DATE_COLS = ["Created Date (UTC)", "Disbursed / Settled Date (UTC)"]

# Preserve order while deduplicating column names
ALL_DEFAULT = list(dict.fromkeys(DONOR_IDENTITY_COLS + DONATION_COLS + CAMPAIGN_COLS + DATE_COLS))

def render_explorer_tab(df, df_raw, user_session, col_amount, col_campaign, col_community):
    """Renders Data Explorer tab with column presets, bulk editing, Styler colors, and exports."""
    st.header("📋 Data Explorer & Export Center")
    st.markdown("Search, filter, and inspect donor records across your datasets.")

    # ── Controls row ────────────────────────────────────────────────────────
    ctrl1, ctrl2, ctrl3 = st.columns([4, 4, 2])
    with ctrl1:
        quick_search = st.text_input("🔍 Quick Search (Name / Email / Campaign)", placeholder="Type to search...", key="data_explorer_search")

    with ctrl2:
        col_group = st.selectbox(
            "Column Preset",
            ["Donor + Donation + Campaign (Default)", "Donor Identity Only", "Donation Details Only", "Campaign Details Only", "All Columns"],
            key="data_explorer_col_preset"
        )

    with ctrl3:
        page_size = st.selectbox("Page Size (Rows/Page)", [50, 100, 250, 500, 1000], index=1, key="explorer_page_size")

    # Column preset logic
    if col_group == "Donor Identity Only":
        visible_cols = list(dict.fromkeys(DONOR_IDENTITY_COLS + [c for c in ["Lifetime Donor Classification", "Total LTV", "Payment Frequency"] if c in df.columns]))
    elif col_group == "Donation Details Only":
        visible_cols = list(dict.fromkeys(DONATION_COLS + DATE_COLS))
    elif col_group == "Campaign Details Only":
        visible_cols = list(dict.fromkeys(CAMPAIGN_COLS + DATE_COLS))
    elif col_group == "All Columns":
        visible_cols = list(dict.fromkeys(list(df.columns)))
    else:
        visible_cols = list(dict.fromkeys([c for c in ALL_DEFAULT if c in df.columns]))

    # Ensure every default column actually exists in active dataframe
    visible_cols = [c for c in visible_cols if c in df.columns]

    # Sync Column Preset with multiselect state without duplicate default warning
    if "advanced_col_select" not in st.session_state or st.session_state.get("prev_col_preset") != col_group:
        st.session_state["prev_col_preset"] = col_group
        st.session_state["advanced_col_select"] = visible_cols

    # Apply search filter
    display_df = df.copy()
    if quick_search.strip():
        term = quick_search.strip().lower()
        search_cols = [c for c in ["First Name", "Last Name", "Display Name", "Email", col_campaign, col_community] if c in display_df.columns]
        mask = pd.Series(False, index=display_df.index)
        for sc in search_cols:
            mask = mask | display_df[sc].astype(str).str.lower().str.contains(term, na=False)
        display_df = display_df.loc[mask]

    total_matching = len(display_df)

    with st.expander("⚙️ Advanced: Manually Select Columns"):
        selected_cols_manual = st.multiselect(
            "Pick columns to show",
            options=list(df.columns),
            key="advanced_col_select"
        )
        final_cols = list(dict.fromkeys(selected_cols_manual if selected_cols_manual else visible_cols))

    # Pick valid columns & drop duplicate columns if any
    valid_cols = [c for c in final_cols if c in display_df.columns]
    display_df_show = display_df[valid_cols]
    display_df_show = display_df_show.loc[:, ~display_df_show.columns.duplicated()]

    # ── ⚡ Bulk Edit Filtered Donor Records (Super Admin Only) ────────────────
    if user_session.get("role") == "super_admin":
        with st.expander("⚡ Bulk Edit Filtered Donor Records", expanded=False):
            st.markdown(f"Select column(s) to update for all **{total_matching:,} matching donor records** currently filtered:")
            with st.form("bulk_edit_donors_form", clear_on_submit=False):
                editable_cols = sorted([str(c) for c in df_raw.columns if str(c).strip() != ""])
                
                row1_col1, row1_col2 = st.columns(2)
                with row1_col1:
                    st.markdown("**Field #1**")
                    target_col_1 = st.selectbox("Select Target Column #1", ["-- Select Column --"] + editable_cols, key="bulk_target_col_1")
                    val_1 = st.text_input("New Value for Column #1", placeholder="Type new value...", key="bulk_val_1")
                    
                with row1_col2:
                    st.markdown("**Field #2 (Optional)**")
                    target_col_2 = st.selectbox("Select Target Column #2", ["-- Select Column --"] + editable_cols, key="bulk_target_col_2")
                    val_2 = st.text_input("New Value for Column #2", placeholder="Type new value...", key="bulk_val_2")

                row2_col1, row2_col2 = st.columns(2)
                with row2_col1:
                    st.markdown("**Field #3 (Optional)**")
                    target_col_3 = st.selectbox("Select Target Column #3", ["-- Select Column --"] + editable_cols, key="bulk_target_col_3")
                    val_3 = st.text_input("New Value for Column #3", placeholder="Type new value...", key="bulk_val_3")
                    
                with row2_col2:
                    st.markdown("**Field #4 (Optional)**")
                    target_col_4 = st.selectbox("Select Target Column #4", ["-- Select Column --"] + editable_cols, key="bulk_target_col_4")
                    val_4 = st.text_input("New Value for Column #4", placeholder="Type new value...", key="bulk_val_4")
                    
                submit_bulk_donors = st.form_submit_button("⚡ Apply Bulk Changes to Filtered Records", use_container_width=True)

            if submit_bulk_donors:
                if (target_col_1 == "-- Select Column --" and 
                    target_col_2 == "-- Select Column --" and 
                    target_col_3 == "-- Select Column --" and 
                    target_col_4 == "-- Select Column --"):
                    st.warning("Please select at least one column to update.")
                else:
                    with st.spinner("Applying and saving changes..."):
                        import sqlite3 as _sqlite3
                        df_raw_copy = df_raw.copy()
                        for idx in display_df.index:
                            if target_col_1 != "-- Select Column --" and val_1.strip():
                                df_raw_copy.at[idx, target_col_1] = val_1.strip()
                            if target_col_2 != "-- Select Column --" and val_2.strip():
                                df_raw_copy.at[idx, target_col_2] = val_2.strip()
                            if target_col_3 != "-- Select Column --" and val_3.strip():
                                df_raw_copy.at[idx, target_col_3] = val_3.strip()
                            if target_col_4 != "-- Select Column --" and val_4.strip():
                                df_raw_copy.at[idx, target_col_4] = val_4.strip()

                        # Persist immediately to Parquet + SQLite
                        df_raw_copy.to_parquet(PARQUET_PATH, index=False)
                        _conn = _sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                        df_raw_copy.to_sql("donations", con=_conn, if_exists="replace", index=False)
                        _conn.close()

                        st.session_state["df_raw"] = df_raw_copy
                        sync_donor_classifications_to_matrix(df_raw_copy)
                        st.cache_data.clear()
                        st.cache_resource.clear()
                    st.success(f"✅ Saved {total_matching:,} updated records to database!")
                    st.rerun()
    else:
        st.info("🔒 **Read-Only Access:** Logged in as Admin (`admin@analytics.com`). You can view, search, filter, and export donor data. Cell editing and bulk updates are restricted to Super Admin accounts.")

    # ── Interactive Page Navigation (Pagination Engine) ──────────────────────
    import math
    total_pages = max(1, math.ceil(total_matching / page_size))
    
    st.markdown("<br>", unsafe_allow_html=True)
    p_col1, p_col2 = st.columns([3, 7])
    with p_col1:
        current_page = st.number_input(
            f"📄 Go to Page (1 - {total_pages:,})", 
            min_value=1, 
            max_value=total_pages, 
            value=1, 
            step=1, 
            key="explorer_current_page"
        )
    with p_col2:
        start_idx = (current_page - 1) * page_size
        end_idx = min(start_idx + page_size, total_matching)
        st.markdown(f"""
        <div style="margin-top: 24px; color: #94A3B8; font-weight: 600; font-size: 0.95rem;">
            Showing records <b style="color: #38BDF8;">{start_idx + 1:,} - {end_idx:,}</b> of <b style="color: #F8FAFC;">{total_matching:,}</b> total matching donor records 
            <span style="color: #64748B;">(Page {current_page:,} of {total_pages:,})</span>
        </div>
        """, unsafe_allow_html=True)

    display_df_show_page = display_df_show.iloc[start_idx:end_idx].copy()

    # Round off float columns and build column_config for 2 decimal place display
    numeric_float_cols = display_df_show_page.select_dtypes(include=['float', 'float64']).columns
    col_config_2dec = {col: st.column_config.NumberColumn(format="%.2f") for col in numeric_float_cols}

    # ── Main Data Table ─────────────────────────────────────────────────────
    st.subheader(f"📊 Donor Records Table — Page {current_page:,}")

    # Render Styled Table with Full Background Colored Boxes
    st.dataframe(
        style_donor_classifications(display_df_show_page),
        column_config=col_config_2dec,
        use_container_width=True,
        height=520
    )

    # Super Admin Inline Cell Editor Expander
    if user_session.get("role") == "super_admin":
        with st.expander("📝 Edit Donor Records Inline (Super Admin Only)", expanded=False):
            st.caption("Double-click any cell below to edit donor information.")
            st.data_editor(
                display_df_show_page,
                column_config=col_config_2dec,
                use_container_width=True,
                height=450,
                num_rows="dynamic",
                key="data_editor_explorer"
            )
            if st.button("💾 Save Donor Changes Now", type="primary", use_container_width=True, key="save_donors_btn"):
                with st.spinner("Saving changes..."):
                    import sqlite3
                    df_raw.to_parquet(PARQUET_PATH, index=False)
                    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                    df_raw.to_sql("donations", con=conn, if_exists="replace", index=False)
                    conn.close()
                    st.success("✅ Donor changes saved successfully!")
                    st.rerun()

    # Export Button Row
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    csv_data = display_df_show.to_csv(index=False).encode('utf-8')
    st.download_button(
        "⬇️ Download Filtered Results (CSV)",
        data=csv_data,
        file_name="filtered_donor_export.csv",
        mime="text/csv",
        use_container_width=True
    )
