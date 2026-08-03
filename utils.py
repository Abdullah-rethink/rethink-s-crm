import pandas as pd
import numpy as np
import streamlit as st
import os
import sqlite3
import time
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Absolute path to SQLite DB — prevents issues with Streamlit changing CWD
_HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB_PATH = os.path.join(_HERE, "launchgood_donations.db")
LOCAL_DB_URL = f"sqlite:///{LOCAL_DB_PATH}"
local_engine = create_engine(LOCAL_DB_URL)

# Setup Cloud Database Engine (Supabase PostgreSQL for cloud sync)
DATABASE_URL = os.environ.get("DATABASE_URL", LOCAL_DB_URL)
connect_args = {}
if "postgres" in DATABASE_URL:
    connect_args = {"options": "-c statement_timeout=30000"}

cloud_engine = create_engine(
    DATABASE_URL, 
    connect_args=connect_args,
    pool_pre_ping=True
) if "postgres" in DATABASE_URL else None

# Main engine defaults to local_engine for ultra-fast query performance
engine = local_engine

CACHE_DIR = r'c:\Users\Lenovo\Documents\Antigravity\Python_Visualization\data_cache'

COUNTRY_ISO_MAP = {
    "GB": "United Kingdom", "UK": "United Kingdom", "GBR": "United Kingdom",
    "US": "United States", "USA": "United States",
    "CA": "Canada", "CAN": "Canada",
    "AU": "Australia", "AUS": "Australia",
    "AE": "United Arab Emirates", "ARE": "United Arab Emirates", "UAE": "United Arab Emirates",
    "SA": "Saudi Arabia", "SAU": "Saudi Arabia",
    "PK": "Pakistan", "PAK": "Pakistan",
    "IN": "India", "IND": "India",
    "MY": "Malaysia", "MYS": "Malaysia",
    "SG": "Singapore", "SGP": "Singapore",
    "NZ": "New Zealand", "NZL": "New Zealand", "DE": "Germany", "DEU": "Germany",
    "FR": "France", "FRA": "France", "NL": "Netherlands", "NLD": "Netherlands",
    "TR": "Turkey", "TUR": "Turkey", "ZA": "South Africa", "ZAF": "South Africa",
    "IE": "Ireland", "IRL": "Ireland", "QA": "Qatar", "QAT": "Qatar",
    "KW": "Kuwait", "KWT": "Kuwait", "BH": "Bahrain", "BHR": "Bahrain",
    "OM": "Oman", "OMN": "Oman", "JO": "Jordan", "JOR": "Jordan",
    "EG": "Egypt", "EGY": "Egypt", "BD": "Bangladesh", "BGD": "Bangladesh"
}

def classify_donor_amount(amount):
    """
    Classify donor based on donation amount:
    - < 200: Low End
    - 200 - 600: Medium Low
    - 600 - 1000: Medium
    - 1000 - 3000: High
    - > 3000: Super High
    """
    if pd.isna(amount):
        return "Unknown"
    elif amount < 200:
        return "Low End"
    elif 200 <= amount < 600:
        return "Medium Low"
    elif 600 <= amount < 1000:
        return "Medium"
    elif 1000 <= amount <= 3000:
        return "High"
    else:
        return "Super High"

def deduplicate_dataframe_columns(df):
    """
    Deduplicates DataFrame columns by case-insensitive name matching.
    Merges duplicate columns like 'status' and 'Status' cleanly so SQLite never errors.
    """
    if "status" in df.columns and "Status" in df.columns:
        df["Status"] = df["Status"].fillna(df["status"])
        df.drop(columns=["status"], inplace=True, errors="ignore")
    elif "status" in df.columns and "Status" not in df.columns:
        df.rename(columns={"status": "Status"}, inplace=True)

    cols_seen = {}
    cols_to_drop = []
    for col in df.columns:
        col_lower = str(col).strip().lower()
        if col_lower in cols_seen:
            orig_col = cols_seen[col_lower]
            df[orig_col] = df[orig_col].fillna(df[col])
            cols_to_drop.append(col)
        else:
            cols_seen[col_lower] = col

    if cols_to_drop:
        df.drop(columns=cols_to_drop, inplace=True, errors="ignore")

    df = df.loc[:, ~df.columns.duplicated()]
    return df

def fix_mojibake(val):
    """Repairs garbled UTF-8 Mojibake Arabic strings and invalid control bytes back into clean Arabic Unicode."""
    if not isinstance(val, str) or not val:
        return val

    # Fix specific control bytes
    if '\x81' in val or '\xad' in val:
        val = val.replace('\x81قير', 'فقير').replace('\x81', 'ف').replace('\xad', '')

    # Direct Mojibake replacements for common Arabic fragments
    if any(m in val for m in ['Ù', 'Ø', 'Â', 'Ã', 'â']):
        val = val.replace('ÙفÙ‚ÙŠØ±', 'فقير').replace('فÙ‚ÙŠØ±', 'فقير').replace('Ù‚ÙŠØ±', 'قير')
        val = val.replace('Ø§Ù„ØºÙ†Ù‰', 'الغنى').replace('Ø§Ù„Ù„Ù‡', 'الله').replace('Ù†ØÙ†', 'نحن')
        val = val.replace('ÙفÙ‚Ø±Ø§Ø¡', 'فقراء').replace('Ø¥Ù„Ù‰', 'إلى')
        try:
            val = val.encode('latin1').decode('utf-8')
        except Exception:
            try:
                val = val.encode('cp1252').decode('utf-8')
            except Exception:
                pass
    return val

REQUIRED_COLS = [
    "Donation ID", "Email", "First Name", "Last Name", "Billing Name", 
    "Anonymous or Public", "Billing Country", "Donation Currency (DC)", 
    "Donation Amount (in Donation Currency)", "Donation Amount in Project Currency (May be approx.)", 
    "Zakat (yes or no)", "Gift Aid (yes or no)", "Campaign Name", "Community Name", 
    "Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility", "Source", 
    "Project Impact Location", "Payment Type", "Created Date (UTC)", "Status"
]

PARQUET_PATH = os.path.join(_HERE, "donations_cache.parquet")
SYNC_STATUS_PATH = os.path.join(_HERE, ".cloud_sync_status.json")

def _write_sync_status(success: bool, operation: str, error_msg: str = ""):
    """Writes cloud sync result to a local status file so the UI can surface failures."""
    import json
    status = {
        "success": success,
        "operation": operation,
        "error": error_msg,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }
    try:
        with open(SYNC_STATUS_PATH, "w") as f:
            json.dump(status, f)
    except Exception:
        pass  # Don't crash the sync thread over a status write failure

