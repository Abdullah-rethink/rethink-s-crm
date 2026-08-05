import os

import streamlit as st

from config.settings import PARQUET_PATH
from core.data_processor import (
    delete_single_dataset,
    purge_all_data,
    update_source_tag,
)
from core.database import get_cloud_sync_status


def render_admin_tab(df_raw, user_session):
    """Renders Admin, Data Management, Tag Manager, and Database Purge tab."""
    st.header("⚙️ Admin & Database Management")
    st.markdown("Manage datasets, upload new campaign export files, or purge data.")

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
        pq_exists = os.path.exists(PARQUET_PATH)
        pq_size = f"{os.path.getsize(PARQUET_PATH) / (1024*1024):.1f} MB" if pq_exists else "N/A"
        st.markdown(f"""
        <div class="glass-panel" style="padding: 16px;">
            <div style="color: #94A3B8; font-weight: 700; font-size: 0.8rem; text-transform: uppercase;">Parquet Cache Size</div>
            <div style="color: #10B981; font-size: 1.8rem; font-weight: 800;">{pq_size}</div>
            <div style="color: #64748B; font-size: 0.8rem;">Binary column cache</div>
        </div>
        """, unsafe_allow_html=True)

    with s_col3:
        sync_info = get_cloud_sync_status()
        st_status = sync_info["status"] if sync_info else "ACTIVE"
        st_color = "#34D399" if st_status == "SUCCESS" or st_status == "ACTIVE" else "#F43F5E"
        st.markdown(f"""
        <div class="glass-panel" style="padding: 16px;">
            <div style="color: #94A3B8; font-weight: 700; font-size: 0.8rem; text-transform: uppercase;">Cloud Database Sync</div>
            <div style="color: {st_color}; font-size: 1.8rem; font-weight: 800;">{st_status}</div>
            <div style="color: #64748B; font-size: 0.8rem;">Supabase PostgreSQL</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    # Dataset Tag Manager
    st.subheader("🏷️ Data Source Tag Manager")
    if not df_raw.empty and "Source" in df_raw.columns:
        source_counts = df_raw["Source"].value_counts().reset_index()
        source_counts.columns = ["Source Tag", "Record Count"]

        src_col1, src_col2 = st.columns([6, 4])
        with src_col1:
            st.dataframe(source_counts, use_container_width=True, hide_index=True)
        with src_col2:
            with st.form("rename_tag_form", clear_on_submit=False):
                old_tag_choice = st.selectbox("Select Dataset Tag", options=source_counts["Source Tag"].tolist(), key="select_tag_admin")
                new_tag_input = st.text_input("New Corrected Tag Name", placeholder="e.g. Ramadan 2025", key="rename_tag_admin")
                submit_rename = st.form_submit_button("✏️ Rename Tag", use_container_width=True)

            if submit_rename:
                if user_session.get("role") != "super_admin":
                    st.error("🔒 **Access Restricted:** Renaming dataset tags is restricted to Super Admin accounts.")
                elif old_tag_choice and new_tag_input.strip():
                    n_updated = update_source_tag(old_tag_choice, new_tag_input.strip())
                    st.session_state.pop("df_raw", None)
                    st.success(f"✅ Updated {n_updated:,} records from '{old_tag_choice}' ➔ '{new_tag_input.strip()}'!")
                    st.rerun()
                else:
                    st.warning("Please type a new tag name.")

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Delete Dataset", type="primary", use_container_width=True):
                if user_session.get("role") != "super_admin":
                    st.error("🔒 **Access Restricted:** Deleting dataset batches is restricted to **Super Admin** accounts only.")
                elif old_tag_choice:
                    n_deleted = delete_single_dataset(old_tag_choice)
                    st.session_state.pop("df_raw", None)
                    st.success(f"✅ Successfully deleted dataset '{old_tag_choice}' ({n_deleted:,} records removed)!")
                    st.rerun()

    # Database Purge / Reset Section (RESTRICTED TO SUPER ADMIN)
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    st.subheader("🚨 Danger Zone (Super Admin Only)")
    
    if user_session.get("role") != "super_admin":
        st.error("🔒 **Access Restricted:** Purging all database records is restricted to **Super Admin** accounts only.")
    else:
        with st.expander("🗑️ Purge All Loaded Data"):
            st.error("⚠️ **CAUTION:** Purging will permanently delete all records from SQLite, Parquet cache, and Cloud PostgreSQL!")
            confirm_purge = st.checkbox("I understand this will clear all loaded donation data", key="confirm_purge_check")
            if st.button("🚨 Permanently Purge All Data", type="primary", disabled=not confirm_purge):
                purge_all_data()
                st.session_state.pop("df_raw", None)
                st.success("✅ Database purged cleanly!")
                st.rerun()
