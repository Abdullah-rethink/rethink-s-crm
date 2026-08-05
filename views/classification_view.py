import pandas as pd
import streamlit as st

from core.data_processor import get_classification_matrix, save_classification_matrix


def get_givebright_classification_matrix():
    """Returns GiveBright classification matrix DataFrame dynamically from Parquet & SQLite DB."""
    import os
    import sqlite3

    from config.settings import LOCAL_DB_PATH, PARQUET_PATH

    target_cols_display = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
    matrix_df = pd.DataFrame(columns=["Campaign Name", "Community Name"] + target_cols_display)

    try:
        if os.path.exists(PARQUET_PATH):
            df_donations = pd.read_parquet(PARQUET_PATH)
            if not df_donations.empty and "Campaign Name" in df_donations.columns:
                platform_s = df_donations.get("Platform", pd.Series("", index=df_donations.index)).astype(str).str.lower()
                source_s = df_donations.get("Source", pd.Series("", index=df_donations.index)).astype(str).str.lower()

                gb_mask = (platform_s == "givebright") | source_s.str.contains("givebright|give_bright|file-", na=False)
                gb_df = df_donations[gb_mask] if gb_mask.any() else df_donations.iloc[0:0]

                if not gb_df.empty:
                    c_name = gb_df["Campaign Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})
                    comm_name = gb_df["Community Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'}) if "Community Name" in gb_df.columns else pd.Series("N/A", index=gb_df.index)

                    available_target_cols = [c for c in target_cols_display if c in gb_df.columns]
                    donor_df = pd.DataFrame({"Campaign Name": c_name, "Community Name": comm_name})
                    for tc in available_target_cols:
                        donor_df[tc] = gb_df[tc].values

                    for tc in target_cols_display:
                        if tc not in donor_df.columns:
                            donor_df[tc] = "Unassigned"

                    matrix_df = donor_df.groupby(["Campaign Name", "Community Name"], dropna=False)[target_cols_display].first().reset_index()

        # Merge with saved entries from SQLite
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        try:
            db_matrix = pd.read_sql_query("SELECT * FROM givebright_classifications", conn)
            db_matrix.rename(columns={
                "campaign_name": "Campaign Name",
                "community_name": "Community Name",
                "heading": "Heading",
                "sub_heading": "Sub-Heading",
                "country": "Country",
                "code": "Code",
                "zakat_eligibility": "Zakat Eligibility"
            }, inplace=True)

            if not db_matrix.empty:
                db_matrix["Campaign Name"] = db_matrix["Campaign Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})
                db_matrix["Community Name"] = db_matrix["Community Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})

                if matrix_df.empty:
                    matrix_df = db_matrix
                else:
                    existing_keys = set(zip(matrix_df["Campaign Name"].astype(str), matrix_df["Community Name"].astype(str)))
                    new_rows = db_matrix[~db_matrix.apply(
                        lambda r: (str(r.get("Campaign Name", "")), str(r.get("Community Name", ""))) in existing_keys, axis=1
                    )]
                    if not new_rows.empty:
                        matrix_df = pd.concat([matrix_df, new_rows], ignore_index=True)
        except Exception:
            pass
        finally:
            conn.close()

    except Exception as e:
        print(f"GiveBright matrix load notice: {e}")

    for col in ["Campaign Name", "Community Name"] + target_cols_display:
        if col not in matrix_df.columns:
            matrix_df[col] = "Unassigned"

    return matrix_df

def save_givebright_classification_matrix(matrix_df):
    """Saves updated GiveBright classification matrix to SQLite."""
    import sqlite3

    from config.settings import LOCAL_DB_PATH
    if matrix_df.empty:
        return 0
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS givebright_classifications (
            campaign_name TEXT PRIMARY KEY,
            community_name TEXT,
            heading TEXT DEFAULT 'Unassigned',
            sub_heading TEXT DEFAULT 'Unassigned',
            country TEXT DEFAULT 'Unassigned',
            code TEXT DEFAULT 'Unassigned',
            zakat_eligibility TEXT DEFAULT 'Unassigned'
        );
    """)
    for _, row in matrix_df.iterrows():
        conn.execute("""
            INSERT INTO givebright_classifications (campaign_name, community_name, heading, sub_heading, country, code, zakat_eligibility)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_name) DO UPDATE SET
                community_name=excluded.community_name,
                heading=excluded.heading,
                sub_heading=excluded.sub_heading,
                country=excluded.country,
                code=excluded.code,
                zakat_eligibility=excluded.zakat_eligibility;
        """, (
            str(row.get("Campaign Name", "Unassigned")),
            str(row.get("Community Name", "Unassigned")),
            str(row.get("Heading", "Unassigned")),
            str(row.get("Sub-Heading", "Unassigned")),
            str(row.get("Country", "Unassigned")),
            str(row.get("Code", "Unassigned")),
            str(row.get("Zakat Eligibility", "Unassigned"))
        ))
    conn.commit()
    conn.close()
    return len(matrix_df)

def render_classification_tab(user_session):
    """Renders Campaign Classification matrix rules manager with strict RBAC."""
    st.header("🏷️ Campaign Classification Manager (Source of Truth)")
    st.markdown("This matrix is your **source of truth** for mapping (`Campaign Name`, `Community Name`) ➔ `Heading`, `Sub-Heading`, `Country`, `Code`, and `Zakat Eligibility`.")

    matrix_platform = st.radio("Platform Matrix", options=["⚡ LaunchGood Matrix", "🎁 GiveBright Matrix"], horizontal=True, key="matrix_platform_toggle")
    state_key = f"matrix_df_{matrix_platform}"

    if st.session_state.get("prev_matrix_platform") != matrix_platform:
        st.session_state.pop(state_key, None)
        st.session_state["prev_matrix_platform"] = matrix_platform

    if state_key not in st.session_state:
        if matrix_platform == "⚡ LaunchGood Matrix":
            matrix_df = get_classification_matrix()
        else:
            matrix_df = get_givebright_classification_matrix()
    else:
        matrix_df = st.session_state[state_key]

    unassigned_count = (matrix_df["Heading"] == "Unassigned").sum() if "Heading" in matrix_df.columns else 0

    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        st.metric("Total Tracked Campaigns", f"{len(matrix_df):,}")
    with col_c2:
        st.metric("Fully Classified Campaigns", f"{len(matrix_df) - unassigned_count:,}")
    with col_c3:
        st.metric("Unassigned Campaigns", f"{unassigned_count:,}")

    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    # ── Export Row ───────────────────────────────────────────
    csv_matrix = matrix_df.to_csv(index=False).encode('utf-8')
    fname_export = "launchgood_classifications.csv" if matrix_platform == "⚡ LaunchGood Matrix" else "givebright_classifications.csv"
    st.download_button(
        f"⬇️ Export {matrix_platform} Matrix (CSV)",
        csv_matrix,
        fname_export,
        "text/csv",
        use_container_width=True
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader(f"📝 {matrix_platform} Rules")

    if user_session.get("role") != "super_admin":
        st.info("🔒 **Read-Only Mode:** Logged in as Admin (`admin@analytics.com`). You can view and search classification rules. Rule editing, imports, and bulk updates are restricted to Super Admin accounts.")
        st.dataframe(matrix_df, use_container_width=True)
    else:
        # Bulk Edit Form for Super Admin
        with st.expander("⚡ Bulk Edit Filtered Rows", expanded=False):
            with st.form(key=f"bulk_matrix_form_{matrix_platform}", clear_on_submit=False):
                b_col1, b_col2, b_col3, b_col4 = st.columns(4)
                with b_col1:
                    bulk_heading = st.text_input("New Heading", placeholder="e.g. Infrastructure", key=f"bulk_h_{matrix_platform}")
                with b_col2:
                    bulk_subheading = st.text_input("New Sub-Heading", placeholder="e.g. Clean Water", key=f"bulk_sh_{matrix_platform}")
                with b_col3:
                    bulk_country = st.text_input("New Country", placeholder="e.g. Gaza", key=f"bulk_c_{matrix_platform}")
                with b_col4:
                    bulk_zakat = st.selectbox("New Zakat Eligibility", ["Leave Unchanged", "Zakat", "Non-Zakat", "Unassigned"], key=f"bulk_z_{matrix_platform}")
                submit_bulk_matrix = st.form_submit_button("⚡ Apply Bulk Values to Filtered Rows", use_container_width=True)

            if submit_bulk_matrix:
                matrix_df_copy = matrix_df.copy()
                for idx in matrix_df_copy.index:
                    if bulk_heading.strip():
                        matrix_df_copy.at[idx, "Heading"] = bulk_heading.strip()
                    if bulk_subheading.strip():
                        matrix_df_copy.at[idx, "Sub-Heading"] = bulk_subheading.strip()
                    if bulk_country.strip():
                        matrix_df_copy.at[idx, "Country"] = bulk_country.strip()
                    if bulk_zakat != "Leave Unchanged":
                        matrix_df_copy.at[idx, "Zakat Eligibility"] = bulk_zakat
                st.session_state[state_key] = matrix_df_copy
                st.success("✅ Applied changes to rows in-memory! Click 'Save & Apply Rules Now' below to save.")
                st.rerun()

        edited_df = st.data_editor(
            matrix_df,
            use_container_width=True,
            num_rows="dynamic",
            key=f"editor_{matrix_platform}"
        )

        if st.button(f"💾 Save & Apply {matrix_platform} Rules Now", type="primary", use_container_width=True):
            save_target_df = st.session_state.get(state_key, edited_df)
            with st.spinner("Saving rules to database..."):
                if matrix_platform == "⚡ LaunchGood Matrix":
                    n_saved = save_classification_matrix(save_target_df)
                else:
                    n_saved = save_givebright_classification_matrix(save_target_df)
                st.session_state.pop(state_key, None)
                st.session_state.pop("df_raw", None)
                st.success(f"✅ Saved {n_saved:,} campaign rules!")
                st.rerun()