def get_cloud_sync_status():
    """Returns the last cloud sync status dict, or None if never synced."""
    import json
    if not os.path.exists(SYNC_STATUS_PATH):
        return None
    try:
        with open(SYNC_STATUS_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def normalize_classifications(df):
    for col in ["Lifetime Donor Classification", "Transaction Donor Classification"]:
        if col in df.columns:
            df[col] = df[col].astype(str).replace({
                "Low End (<$200)": "Low End",
                "Low End (<£200)": "Low End",
                "Low End (<Mixed 200)": "Low End",
                "Medium Low ($200-$600)": "Medium Low",
                "Medium Low (£200-£600)": "Medium Low",
                "Medium Low (Mixed 200-Mixed 600)": "Medium Low",
                "Medium ($600-$1000)": "Medium",
                "Medium (£600-£1000)": "Medium",
                "Medium (Mixed 600-Mixed 1000)": "Medium",
                "High ($1000-$3000)": "High",
                "High (£1000-£3000)": "High",
                "High (Mixed 1000-Mixed 3000)": "High",
                "Super High (>$3000)": "Super High",
                "Super High (>£3000)": "Super High",
                "Super High (>Mixed 3000)": "Super High",
            })
    return df

@st.cache_resource(show_spinner=False, ttl=3600)
def load_data():
    """
    Reads from Parquet cache (~0.05s) if it exists, else falls back to SQLite.
    Parquet is a binary columnar format — 30x faster than SQLite for bulk reads.
    """
    DERIVED_COLS = ["Donor ID", "Total LTV", "Lifetime Donor Classification", 
                    "Transaction Donor Classification", "Payment Frequency"]
    ALL_NEEDED = REQUIRED_COLS + [c for c in DERIVED_COLS if c not in REQUIRED_COLS]

    # Step 1: Try Parquet (fastest possible — ~0.05s for 88k rows)
    if os.path.exists(PARQUET_PATH):
        try:
            df = pd.read_parquet(PARQUET_PATH)
            if not df.empty:
                for c in ['Created Date (UTC)', 'Settled Date (UTC)']:
                    if c in df.columns and not pd.api.types.is_datetime64_any_dtype(df[c]):
                        df[c] = pd.to_datetime(df[c], format='mixed', errors='coerce')
                return normalize_classifications(df)
        except Exception:
            pass

    # Step 2: Fall back to SQLite if no Parquet cache
    if os.path.exists(LOCAL_DB_PATH):
        try:
            conn = sqlite3.connect(LOCAL_DB_PATH)
            cursor = conn.execute("PRAGMA table_info(donations)")
            avail = {row[1] for row in cursor.fetchall()}
            cols = [c for c in ALL_NEEDED if c in avail]
            if cols:
                cols_str = ", ".join([f'"{c}"' for c in cols])
                df = pd.read_sql_query(f"SELECT {cols_str} FROM donations", con=conn)
                conn.close()
                if not df.empty:
                    for c in ['Created Date (UTC)', 'Settled Date (UTC)']:
                        if c in df.columns:
                            df[c] = pd.to_datetime(df[c], format='mixed', errors='coerce')
                    # Save as Parquet for next time (instant load)
                    df = normalize_classifications(df)
                    df.to_parquet(PARQUET_PATH, index=False)
                    return df
            conn.close()
        except Exception:
            pass

    return pd.DataFrame()


def init_classification_db():
    """Ensure campaign_classifications table exists in SQLite DB."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_classifications (
                campaign_name TEXT NOT NULL,
                community_name TEXT NOT NULL,
                heading TEXT DEFAULT 'Unassigned',
                sub_heading TEXT DEFAULT 'Unassigned',
                country TEXT DEFAULT 'Unassigned',
                code TEXT DEFAULT 'Unassigned',
                zakat_eligibility TEXT DEFAULT 'Unassigned',
                PRIMARY KEY (campaign_name, community_name)
            );
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Classification DB init notice: {e}")

def sync_donor_classifications_to_matrix(df_raw):
    """
    Extracts updated campaign classifications from donor records and syncs them
    into campaign_classifications and givebright_classifications SQLite tables.
    """
    if df_raw.empty or "Campaign Name" not in df_raw.columns:
        return
        
    target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
    available_targets = [c for c in target_cols if c in df_raw.columns]
    if not available_targets:
        return

    init_classification_db()
    init_givebright_classification_db()
    
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    try:
        # 1. Sync LaunchGood / Default rows
        lg_mask = df_raw.get("Platform", pd.Series("", index=df_raw.index)) != "GiveBright"
        if lg_mask.any():
            lg_df = df_raw[lg_mask]
            comm_col = "Community Name" if "Community Name" in lg_df.columns else None
            group_cols = ["Campaign Name"] + ([comm_col] if comm_col else [])
            
            lg_matrix = lg_df.groupby(group_cols)[available_targets].first().reset_index()
            if comm_col is None:
                lg_matrix["Community Name"] = "N/A"
                
            lg_save = lg_matrix.rename(columns={
                "Campaign Name": "campaign_name",
                "Community Name": "community_name",
                "Heading": "heading",
                "Sub-Heading": "sub_heading",
                "Country": "country",
                "Code": "code",
                "Zakat Eligibility": "zakat_eligibility"
            })
            
            db_cols = ["campaign_name", "community_name", "heading", "sub_heading", "country", "code", "zakat_eligibility"]
            lg_save = lg_save[[c for c in db_cols if c in lg_save.columns]]
            
            try:
                existing_lg = pd.read_sql_query("SELECT * FROM campaign_classifications", conn)
                if not existing_lg.empty:
                    lg_save = pd.concat([existing_lg, lg_save], ignore_index=True).drop_duplicates(subset=["campaign_name", "community_name"], keep="last")
            except Exception:
                pass
                
            lg_save.to_sql("campaign_classifications", con=conn, if_exists="replace", index=False)

        # 2. Sync GiveBright rows
        gb_mask = df_raw.get("Platform", pd.Series("", index=df_raw.index)) == "GiveBright"
        if gb_mask.any():
            gb_df = df_raw[gb_mask]
            gb_matrix = gb_df.groupby("Campaign Name")[available_targets].first().reset_index()
            
            gb_save = gb_matrix.rename(columns={
                "Campaign Name": "campaign_name",
                "Heading": "heading",
                "Sub-Heading": "sub_heading",
                "Country": "country",
                "Code": "code",
                "Zakat Eligibility": "zakat_eligibility"
            })
            
            db_cols_gb = ["campaign_name", "heading", "sub_heading", "country", "code", "zakat_eligibility"]
            gb_save = gb_save[[c for c in db_cols_gb if c in gb_save.columns]]
            
            try:
                existing_gb = pd.read_sql_query("SELECT * FROM givebright_classifications", conn)
                if not existing_gb.empty:
                    gb_save = pd.concat([existing_gb, gb_save], ignore_index=True).drop_duplicates(subset=["campaign_name"], keep="last")
            except Exception:
                pass
                
            gb_save.to_sql("givebright_classifications", con=conn, if_exists="replace", index=False)
            
        conn.commit()
    except Exception as e:
        print(f"Error syncing donor classifications to matrix: {e}")
    finally:
        conn.close()

def _mode_or_last(series):
    """Returns the most frequently occurring non-Unassigned value in the series, or the last value as fallback."""
    clean = series.astype(str).replace({'nan': '', 'None': '', 'Unassigned': ''})
    clean = clean[clean.str.strip() != '']
    if clean.empty:
        return series.iloc[-1] if not series.empty else 'Unassigned'
    mode_vals = clean.mode()
    return mode_vals.iloc[0] if not mode_vals.empty else clean.iloc[-1]

def get_classification_matrix():
    """
    Returns the campaign_classifications matrix DataFrame from SQLite DB,
    merged with real-time active donor classifications.
    """
    init_classification_db()

    target_cols_display = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]

    try:
        # Primary source: live Parquet (always up to date after donor saves)
        if os.path.exists(PARQUET_PATH):
            df_donations = pd.read_parquet(PARQUET_PATH)
            if not df_donations.empty and "Campaign Name" in df_donations.columns:
                lg_mask = df_donations.get("Platform", pd.Series("", index=df_donations.index)) != "GiveBright"
                lg_df = df_donations[lg_mask] if lg_mask.any() else df_donations

                c_name = lg_df["Campaign Name"].astype(str).fillna("N/A")
                comm_name = lg_df["Community Name"].astype(str).fillna("N/A") if "Community Name" in lg_df.columns else pd.Series("N/A", index=lg_df.index)

                available_target_cols = [c for c in target_cols_display if c in lg_df.columns]
                donor_df = pd.DataFrame({"Campaign Name": c_name, "Community Name": comm_name})
                for tc in available_target_cols:
                    donor_df[tc] = lg_df[tc].values

                # Take the most frequently occurring value per (Campaign, Community) pair.
                # This means if 90 rows have Code=GBR-FBK and 2 have FBK-GBR, the matrix shows GBR-FBK.
                matrix_df = donor_df.groupby(["Campaign Name", "Community Name"])[available_target_cols].agg(_mode_or_last).reset_index()
                
                # Supplement with SQLite for any campaigns not in live Parquet
                conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                try:
                    db_matrix = pd.read_sql_query("SELECT * FROM campaign_classifications", conn)
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
                        # Only add rows from DB that are NOT already in the live Parquet matrix
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
        print(f"Matrix load notice: {e}")
        # Fallback: read from SQLite only
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        try:
            matrix_df = pd.read_sql_query("SELECT * FROM campaign_classifications", conn)
            matrix_df.rename(columns={
                "campaign_name": "Campaign Name",
                "community_name": "Community Name",
                "heading": "Heading",
                "sub_heading": "Sub-Heading",
                "country": "Country",
                "code": "Code",
                "zakat_eligibility": "Zakat Eligibility"
            }, inplace=True)
        except Exception:
            matrix_df = pd.DataFrame(columns=["Campaign Name", "Community Name"] + target_cols_display)
        finally:
            conn.close()

    for col in target_cols_display:
        if col not in matrix_df.columns:
            matrix_df[col] = "Unassigned"
        matrix_df[col] = matrix_df[col].fillna("Unassigned").astype(str).replace({'nan': 'Unassigned', '': 'Unassigned', 'None': 'Unassigned'})

    return matrix_df


def save_classification_matrix(matrix_df):
    """
    Saves the user-edited classification matrix into SQLite DB table campaign_classifications
    and re-enriches active donation records in-place across Parquet cache, SQLite, and Supabase!
    """
    if matrix_df.empty:
        return 0

    init_classification_db()
    save_df = matrix_df.copy()
    save_df.rename(columns={
        "Campaign Name": "campaign_name",
        "Community Name": "community_name",
        "Heading": "heading",
        "Sub-Heading": "sub_heading",
        "Country": "country",
        "Code": "code",
        "Zakat Eligibility": "zakat_eligibility"
    }, inplace=True)

    db_cols = ["campaign_name", "community_name", "heading", "sub_heading", "country", "code", "zakat_eligibility"]
    save_df = save_df[[c for c in db_cols if c in save_df.columns]]

    conn = sqlite3.connect(LOCAL_DB_PATH)
    try:
        save_df.to_sql("campaign_classifications", con=conn, if_exists="replace", index=False)
        conn.commit()
    finally:
        conn.close()

    # Re-apply to active dataset in Parquet and SQLite using vectorized pd.merge (~0.05s for 88k rows)
    if os.path.exists(PARQUET_PATH):
        df_donations = pd.read_parquet(PARQUET_PATH)
        if not df_donations.empty and "Campaign Name" in df_donations.columns:
            target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
            df_donations.drop(columns=[c for c in target_cols if c in df_donations.columns], inplace=True, errors="ignore")
            
            clean_matrix = matrix_df[["Campaign Name", "Community Name"] + [c for c in target_cols if c in matrix_df.columns]].drop_duplicates(subset=["Campaign Name", "Community Name"])
            df_donations = pd.merge(df_donations, clean_matrix, on=["Campaign Name", "Community Name"], how="left")
            
            for f in target_cols:
                if f in df_donations.columns:
                    df_donations[f] = df_donations[f].fillna("Unassigned").astype(str).replace({'nan': 'Unassigned', '': 'Unassigned', 'None': 'Unassigned'})

            df_donations.to_parquet(PARQUET_PATH, index=False)
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            df_donations.to_sql("donations", con=conn, if_exists="replace", index=False)
            conn.close()

    st.cache_data.clear()
    st.cache_resource.clear()
    return len(matrix_df)

COUNTRY_ISO_MAP = {
    "GB": "United Kingdom",
    "US": "United States",
    "CA": "Canada",
    "AU": "Australia",
    "AE": "United Arab Emirates",
    "SA": "Saudi Arabia",
    "QA": "Qatar",
    "KW": "Kuwait",
    "BH": "Bahrain",
    "OM": "Oman",
    "PK": "Pakistan",
    "IN": "India",
    "BD": "Bangladesh",
    "MY": "Malaysia",
    "SG": "Singapore",
    "DE": "Germany",
    "FR": "France",
    "NL": "Netherlands",
    "IE": "Ireland",
    "NZ": "New Zealand",
    "ZA": "South Africa"
}

def init_givebright_classification_db():
    """Ensure givebright_classifications table exists in SQLite DB."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS givebright_classifications (
                campaign_name TEXT PRIMARY KEY,
                heading TEXT DEFAULT 'Unassigned',
                sub_heading TEXT DEFAULT 'Unassigned',
                country TEXT DEFAULT 'Unassigned',
                code TEXT DEFAULT 'Unassigned',
                zakat_eligibility TEXT DEFAULT 'Unassigned'
            );
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"GiveBright Classification DB init notice: {e}")

def get_givebright_classification_matrix():
    """Returns the givebright_classifications matrix from live Parquet (source of truth) supplemented by SQLite."""
    init_givebright_classification_db()
    target_cols_display = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]

    try:
        # Primary source: live Parquet (always up to date after donor saves)
        if os.path.exists(PARQUET_PATH):
            df_donations = pd.read_parquet(PARQUET_PATH)
            if not df_donations.empty and "Campaign Name" in df_donations.columns:
                gb_mask = df_donations.get("Platform", pd.Series("", index=df_donations.index)) == "GiveBright"
                if gb_mask.any():
                    gb_df = df_donations[gb_mask]
                    c_name = gb_df["Campaign Name"].astype(str).fillna("N/A")
                    available_target_cols = [c for c in target_cols_display if c in gb_df.columns]
                    
                    donor_df = pd.DataFrame({"Campaign Name": c_name})
                    for tc in available_target_cols:
                        donor_df[tc] = gb_df[tc].values
                    
                    matrix_df = donor_df.groupby("Campaign Name")[available_target_cols].agg(_mode_or_last).reset_index()
                    
                    # Supplement with SQLite for any campaigns not in live Parquet
                    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                    try:
                        db_matrix = pd.read_sql_query("SELECT * FROM givebright_classifications", conn)
                        db_matrix.rename(columns={
                            "campaign_name": "Campaign Name",
                            "heading": "Heading",
                            "sub_heading": "Sub-Heading",
                            "country": "Country",
                            "code": "Code",
                            "zakat_eligibility": "Zakat Eligibility"
                        }, inplace=True)
                        if not db_matrix.empty:
                            existing_keys = set(matrix_df["Campaign Name"].astype(str))
                            new_rows = db_matrix[~db_matrix["Campaign Name"].astype(str).isin(existing_keys)]
                            if not new_rows.empty:
                                matrix_df = pd.concat([matrix_df, new_rows], ignore_index=True)
                    except Exception:
                        pass
                    finally:
                        conn.close()
                    
                    for col in target_cols_display:
                        if col not in matrix_df.columns:
                            matrix_df[col] = "Unassigned"
                        matrix_df[col] = matrix_df[col].fillna("Unassigned").astype(str).replace({'nan': 'Unassigned', '': 'Unassigned', 'None': 'Unassigned'})
                    return matrix_df

    except Exception as e:
        print(f"GB matrix load notice: {e}")

    # Fallback: read from SQLite only
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    try:
        matrix_df = pd.read_sql_query("SELECT * FROM givebright_classifications", conn)
        matrix_df.rename(columns={
            "campaign_name": "Campaign Name",
            "heading": "Heading",
            "sub_heading": "Sub-Heading",
            "country": "Country",
            "code": "Code",
            "zakat_eligibility": "Zakat Eligibility"
        }, inplace=True)
    except Exception:
        matrix_df = pd.DataFrame(columns=["Campaign Name"] + target_cols_display)
    finally:
        conn.close()

    for col in target_cols_display:
        if col not in matrix_df.columns:
            matrix_df[col] = "Unassigned"
        matrix_df[col] = matrix_df[col].fillna("Unassigned").astype(str).replace({'nan': 'Unassigned', '': 'Unassigned', 'None': 'Unassigned'})

    return matrix_df

def save_givebright_classification_matrix(matrix_df):
    """Saves edited GiveBright classification matrix into SQLite DB and re-enriches active GiveBright records."""
    if matrix_df.empty:
        return 0

    init_givebright_classification_db()
    save_df = matrix_df.copy()
    save_df.rename(columns={
        "Campaign Name": "campaign_name",
        "Heading": "heading",
        "Sub-Heading": "sub_heading",
        "Country": "country",
        "Code": "code",
        "Zakat Eligibility": "zakat_eligibility"
    }, inplace=True)

    db_cols = ["campaign_name", "heading", "sub_heading", "country", "code", "zakat_eligibility"]
    save_df = save_df[[c for c in db_cols if c in save_df.columns]].drop_duplicates("campaign_name")

    conn = sqlite3.connect(LOCAL_DB_PATH)
    try:
        save_df.to_sql("givebright_classifications", con=conn, if_exists="replace", index=False)
        conn.commit()
    finally:
        conn.close()

    # Re-apply to active dataset in Parquet and SQLite
    if os.path.exists(PARQUET_PATH):
        df_donations = pd.read_parquet(PARQUET_PATH)
        if not df_donations.empty and "Campaign Name" in df_donations.columns:
            target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
            map_data = matrix_df.set_index("Campaign Name")
            
            gb_mask = df_donations.get("Platform", pd.Series("", index=df_donations.index)) == "GiveBright"
            if gb_mask.any():
                for f in target_cols:
                    if f in matrix_df.columns:
                        map_dict = map_data[f].to_dict() if f in map_data.columns else {}
                        mapped_vals = df_donations.loc[gb_mask, "Campaign Name"].map(map_dict).fillna("Unassigned")
                        df_donations.loc[gb_mask, f] = mapped_vals

                df_donations = deduplicate_dataframe_columns(df_donations)
                df_donations.to_parquet(PARQUET_PATH, index=False)
                conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                df_donations.to_sql("donations", con=conn, if_exists="replace", index=False)
                conn.close()

    st.cache_data.clear()
    st.cache_resource.clear()
    return len(matrix_df)

def delete_single_dataset(source_tag):
    """
    Deletes all records matching the given source_tag from Parquet cache, local SQLite, and Cloud DB.
    """
    if not source_tag or str(source_tag).strip() == "":
        return 0

    deleted_rows = 0

    # 1. Update Parquet cache
    if os.path.exists(PARQUET_PATH):
        try:
            df = pd.read_parquet(PARQUET_PATH)
            if not df.empty and "Source" in df.columns:
                initial_count = len(df)
                df_filtered = df[df["Source"].astype(str) != str(source_tag)]
                deleted_rows = initial_count - len(df_filtered)
                
                if df_filtered.empty:
                    os.remove(PARQUET_PATH)
                else:
                    df_filtered = _enrich_dataframe(df_filtered)
                    df_filtered = deduplicate_dataframe_columns(df_filtered)
                    df_filtered.to_parquet(PARQUET_PATH, index=False)
                    
                    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                    df_filtered.to_sql("donations", con=conn, if_exists="replace", index=False)
                    conn.close()
        except Exception as e:
            print(f"Delete single dataset Parquet notice: {e}")

    # 2. Delete from SQLite DB directly if Parquet didn't run
    if os.path.exists(LOCAL_DB_PATH):
        try:
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM donations WHERE Source = ?", (str(source_tag),))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Delete single dataset SQLite notice: {e}")

    # 3. Delete from Supabase Cloud DB in background
    if DATABASE_URL and "postgres" in DATABASE_URL:
        def delete_cloud():
            try:
                import psycopg2
                conn = psycopg2.connect(DATABASE_URL)
                cur = conn.cursor()
                cur.execute('DELETE FROM "donations" WHERE "Source" = %s;', (str(source_tag),))
                conn.commit()
                cur.close()
                conn.close()
                _write_sync_status(True, f"delete dataset '{source_tag}'")
                print(f"✅ Deleted source tag '{source_tag}' from Supabase Cloud DB.")
            except Exception as e:
                _write_sync_status(False, f"delete dataset '{source_tag}'", str(e))
                print(f"Cloud delete notice: {e}")
        threading.Thread(target=delete_cloud, daemon=True).start()

    st.cache_data.clear()
    st.cache_resource.clear()
    return deleted_rows

def import_givebright_classifications_file(file_path_or_buffer):
    """Imports Give_bright - Campaign-List_Givebright.csv into givebright_classifications DB table."""
    if isinstance(file_path_or_buffer, str):
        df_gb = pd.read_csv(file_path_or_buffer)
    else:
        file_path_or_buffer.seek(0)
        try:
            df_gb = pd.read_csv(file_path_or_buffer)
        except Exception:
            file_path_or_buffer.seek(0)
            df_gb = pd.read_excel(file_path_or_buffer)
            
    col_map = {
        "Campaign": "Campaign Name",
        "Main Heading": "Heading",
        "Sub-Heading": "Sub-Heading",
        "Country": "Country",
        "Code": "Code",
        "Zakat Eligibilty": "Zakat Eligibility",
        "Zakat Eligibility": "Zakat Eligibility"
    }
    df_gb.rename(columns=col_map, inplace=True)
    
    target_cols = ["Campaign Name", "Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
    for c in target_cols:
        if c not in df_gb.columns:
            df_gb[c] = "Unassigned"
        df_gb[c] = df_gb[c].fillna("Unassigned").astype(str).replace({'nan': 'Unassigned', '': 'Unassigned', 'None': 'Unassigned', 'TBC': 'To be confirmed'})
        
    res = save_givebright_classification_matrix(df_gb[target_cols])
    return res

def update_source_tag(old_tag, new_tag):
    """Updates a Source label across active records in Parquet & SQLite & Cloud."""
    if not old_tag or not new_tag or old_tag == new_tag:
        return 0
        
    updated_count = 0
    if os.path.exists(PARQUET_PATH):
        df = pd.read_parquet(PARQUET_PATH)
        if not df.empty and "Source" in df.columns:
            mask = df["Source"] == old_tag
            updated_count = mask.sum()
            df.loc[mask, "Source"] = new_tag
            df.to_parquet(PARQUET_PATH, index=False)
            
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            df.to_sql("donations", con=conn, if_exists="replace", index=False)
            conn.close()

            # Sync rename to Supabase cloud in background
            if DATABASE_URL and "postgres" in DATABASE_URL:
                def _rename_cloud():
                    try:
                        import psycopg2
                        conn = psycopg2.connect(DATABASE_URL)
                        cur = conn.cursor()
                        cur.execute('UPDATE "donations" SET "Source" = %s WHERE "Source" = %s;', (str(new_tag), str(old_tag)))
                        conn.commit()
                        cur.close()
                        conn.close()
                        _write_sync_status(True, f"rename '{old_tag}' → '{new_tag}'")
                    except Exception as e:
                        _write_sync_status(False, f"rename '{old_tag}' → '{new_tag}'", str(e))
                        print(f"Cloud source tag rename notice: {e}")
                threading.Thread(target=_rename_cloud, daemon=True).start()


    st.cache_data.clear()
    return updated_count


def _enrich_dataframe(df):
    """
    Pre-compute all derived columns (Donor ID, LTV, Classification, Payment Frequency).
    This runs ONCE at upload time so load_data() stays instant.
    """
    # Align and unify amounts across platforms
    if "Total Online Donations Net Amount in Settled Currency" in df.columns and "Donation Amount in Project Currency (May be approx.)" in df.columns:
        df["Total Online Donations Net Amount in Settled Currency"] = df["Total Online Donations Net Amount in Settled Currency"].fillna(df["Donation Amount in Project Currency (May be approx.)"])
    elif "Total Online Donations Net Amount in Settled Currency" not in df.columns and "Donation Amount in Project Currency (May be approx.)" in df.columns:
        df["Total Online Donations Net Amount in Settled Currency"] = df["Donation Amount in Project Currency (May be approx.)"]

    col_amount = "Total Online Donations Net Amount in Settled Currency"
    if col_amount not in df.columns:
        col_amount = "Donation Amount in Project Currency (May be approx.)"
    if col_amount not in df.columns:
        col_amount = "Donation Amount (in Donation Currency)"

    # Identity Resolution - Vectorized
    df['email_clean'] = df['Email'].astype(str).str.strip().str.lower()
    df['email_clean'] = df['email_clean'].where(~df['email_clean'].isin(['nan', 'none', '']), None)
    fname = df['First Name'].astype(str).str.strip().str.lower().replace({'nan': '', 'none': ''})
    lname = df['Last Name'].astype(str).str.strip().str.lower().replace({'nan': '', 'none': ''})
    df['full_name_clean'] = (fname + " " + lname).str.strip()
    df['full_name_clean'] = df['full_name_clean'].where(~df['full_name_clean'].isin(['', 'nan', 'none']), None)

    bname_col = df['Billing Name'] if 'Billing Name' in df.columns else pd.Series(index=df.index, dtype=str)
    df['bname_clean'] = bname_col.astype(str).str.strip().str.lower()
    df['bname_clean'] = df['bname_clean'].where(~df['bname_clean'].isin(['nan', 'none', '']), None)

    valid = df.dropna(subset=['full_name_clean', 'email_clean'])
    name_to_email_map = valid.groupby('full_name_clean')['email_clean'].first()

    mapped_email_from_name = df['full_name_clean'].map(name_to_email_map)
    mapped_email_from_billing = df['bname_clean'].map(name_to_email_map)

    df['Donor ID'] = df['email_clean'] \
        .combine_first(mapped_email_from_name) \
        .combine_first(df['full_name_clean']) \
        .combine_first(mapped_email_from_billing) \
        .combine_first(df['bname_clean']) \
        .combine_first(df.get('Donation ID', pd.Series(range(len(df)), index=df.index)).astype(str))

    df.drop(columns=['email_clean', 'full_name_clean', 'bname_clean'], inplace=True, errors='ignore')

    # LTV Calculation & Classification
    if col_amount in df.columns:
        df[col_amount] = pd.to_numeric(df[col_amount], errors='coerce').fillna(0)
        ltv_map = df.groupby('Donor ID')[col_amount].sum()
        df['Total LTV'] = df['Donor ID'].map(ltv_map)
        df['Lifetime Donor Classification'] = df['Total LTV'].apply(classify_donor_amount)
        df['Transaction Donor Classification'] = df[col_amount].apply(classify_donor_amount)

    # Payment Frequency
    donor_counts = df['Donor ID'].value_counts()
    repeat_donors = set(donor_counts[donor_counts > 1].index)
    df['Payment Frequency'] = df['Donor ID'].map(
        lambda d: 'Recurring Payment' if d in repeat_donors else 'One-Time Payment'
    )

    # Apply Classification Matrices (LaunchGood & GiveBright)
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
        
        # Initialize target columns if not present
        for f in target_cols:
            if f not in df.columns:
                df[f] = "Unassigned"
        
        # 1. Apply GiveBright Classification Matrix for GiveBright records
        init_givebright_classification_db()
        gb_matrix = pd.read_sql_query("SELECT * FROM givebright_classifications", conn)
        if not gb_matrix.empty and "campaign_name" in gb_matrix.columns:
            gb_map = gb_matrix.set_index("campaign_name")
            gb_mask = df.get("Platform", pd.Series("", index=df.index)) == "GiveBright"
            if gb_mask.any():
                for f in target_cols:
                    db_f = f.lower().replace("-", "_").replace(" ", "_")
                    if db_f in gb_matrix.columns:
                        map_dict = gb_map[db_f].to_dict()
                        mapped_series = df.loc[gb_mask, "Campaign Name"].map(map_dict)
                        valid_mask = mapped_series.notna() & (mapped_series.astype(str).str.strip() != "")
                        df.loc[gb_mask & valid_mask, f] = mapped_series[valid_mask]

        # 2. Apply LaunchGood Classification Matrix for LaunchGood / default records
        init_classification_db()
        lg_matrix = pd.read_sql_query("SELECT * FROM campaign_classifications", conn)
        if not lg_matrix.empty and "campaign_name" in lg_matrix.columns:
            lg_matrix.rename(columns={
                "campaign_name": "Campaign Name",
                "community_name": "Community Name",
                "heading": "Heading_mat",
                "sub_heading": "Sub-Heading_mat",
                "country": "Country_mat",
                "code": "Code_mat",
                "zakat_eligibility": "Zakat Eligibility_mat"
            }, inplace=True)
            
            cols_to_keep = ["Campaign Name", "Community Name"] + [f"{f}_mat" for f in target_cols]
            lg_matrix = lg_matrix[cols_to_keep].drop_duplicates(subset=["Campaign Name", "Community Name"])
            
            lg_mask = df.get("Platform", pd.Series("", index=df.index)) != "GiveBright"
            if lg_mask.any():
                merged = pd.merge(df[lg_mask], lg_matrix, on=["Campaign Name", "Community Name"], how="left")
                for f in target_cols:
                    mat_col = f"{f}_mat"
                    if mat_col in merged.columns:
                        val_series = merged[mat_col].fillna("").astype(str).str.strip()
                        orig_series = merged[f].fillna("").astype(str).str.strip()
                        
                        final_series = val_series.where((val_series != "") & (val_series != "Unassigned"), orig_series)
                        final_series = final_series.where(final_series.notna() & (final_series != ""), "Unassigned")
                        
                        df.loc[lg_mask, f] = final_series.values

        conn.close()
    except Exception as e:
        print(f"Enrich classification notice: {e}")

    # Deduplicate columns case-insensitively (e.g. merge 'status' and 'Status')
    df = deduplicate_dataframe_columns(df)

    # Cast object columns to str & repair Mojibake garbled Arabic text
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).apply(fix_mojibake)

    return df

import threading

def purge_all_data():
    """
    Completely purges all loaded data across Parquet cache, local SQLite, and Supabase cloud DB.
    """
    import sqlite3, gc
    st.cache_data.clear()
    st.cache_resource.clear()
    
    # 1. Clear Parquet cache file
    if os.path.exists(PARQUET_PATH):
        try:
            os.remove(PARQUET_PATH)
        except Exception as e:
            print(f"Parquet purge notice: {e}")

    # 2. Drop table in local SQLite DB
    try:
        local_engine.dispose()
        gc.collect()
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        conn.execute("DROP TABLE IF EXISTS donations;")
        conn.execute("VACUUM;")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"SQLite purge notice: {e}")

    # 3. Drop table in Supabase Cloud DB if connected
    if DATABASE_URL and "postgres" in DATABASE_URL:
        try:
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute('DROP TABLE IF EXISTS "donations";')
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Cloud purge notice: {e}")

    st.cache_data.clear()

def process_and_upload_excel(file_buffer, source_name=None, upload_mode="replace", platform="auto"):
    """
    Reads an uploaded Excel or CSV file (LaunchGood or GiveBright), standardizes schema,
    pre-computes all derived columns (Donor ID, LTV, Classification), saves to local SQLite,
    and syncs to Supabase in a background thread.
    """
    # 0. Ensure GiveBright classifications seeded if file exists locally
    gb_csv_local = os.path.join(_HERE, "Give_bright - Campaign-List_Givebright.csv")
    if os.path.exists(gb_csv_local):
        try:
            import_givebright_classifications_file(gb_csv_local)
        except Exception as e:
            print(f"Auto seed GiveBright classification notice: {e}")

    # 1. Parse Excel or CSV
    is_csv = False
    fname = getattr(file_buffer, 'name', '')
    if isinstance(fname, str) and fname.lower().endswith('.csv'):
        is_csv = True
        
    try:
        if is_csv:
            df = pd.read_csv(file_buffer)
        else:
            try:
                sheets_dict = pd.read_excel(file_buffer, sheet_name=None)
                if not sheets_dict:
                    raise ValueError("Excel file is empty.")
                
                list_of_dfs = []
                for sname, sdf in sheets_dict.items():
                    if not sdf.empty:
                        # Clean column whitespace
                        sdf.columns = [str(c).strip() for c in sdf.columns]
                        list_of_dfs.append(sdf)
                
                if not list_of_dfs:
                    raise ValueError("No non-empty sheets found in Excel file.")
                
                df = pd.concat(list_of_dfs, ignore_index=True)
            except Exception:
                file_buffer.seek(0)
                df = pd.read_csv(file_buffer)
    except Exception as e:
        raise ValueError(f"Failed to parse upload file: {e}")
        
    # 2. Platform Schema Adaptation (GiveBright vs LaunchGood)
    is_givebright = False
    if str(platform).lower() == "givebright":
        is_givebright = True
    elif str(platform).lower() in ["auto", "none", ""]:
        gb_sig = {"donation_id", "campaign_name", "fundraiser_by", "charge_id", "payment_method_type"}
        if len(gb_sig.intersection(set(df.columns))) >= 2:
            is_givebright = True

    if is_givebright:
        df["Platform"] = "GiveBright"
        col_map = {
            "donation_id": "Donation ID",
            "campaign_name": "Campaign Name",
            "fundraiser_by": "Community Name",
            "amount": "Donation Amount in Project Currency (May be approx.)",
            "currency": "Donation Currency (DC)",
            "is_anonymous": "Anonymous or Public",
            "country": "Billing Country",
            "first_name": "First Name",
            "last_name": "Last Name",
            "email": "Email"
        }
        df.rename(columns=col_map, inplace=True)

        if "subscription_id" in df.columns:
            df["Payment Frequency"] = df["subscription_id"].apply(
                lambda s: "Recurring Payment" if pd.notna(s) and str(s).strip() not in ["", "nan", "None"] else "One-Time Payment"
            )

        if "Anonymous or Public" in df.columns:
            df["Anonymous or Public"] = df["Anonymous or Public"].apply(
                lambda a: "Anonymous" if pd.notna(a) and str(a).lower() in ["true", "1", "yes"] else "Public"
            )

        if "Billing Country" in df.columns:
            def safe_country(c):
                if pd.isna(c) or str(c).strip() in ["", "nan", "None", "NaN"]:
                    return "Unknown"
                c_str = str(c).strip()
                return COUNTRY_ISO_MAP.get(c_str.upper(), c_str)

            df["Billing Country"] = df["Billing Country"].apply(safe_country)

        if "created_at" in df.columns:
            df["Created Date (UTC)"] = pd.to_datetime(df["created_at"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
            df["Created Date (UTC)"] = df["Created Date (UTC)"].fillna(pd.to_datetime(df["created_at"], errors="coerce"))
    else:
        df["Platform"] = "LaunchGood"

    # 3. Determine batch data source label
    batch_label = str(source_name).strip() if (source_name and str(source_name).strip()) else None
    if not batch_label:
        fname = getattr(file_buffer, 'name', 'Master Dataset')
        if isinstance(fname, str) and "." in fname:
            fname = fname.rsplit(".", 1)[0]
        batch_label = fname or "Master Dataset"
    
    # Handle Source column referral strings
    if "Source" in df.columns:
        uniq_vals = df["Source"].dropna().unique()
        if len(uniq_vals) > 5 or (len(uniq_vals) == 1 and str(uniq_vals[0]).strip() != batch_label):
            df.rename(columns={"Source": "UTM / Referral Source"}, inplace=True)
            
    df["Source"] = batch_label

    # Deduplicate columns case-insensitively before enrichment
    df = deduplicate_dataframe_columns(df)

    # Deduplicate rows by Donation ID to handle overlaps
    if "Donation ID" in df.columns:
        df.drop_duplicates(subset=["Donation ID"], keep="first", inplace=True)

    # 4. Pre-compute all derived columns (Donor ID, LTV, Classifications, Payment Frequency)
    df = _enrich_dataframe(df)

    # If appending, merge with existing Parquet cache dataset
    if upload_mode == "append" and os.path.exists(PARQUET_PATH):
        try:
            existing_df = pd.read_parquet(PARQUET_PATH)
            if not existing_df.empty:
                df = pd.concat([existing_df, df], ignore_index=True)
                df = deduplicate_dataframe_columns(df)
                if "Donation ID" in df.columns:
                    df.drop_duplicates(subset=["Donation ID"], keep="first", inplace=True)
                df = _enrich_dataframe(df)
        except Exception as e:
            print(f"Concat append notice: {e}")

    # Ensure clean deduplicated columns before saving
    df = deduplicate_dataframe_columns(df)

    # 5. Save Parquet cache (instant 0.05s loads on every restart)
    df.to_parquet(PARQUET_PATH, index=False)

    # 6. Push to Local SQLite Database
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    df.to_sql("donations", con=conn, if_exists="replace", index=False)
    conn.close()
    
    # 6. Push to Cloud Database in non-blocking background thread via high-speed native COPY stream
    if DATABASE_URL and "postgres" in DATABASE_URL:
        def sync_to_cloud_fast(data_df, mode):
            import io, psycopg2
            try:
                t0 = time.time()
                buf = io.StringIO()
                data_df.to_csv(buf, index=False, header=False, sep='\t', na_rep='')
                buf.seek(0)
                
                conn = psycopg2.connect(DATABASE_URL)
                cur = conn.cursor()
                
                cols_def = ', '.join([f'"{c}" TEXT' for c in data_df.columns])
                cur.execute(f'CREATE TABLE IF NOT EXISTS "donations" ({cols_def});')
                if mode == "replace":
                    cur.execute('TRUNCATE TABLE "donations";')
                conn.commit()
                
                target_cols = ', '.join([f'"{c}"' for c in data_df.columns])
                copy_sql = f'COPY "donations" ({target_cols}) FROM STDIN WITH (FORMAT csv, DELIMITER \'\t\', NULL \'\');'
                cur.copy_expert(sql=copy_sql, file=buf)
                conn.commit()
                cur.close()
                conn.close()
                elapsed = time.time() - t0
                _write_sync_status(True, f"upload ({mode})", "")
                print(f"✅ Supabase Cloud PostgreSQL native COPY complete in {elapsed:.2f}s!")
            except Exception as e:
                _write_sync_status(False, f"upload ({mode})", str(e))
                print(f"Cloud DB sync notice: {e}")
                
        threading.Thread(target=sync_to_cloud_fast, args=(df, upload_mode), daemon=True).start()
    
    # 7. Clear Streamlit cache
    st.cache_data.clear()
    st.cache_resource.clear()
    return len(df)

def apply_custom_css():
    """
    Inject modern glassmorphism and card CSS into Streamlit.
    """
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }
        
        /* Premium Gradient Headers */
        h1, h2, h3 {
            background: linear-gradient(135deg, #F8FAFC 0%, #E2E8F0 50%, #3B82F6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800 !important;
            letter-spacing: -0.02em;
        }

        /* Sleek Persistent Tab Navigation Bar */
        div[data-testid="stRadio"] > div[role="radiogroup"] {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            background: rgba(15, 23, 42, 0.7);
            padding: 8px 12px;
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            margin-bottom: 20px;
        }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label {
            background: rgba(255, 255, 255, 0.03) !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            border-radius: 10px !important;
            padding: 8px 16px !important;
            color: #94A3B8 !important;
            font-weight: 600 !important;
            cursor: pointer;
            transition: all 0.2s ease-in-out !important;
            margin: 0 !important;
        }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label:hover {
            background: rgba(255, 255, 255, 0.08) !important;
            color: #F8FAFC !important;
            border-color: rgba(56, 189, 248, 0.4) !important;
        }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label[data-checked="true"] {
            background: linear-gradient(135deg, #0EA5E9 0%, #6366F1 100%) !important;
            color: #FFFFFF !important;
            font-weight: 700 !important;
            border-color: rgba(56, 189, 248, 0.8) !important;
            box-shadow: 0 4px 14px rgba(14, 165, 233, 0.4) !important;
        }

        /* Glassmorphic Metric Cards with Neon Glow */
        .metric-card {
            background: linear-gradient(145deg, rgba(30, 41, 59, 0.75), rgba(15, 23, 42, 0.95));
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 20px 22px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            text-align: left;
            margin-bottom: 16px;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            position: relative;
            overflow: hidden;
        }
        
        .metric-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 2px;
            background: linear-gradient(90deg, #3B82F6, #8B5CF6, #10B981);
            opacity: 0.8;
        }

        .metric-card:hover {
            transform: translateY(-4px);
            border-color: rgba(59, 130, 246, 0.6);
            box-shadow: 0 14px 40px 0 rgba(59, 130, 246, 0.25), 0 0 20px 0 rgba(16, 185, 129, 0.15);
        }
        
        .metric-label {
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #94A3B8;
            margin-bottom: 6px;
            font-weight: 700;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .metric-value {
            font-size: 1.85rem;
            font-weight: 800;
            color: #F8FAFC;
            margin-bottom: 4px;
            letter-spacing: -0.03em;
        }

        .metric-sub {
            font-size: 0.82rem;
            color: #64748B;
            font-weight: 500;
        }

        /* Glass Content Containers */
        .glass-panel {
            background: linear-gradient(145deg, rgba(30, 41, 59, 0.5), rgba(15, 23, 42, 0.7));
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
        }
        
        .header-badge {
            background: linear-gradient(90deg, #3B82F6 0%, #8B5CF6 100%);
            color: white;
            padding: 5px 14px;
            border-radius: 30px;
            font-size: 0.72rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            display: inline-block;
            margin-bottom: 10px;
            box-shadow: 0 4px 15px rgba(139, 92, 246, 0.35);
        }
        
        /* Custom Tab Bar Styling */
        button[data-baseweb="tab"] {
            border-radius: 12px !important;
            padding: 10px 20px !important;
            font-weight: 700 !important;
            font-size: 0.9rem !important;
            color: #94A3B8 !important;
            background-color: transparent !important;
            border: 1px solid transparent !important;
            transition: all 0.2s ease-in-out !important;
        }
        
        button[data-baseweb="tab"]:hover {
            color: #F8FAFC !important;
            background-color: rgba(255, 255, 255, 0.05) !important;
        }
        
        button[aria-selected="true"] {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(139, 92, 246, 0.25)) !important;
            border: 1px solid rgba(139, 92, 246, 0.4) !important;
            color: #F8FAFC !important;
            box-shadow: 0 4px 20px rgba(59, 130, 246, 0.25) !important;
        }
        
        /* Divider */
        .custom-divider {
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent);
            margin: 1.5rem 0;
            border: none;
        }
        
        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0F172A 0%, #090D16 100%) !important;
            border-right: 1px solid rgba(255, 255, 255, 0.07);
        }
        
        /* Custom Tier Cards for LTV Tab */
        .tier-card {
            background: rgba(30, 41, 59, 0.6);
            border-radius: 14px;
            padding: 16px;
            border-left: 4px solid #3B82F6;
            margin-bottom: 12px;
            transition: transform 0.2s;
        }
        .tier-card:hover {
            transform: translateX(4px);
        }
        .tier-card.tier-low { border-left-color: #3B82F6; }
        .tier-card.tier-medlow { border-left-color: #10B981; }
        .tier-card.tier-med { border-left-color: #F59E0B; }
        .tier-card.tier-high { border-left-color: #F97316; }
        .tier-card.tier-super { border-left-color: #EC4899; }
        
        /* Streamlit Input Enhancements */
        div[data-baseweb="select"] > div {
            background-color: rgba(30, 41, 59, 0.8) !important;
            border-color: rgba(255, 255, 255, 0.1) !important;
            border-radius: 10px !important;
        }

        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

def format_currency(val):
    if pd.isna(val) or val is None:
        return "$0"
    if val >= 1_000_000:
        return f"${val / 1_000_000:.2f}M"
    elif val >= 1_000:
        return f"${val / 1_000:.1f}K"
    else:
        return f"${val:,.2f}"

def format_number(val):
    if pd.isna(val) or val is None:
        return "0"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.2f}M"
    elif val >= 1_000:
        return f"{val / 1_000:.1f}K"
    else:
        return f"{val:,.0f}"

PLOTLY_COLORS = [
    "#06B6D4", # Cyan
    "#8B5CF6", # Purple
    "#10B981", # Emerald
    "#EC4899", # Pink
    "#F59E0B", # Amber
    "#3B82F6", # Blue
    "#14B8A6", # Teal
    "#F43F5E", # Rose
    "#84CC16", # Lime
    "#6366F1"  # Indigo
]

DONOR_TIER_ORDER = [
    "Low End",
    "Medium Low",
    "Medium",
    "High",
    "Super High"
]
