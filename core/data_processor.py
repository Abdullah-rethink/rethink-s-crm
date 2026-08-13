import os
import sqlite3
import threading
from typing import Optional

import pandas as pd
import streamlit as st

from config.settings import LOCAL_DB_PATH, PARQUET_PATH
from core.database import sync_to_cloud_async

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

# Global In-Memory Dataset Cache Singleton
_CACHED_DF: Optional[pd.DataFrame] = None
_CACHE_MTIME: float = 0.0
_CACHE_LOCK = threading.Lock()



def fix_mojibake(text):
    """
    Fixes garbled text encodings (UTF-8 bytes mis-decoded as Windows-1252 / ISO-8859-1).
    Restores multi-lingual characters, Arabic, accents, and special symbols.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    try:
        import ftfy
        return ftfy.fix_text(text)
    except Exception:
        return text

def deduplicate_dataframe_columns(df_input):
    """
    Finds and merges duplicate columns case-insensitively.
    """
    if df_input.empty:
        return df_input
    
    seen = {}
    col_map = {}
    for col in df_input.columns:
        norm = str(col).strip().lower()
        if norm in seen:
            col_map[col] = seen[norm]
        else:
            seen[norm] = col

    if len(col_map) == 0:
        return df_input

    res_df = pd.DataFrame(index=df_input.index)
    for original_col in seen.values():
        res_df[original_col] = df_input[original_col]
        
    for dup_col, primary_col in col_map.items():
        res_df[primary_col] = res_df[primary_col].fillna(df_input[dup_col])
        
    return res_df

# Global In-Memory Code Map Cache
_CACHED_CODE_MAP = None


def get_code_to_classification_map(force_reload: bool = False):
    """
    Queries all known classifications from campaign, givebright, and paysuite classification tables
    to build a dynamic dictionary mapping a Code (case-insensitive) to its corresponding
    Heading, Sub-Heading, Country, and Zakat Eligibility in < 1ms via in-memory caching.
    """
    global _CACHED_CODE_MAP
    if not force_reload and _CACHED_CODE_MAP is not None:
        return _CACHED_CODE_MAP

    code_map = {}
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        tables = ["campaign_classifications", "givebright_classifications", "paysuite_classifications", "rethink_website_classifications"]
        for tbl in tables:
            try:
                df = pd.read_sql_query(f"SELECT code, heading, sub_heading, country, zakat_eligibility FROM {tbl}", conn)
                for _, row in df.iterrows():
                    code = str(row.get("code") or "").strip()
                    code_lower = code.lower()
                    if not code or code_lower in ["unassigned", "nan", "none", ""]:
                        continue
                    
                    heading = str(row.get("heading") or "").strip()
                    sub_heading = str(row.get("sub_heading") or "").strip()
                    country = str(row.get("country") or "").strip()
                    zakat = str(row.get("zakat_eligibility") or "").strip()

                    if (heading.lower() in ["unassigned", ""] and 
                        sub_heading.lower() in ["unassigned", ""] and 
                        country.lower() in ["unassigned", ""]):
                        continue

                    code_lower_clean = code.strip().lower()

                    if code_lower_clean not in code_map:
                        code_map[code_lower_clean] = {
                            "Heading": heading if heading.lower() not in ["unassigned", ""] else "Unassigned",
                            "Sub-Heading": sub_heading if sub_heading.lower() not in ["unassigned", ""] else "Unassigned",
                            "Country": country if country.lower() not in ["unassigned", ""] else "Unassigned",
                            "Zakat Eligibility": zakat if zakat.lower() not in ["unassigned", ""] else "Unassigned"
                        }
            except Exception:
                pass
    finally:
        conn.close()

    _CACHED_CODE_MAP = code_map
    return _CACHED_CODE_MAP


def classify_donor_amount(amount):
    """Classify donor based on donation amount."""
    if pd.isna(amount) or amount is None:
        return "Low End"
    try:
        val = float(amount)
    except (ValueError, TypeError):
        return "Low End"

    if val < 200:
        return "Low End"
    elif val < 600:
        return "Medium Low"
    elif val < 1000:
        return "Medium"
    elif val <= 3000:
        return "High"
    else:
        return "Super High"

def _mode_or_last(series):
    clean = series.dropna().astype(str).str.strip()
    clean = clean[clean != ""]
    if clean.empty:
        return series.iloc[-1] if not series.empty else 'Unassigned'
    mode_vals = clean.mode()
    return mode_vals.iloc[0] if not mode_vals.empty else clean.iloc[-1]

def init_classification_db():
    """Ensure SQLite campaign_classifications, paysuite_classifications, and sponsorship_targets tables exist."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_classifications (
                campaign_name TEXT PRIMARY KEY,
                community_name TEXT,
                campaign_url TEXT DEFAULT '',
                heading TEXT DEFAULT 'Unassigned',
                sub_heading TEXT DEFAULT 'Unassigned',
                country TEXT DEFAULT 'Unassigned',
                code TEXT DEFAULT 'Unassigned',
                zakat_eligibility TEXT DEFAULT 'Unassigned'
            );
        """)
        try:
            conn.execute("ALTER TABLE campaign_classifications ADD COLUMN campaign_url TEXT DEFAULT '';")
            conn.commit()
        except Exception:
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS paysuite_classifications (
                campaign_name TEXT PRIMARY KEY,
                community_name TEXT,
                heading TEXT DEFAULT 'Unassigned',
                sub_heading TEXT DEFAULT 'Unassigned',
                country TEXT DEFAULT 'Unassigned',
                code TEXT DEFAULT 'Unassigned',
                zakat_eligibility TEXT DEFAULT 'Unassigned',
                donor_name TEXT DEFAULT '',
                donor_email TEXT DEFAULT ''
            );
        """)
        try:
            conn.execute("ALTER TABLE paysuite_classifications ADD COLUMN donor_name TEXT DEFAULT '';")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE paysuite_classifications ADD COLUMN donor_email TEXT DEFAULT '';")
        except Exception:
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS rethink_website_classifications (
                campaign_name TEXT PRIMARY KEY,
                community_name TEXT DEFAULT 'N/A',
                heading TEXT DEFAULT 'Unassigned',
                sub_heading TEXT DEFAULT 'Unassigned',
                country TEXT DEFAULT 'Unassigned',
                code TEXT DEFAULT 'Unassigned',
                zakat_eligibility TEXT DEFAULT 'Unassigned'
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sponsorship_targets (
                sponsorship_type TEXT PRIMARY KEY,
                target_value REAL
            );
        """)
        # Seed default target values if not exists
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM sponsorship_targets")
        if cur.fetchone()[0] == 0:
            conn.executemany("""
                INSERT INTO sponsorship_targets (sponsorship_type, target_value)
                VALUES (?, ?)
            """, [
                ("Hafiz", 240.0),
                ("Orphan", 480.0),
                ("Widow", 1080.0),
                ("Ex-Prisoner", 1080.0)
            ])
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Classification DB init notice: {e}")

def get_classification_matrix(df_raw=None):
    """Returns the campaign_classifications matrix DataFrame in < 50ms using vectorized SQLite + in-memory lookup."""
    init_classification_db()
    target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]

    # 1. Read existing saved rules directly from SQLite
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        db_matrix = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(campaign_url, '') as "Campaign URL",
                COALESCE(community_name, 'N/A') as "Community Name",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility"
            FROM campaign_classifications
        """, conn)
    except Exception:
        db_matrix = pd.DataFrame(columns=["Campaign Name", "Campaign URL", "Community Name"] + target_cols)
    finally:
        conn.close()

    # 2. Extract distinct campaigns from in-memory cached donations via DuckDB (< 20ms)
    donor_distinct = None
    try:
        from core.analytics_engine import get_duckdb_connection
        con = get_duckdb_connection()
        if con and os.path.exists(PARQUET_PATH):
            donor_distinct = con.execute(f"""
                SELECT DISTINCT
                    COALESCE(NULLIF(TRIM("Campaign Name"), ''), 'N/A') as "Campaign Name",
                    COALESCE(NULLIF(TRIM("Community Name"), ''), 'N/A') as "Community Name"
                FROM '{PARQUET_PATH.replace(chr(92), '/')}'
                WHERE LOWER(COALESCE("Platform", '')) NOT IN ('givebright', 'paysuite')
                  AND "Campaign Name" IS NOT NULL
            """).df()
    except Exception as e:
        print(f"[DuckDB matrix notice]: {e}")
        donor_distinct = None

    if donor_distinct is None or donor_distinct.empty:
        df_donations = df_raw if (df_raw is not None and not df_raw.empty) else load_data()
        if df_donations is not None and not df_donations.empty and "Campaign Name" in df_donations.columns:
            plat_series = df_donations.get("Platform", pd.Series("", index=df_donations.index)).astype(str).str.lower()
            lg_mask = ~plat_series.isin(["givebright", "paysuite"])
            lg_df = df_donations[lg_mask] if lg_mask.any() else df_donations.iloc[0:0]

            if not lg_df.empty:
                c_name = lg_df["Campaign Name"].astype(str).str.strip()
                c_name = c_name[~c_name.str.lower().isin(['nan', 'none', 'n/a', '', 'unassigned'])]
                comm_name = lg_df.loc[c_name.index, "Community Name"].astype(str).str.strip().replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'}) if "Community Name" in lg_df.columns else pd.Series("N/A", index=c_name.index)
                donor_df = pd.DataFrame({"Campaign Name": c_name, "Community Name": comm_name})
                donor_distinct = donor_df.drop_duplicates(subset=["Campaign Name", "Community Name"])

    if donor_distinct is not None and not donor_distinct.empty:
        if db_matrix.empty:
            matrix_df = donor_distinct.fillna("Unassigned").reset_index(drop=True)
        else:
            merged = pd.merge(
                donor_distinct[["Campaign Name", "Community Name"]],
                db_matrix,
                on=["Campaign Name", "Community Name"],
                how="outer"
            ).fillna("Unassigned")
            matrix_df = merged.drop_duplicates(subset=["Campaign Name", "Community Name"]).reset_index(drop=True)
    else:
        matrix_df = db_matrix


    # Dynamic auto-assignment based on Code mapping in < 5ms
    code_map = get_code_to_classification_map()
    if code_map and "Code" in matrix_df.columns:
        code_clean = matrix_df["Code"].astype(str).str.strip().str.lower()
        for tc in ["Heading", "Sub-Heading", "Country", "Zakat Eligibility"]:
            if tc in matrix_df.columns:
                target_map = {k: v[tc] for k, v in code_map.items() if tc in v and v[tc] != "Unassigned"}
                mask_unassigned = matrix_df[tc].astype(str).str.strip().str.lower().isin(["", "unassigned", "nan", "none"])
                mapped_vals = code_clean.map(target_map)
                fill_mask = mask_unassigned & mapped_vals.notna()
                if fill_mask.any():
                    matrix_df.loc[fill_mask, tc] = mapped_vals[fill_mask]

    return matrix_df



def sanitize_df_dtypes_for_parquet(df):
    """Sanitizes object/date/datetime/ID columns to string format and eliminates case-insensitive duplicate columns."""
    if df is None or df.empty:
        return df
    
    # 1. Eliminate case-insensitive duplicate columns (e.g. 'title' vs 'Title')
    df = deduplicate_dataframe_columns(df)
    
    # 2. Sanitize column dtypes for PyArrow and SQLite compatibility
    for col in df.columns:
        if df[col].dtype == 'object' or col in ["Created Date (UTC)", "Created Time (UTC)", "Date", "Time", "Donation ID", "Donor ID"]:
            df[col] = df[col].astype(str).replace({'nan': '', 'None': '', 'NaN': '', '<NA>': '', 'NaT': ''})
            
    return df


def sync_donors_to_classification_matrix(df_raw=None):
    """
    Synchronizes updated classifications (Code, Heading, Sub-Heading, Country, Zakat Eligibility)
    from active donor transactions into SQLite classification matrix tables
    (campaign_classifications, givebright_classifications, paysuite_classifications, rethink_website_classifications).
    Ensures that when donor records are edited, the classification matrix is immediately updated.
    """
    global _CACHED_CODE_MAP
    _CACHED_CODE_MAP = None  # Invalidate cached code map
    
    init_classification_db()
    df = df_raw if (df_raw is not None and not df_raw.empty) else load_data()
    if df.empty or "Campaign Name" not in df.columns:
        return 0

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    synced_total = 0

    # Ensure all target columns exist defensively
    for col_def, default_val in [
        ("Community Name", "N/A"),
        ("Campaign URL", ""),
        ("Heading", "Unassigned"),
        ("Sub-Heading", "Unassigned"),
        ("Country", "Unassigned"),
        ("Code", "Unassigned"),
        ("Zakat Eligibility", "Unassigned"),
        ("First Name", ""),
        ("Last Name", ""),
        ("Email", "")
    ]:
        if col_def not in df.columns:
            df[col_def] = default_val

    try:
        platform_s = df.get("Platform", pd.Series("", index=df.index)).astype(str).str.lower()
        source_s = df.get("Source", pd.Series("", index=df.index)).astype(str).str.lower()

        # Partition Platform Masks strictly
        ws_mask = platform_s.isin(["rethink website", "website"]) | source_s.str.contains("rethink|website", na=False)
        gb_mask = platform_s.isin(["givebright"]) | source_s.str.contains("givebright|give_bright", na=False)
        ps_mask = platform_s.isin(["paysuite"]) | source_s.str.contains("paysuite", na=False)
        lg_mask = (~ws_mask) & (~gb_mask) & (~ps_mask)

        # 1. Sync LaunchGood Campaigns
        lg_df = df[lg_mask]
        if not lg_df.empty:
            lg_grouped = lg_df.groupby("Campaign Name", as_index=False).agg({
                "Community Name": "first" if "Community Name" in lg_df.columns else lambda x: "N/A",
                "Campaign URL": "first" if "Campaign URL" in lg_df.columns else lambda x: "",
                "Heading": "last",
                "Sub-Heading": "last",
                "Country": "last",
                "Code": "last",
                "Zakat Eligibility": "last"
            })
            for _, r in lg_grouped.iterrows():
                cname = str(r["Campaign Name"]).strip()
                if not cname or cname.lower() in ["nan", "none", "n/a", ""]:
                    continue
                comm = str(r.get("Community Name") or "N/A").strip()
                curl = str(r.get("Campaign URL") or "").strip()
                code = str(r.get("Code") or "Unassigned").strip()
                heading = str(r.get("Heading") or "Unassigned").strip()
                subheading = str(r.get("Sub-Heading") or "Unassigned").strip()
                country = str(r.get("Country") or "Unassigned").strip()
                zakat = str(r.get("Zakat Eligibility") or "Unassigned").strip()

                cursor.execute("""
                    UPDATE campaign_classifications 
                    SET community_name = ?, campaign_url = COALESCE(NULLIF(?, ''), campaign_url), heading = ?, sub_heading = ?, country = ?, code = ?, zakat_eligibility = ?
                    WHERE campaign_name = ?
                """, (comm, curl, heading, subheading, country, code, zakat, cname))
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO campaign_classifications (campaign_name, community_name, campaign_url, heading, sub_heading, country, code, zakat_eligibility)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (cname, comm, curl, heading, subheading, country, code, zakat))
                synced_total += 1

        # 2. Sync GiveBright Campaigns
        gb_df = df[gb_mask]
        if not gb_df.empty:
            gb_grouped = gb_df.groupby("Campaign Name", as_index=False).agg({
                "Campaign URL": "first" if "Campaign URL" in gb_df.columns else lambda x: "",
                "Heading": "last",
                "Sub-Heading": "last",
                "Country": "last",
                "Code": "last",
                "Zakat Eligibility": "last"
            })
            new_gb_rules = []
            for _, r in gb_grouped.iterrows():
                cname = str(r["Campaign Name"]).strip()
                if not cname or cname.lower() in ["nan", "none", "n/a", ""]:
                    continue
                curl = str(r.get("Campaign URL") or "").strip()
                code = str(r.get("Code") or "Unassigned").strip()
                heading = str(r.get("Heading") or "Unassigned").strip()
                subheading = str(r.get("Sub-Heading") or "Unassigned").strip()
                country = str(r.get("Country") or "Unassigned").strip()
                zakat = str(r.get("Zakat Eligibility") or "Unassigned").strip()
                new_gb_rules.append((cname, curl, heading, subheading, country, code, zakat))

            if new_gb_rules:
                cursor.executemany("""
                    INSERT OR REPLACE INTO givebright_classifications (campaign_name, campaign_url, heading, sub_heading, country, code, zakat_eligibility)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, new_gb_rules)
                synced_total += len(new_gb_rules)

        # 3. Sync Paysuite Campaigns
        ps_mask = (platform_s == "paysuite") | source_s.str.contains("paysuite", na=False)
        ps_df = df[ps_mask]
        if not ps_df.empty:
            active_ps_cnames = set(str(c).strip() for c in ps_df["Campaign Name"].dropna().unique() if str(c).strip() not in ["", "nan", "none", "n/a"])

            # Prune orphaned rules that do not exist in active donations
            cursor.execute("SELECT campaign_name FROM paysuite_classifications")
            existing_ps = [r[0] for r in cursor.fetchall()]
            to_delete = [r for r in existing_ps if r not in active_ps_cnames]
            for dead_cname in to_delete:
                cursor.execute("DELETE FROM paysuite_classifications WHERE campaign_name = ?", (dead_cname,))

            ps_grouped = ps_df.groupby(["Campaign Name", "Community Name"], as_index=False).agg({
                "Heading": "last",
                "Sub-Heading": "last",
                "Country": "last",
                "Code": "last",
                "Zakat Eligibility": "last",
                "First Name": "last" if "First Name" in ps_df.columns else lambda x: "",
                "Last Name": "last" if "Last Name" in ps_df.columns else lambda x: "",
                "Email": "last" if "Email" in ps_df.columns else lambda x: ""
            })
            for _, r in ps_grouped.iterrows():
                cname = str(r["Campaign Name"]).strip()
                if not cname or cname.lower() in ["nan", "none", "n/a", ""]:
                    continue
                comm = str(r.get("Community Name") or "N/A").strip()
                code = str(r.get("Code") or "Unassigned").strip()
                heading = str(r.get("Heading") or "Unassigned").strip()
                subheading = str(r.get("Sub-Heading") or "Unassigned").strip()
                country = str(r.get("Country") or "Unassigned").strip()
                zakat = str(r.get("Zakat Eligibility") or "Unassigned").strip()
                fname = str(r.get("First Name") or "").strip()
                lname = str(r.get("Last Name") or "").strip()
                donor_name = f"{fname} {lname}".strip()
                donor_email = str(r.get("Email") or "").strip()

                cursor.execute("""
                    UPDATE paysuite_classifications 
                    SET community_name = ?, heading = ?, sub_heading = ?, country = ?, code = ?, zakat_eligibility = ?, donor_name = ?, donor_email = ?
                    WHERE campaign_name = ?
                """, (comm, heading, subheading, country, code, zakat, donor_name, donor_email, cname))
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO paysuite_classifications (campaign_name, community_name, heading, sub_heading, country, code, zakat_eligibility, donor_name, donor_email)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (cname, comm, heading, subheading, country, code, zakat, donor_name, donor_email))
                synced_total += 1

        # 4. Sync Rethink Website Campaigns
        ws_mask = platform_s.str.contains("rethink website|website", regex=True, na=False)
        ws_df = df[ws_mask]
        if not ws_df.empty:
            ws_grouped = ws_df.groupby("Campaign Name", as_index=False).agg({
                "Community Name": "first" if "Community Name" in ws_df.columns else lambda x: "N/A",
                "Heading": "last",
                "Sub-Heading": "last",
                "Country": "last",
                "Code": "last",
                "Zakat Eligibility": "last"
            })
            for _, r in ws_grouped.iterrows():
                cname = str(r["Campaign Name"]).strip()
                if not cname or cname.lower() in ["nan", "none", "n/a", ""]:
                    continue
                comm = str(r.get("Community Name") or "N/A").strip()
                code = str(r.get("Code") or "Unassigned").strip()
                heading = str(r.get("Heading") or "Unassigned").strip()
                subheading = str(r.get("Sub-Heading") or "Unassigned").strip()
                country = str(r.get("Country") or "Unassigned").strip()
                zakat = str(r.get("Zakat Eligibility") or "Unassigned").strip()

                cursor.execute("""
                    UPDATE rethink_website_classifications 
                    SET community_name = ?, heading = ?, sub_heading = ?, country = ?, code = ?, zakat_eligibility = ?
                    WHERE campaign_name = ?
                """, (comm, heading, subheading, country, code, zakat, cname))
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO rethink_website_classifications (campaign_name, community_name, heading, sub_heading, country, code, zakat_eligibility)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (cname, comm, heading, subheading, country, code, zakat))
                synced_total += 1

        conn.commit()
    finally:
        conn.close()

    return synced_total


def sync_matrix_classifications_to_donors(matrix_df):
    """Updates matching donor records in Parquet and SQLite DB with saved classification matrix rules."""
    if matrix_df is None or matrix_df.empty:
        return 0

    df_raw = load_data()
    if df_raw.empty or "Campaign Name" not in df_raw.columns:
        return 0

    updated_count = 0
    rule_map = {}
    for _, row in matrix_df.iterrows():
        cname = str(row.get("Campaign Name", "")).strip().lower()
        if cname and cname not in ["n/a", "none", "nan", ""]:
            rule_map[cname] = {
                "Heading": str(row.get("Heading", "Unassigned")),
                "Sub-Heading": str(row.get("Sub-Heading", "Unassigned")),
                "Country": str(row.get("Country", "Unassigned")),
                "Code": str(row.get("Code", "Unassigned")),
                "Zakat Eligibility": str(row.get("Zakat Eligibility", "Unassigned")),
            }
            if "Campaign URL" in row and str(row.get("Campaign URL") or "").strip():
                rule_map[cname]["Campaign URL"] = str(row.get("Campaign URL")).strip()

    if not rule_map:
        return 0

    campaign_series = df_raw["Campaign Name"].astype(str).str.strip().str.lower()
    for cname, rules in rule_map.items():
        mask = campaign_series == cname
        if mask.any():
            updated_count += int(mask.sum())
            for col_name, col_val in rules.items():
                if col_name in df_raw.columns:
                    df_raw.loc[mask, col_name] = col_val

    df_raw.to_parquet(PARQUET_PATH, index=False)
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    df_raw.to_sql("donations", con=conn, if_exists="replace", index=False)
    conn.close()

    invalidate_data_cache()
    return updated_count


def save_classification_matrix(matrix_df):
    """Saves updated LaunchGood classification matrix."""
    init_classification_db()
    if matrix_df.empty:
        return 0

    clean_matrix = matrix_df.copy()
    clean_matrix["Campaign Name"] = clean_matrix["Campaign Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})
    clean_matrix["Community Name"] = clean_matrix["Community Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    for _, row in clean_matrix.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned"))
        conn.execute("DELETE FROM campaign_classifications WHERE campaign_name = ?", (cname,))
        conn.execute("""
            INSERT INTO campaign_classifications (campaign_name, community_name, campaign_url, heading, sub_heading, country, code, zakat_eligibility)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cname,
            str(row.get("Community Name", "Unassigned")),
            str(row.get("Campaign URL", "") or ""),
            str(row.get("Heading", "Unassigned")),
            str(row.get("Sub-Heading", "Unassigned")),
            str(row.get("Country", "Unassigned")),
            str(row.get("Code", "Unassigned")),
            str(row.get("Zakat Eligibility", "Unassigned"))
        ))
    conn.commit()
    conn.close()
    return len(clean_matrix)



def get_paysuite_classification_matrix(df_raw=None):
    """Returns the paysuite_classifications matrix DataFrame in < 50ms using vectorized SQLite + in-memory lookup."""
    init_classification_db()
    target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        db_matrix = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(community_name, 'N/A') as "Community Name",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility",
                COALESCE(donor_name, '') as "Donor Name",
                COALESCE(donor_email, '') as "Donor Email"
            FROM paysuite_classifications
        """, conn)
    except Exception:
        db_matrix = pd.DataFrame(columns=["Campaign Name", "Community Name"] + target_cols + ["Donor Name", "Donor Email"])
    finally:
        conn.close()

    df_donations = df_raw if (df_raw is not None and not df_raw.empty) else load_data()
    if df_donations is not None and not df_donations.empty and "Campaign Name" in df_donations.columns:
        platform_s = df_donations.get("Platform", pd.Series("", index=df_donations.index)).astype(str).str.lower()
        source_s = df_donations.get("Source", pd.Series("", index=df_donations.index)).astype(str).str.lower()
        ps_mask = (platform_s == "paysuite") | source_s.str.contains("paysuite", na=False)
        ps_df = df_donations[ps_mask] if ps_mask.any() else df_donations.iloc[0:0]

        if not ps_df.empty:
            c_name = ps_df["Campaign Name"].astype(str).str.strip()
            c_name = c_name[~c_name.str.lower().isin(['nan', 'none', 'n/a', '', 'unassigned'])]
            comm_name = ps_df.loc[c_name.index, "Community Name"].astype(str).str.strip().replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'}) if "Community Name" in ps_df.columns else pd.Series("N/A", index=c_name.index)
            
            donor_df = pd.DataFrame({"Campaign Name": c_name, "Community Name": comm_name})
            for tc in target_cols:
                if tc in ps_df.columns:
                    donor_df[tc] = ps_df.loc[c_name.index, tc].values

            donor_distinct = donor_df.drop_duplicates(subset=["Campaign Name", "Community Name"])

            if db_matrix.empty:
                return donor_distinct.fillna("Unassigned").reset_index(drop=True)

            merged = pd.merge(
                donor_distinct[["Campaign Name", "Community Name"]],
                db_matrix,
                on=["Campaign Name", "Community Name"],
                how="outer"
            ).fillna("Unassigned")
            return merged.drop_duplicates(subset=["Campaign Name", "Community Name"]).reset_index(drop=True)

    if not db_matrix.empty:
        return db_matrix.fillna("Unassigned").reset_index(drop=True)

    return pd.DataFrame(columns=["Campaign Name", "Community Name"] + target_cols)



def save_paysuite_classification_matrix(matrix_df):
    """Saves updated Paysuite classification matrix to SQLite."""
    init_classification_db()
    if matrix_df.empty:
        return 0
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    for _, row in matrix_df.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned"))
        conn.execute("DELETE FROM paysuite_classifications WHERE campaign_name = ?", (cname,))
        conn.execute("""
            INSERT INTO paysuite_classifications (campaign_name, community_name, heading, sub_heading, country, code, zakat_eligibility)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cname,
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


def get_rethink_website_classification_matrix(df_raw=None):
    """Returns the rethink_website_classifications matrix DataFrame in < 50ms."""
    init_classification_db()
    target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        db_matrix = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(community_name, 'N/A') as "Community Name",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility"
            FROM rethink_website_classifications
        """, conn)
    except Exception:
        db_matrix = pd.DataFrame(columns=["Campaign Name", "Community Name"] + target_cols)
    finally:
        conn.close()

    df_donations = df_raw if (df_raw is not None and not df_raw.empty) else load_data()
    if df_donations is not None and not df_donations.empty and "Campaign Name" in df_donations.columns:
        platform_s = df_donations.get("Platform", pd.Series("", index=df_donations.index)).astype(str).str.lower()
        ws_mask = platform_s.str.contains("rethink website|website", regex=True, na=False)
        ws_df = df_donations[ws_mask] if ws_mask.any() else df_donations.iloc[0:0]

        if not ws_df.empty:
            c_name = ws_df["Campaign Name"].astype(str).str.strip()
            c_name = c_name[~c_name.str.lower().isin(['nan', 'none', 'n/a', '', 'unassigned'])]
            comm_name = ws_df.loc[c_name.index, "Community Name"].astype(str).str.strip().replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'}) if "Community Name" in ws_df.columns else pd.Series("N/A", index=c_name.index)
            
            donor_df = pd.DataFrame({"Campaign Name": c_name, "Community Name": comm_name})
            for tc in target_cols:
                if tc in ws_df.columns:
                    donor_df[tc] = ws_df.loc[c_name.index, tc].values

            donor_distinct = donor_df.drop_duplicates(subset=["Campaign Name", "Community Name"])

            if db_matrix.empty:
                return donor_distinct.fillna("Unassigned").reset_index(drop=True)

            merged = pd.merge(
                donor_distinct[["Campaign Name", "Community Name"]],
                db_matrix,
                on=["Campaign Name", "Community Name"],
                how="outer"
            ).fillna("Unassigned")
            return merged.drop_duplicates(subset=["Campaign Name", "Community Name"]).reset_index(drop=True)

    if not db_matrix.empty:
        return db_matrix.fillna("Unassigned").reset_index(drop=True)

    return pd.DataFrame(columns=["Campaign Name", "Community Name"] + target_cols)


def save_rethink_website_classification_matrix(matrix_df):
    """Saves updated Rethink Website classification matrix to SQLite."""
    init_classification_db()
    if matrix_df.empty:
        return 0
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    for _, row in matrix_df.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned")).strip()
        if not cname or cname.lower() in ["nan", "none", "n/a", ""]:
            continue
        conn.execute("DELETE FROM rethink_website_classifications WHERE campaign_name = ?", (cname,))
        conn.execute("""
            INSERT INTO rethink_website_classifications (campaign_name, community_name, heading, sub_heading, country, code, zakat_eligibility)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cname,
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


def _enrich_dataframe(df, platform="auto"):
    """Pre-compute all derived columns (Donor ID, LTV, Classification, Payment Frequency) and apply classifications."""
    # 1. Platform Detection & Standardization
    is_paysuite = "Bank Ref" in df.columns and "Date of collection" in df.columns
    is_rethink_website = ("Reference" in df.columns and "Donor First Name" in df.columns and ("Project Name" in df.columns or "Processor" in df.columns)) or (str(platform).lower() in ["rethink website", "website", "rethink_website"])
    is_givebright = False
    
    if not is_paysuite and not is_rethink_website:
        if str(platform).lower() == "givebright":
            is_givebright = True
        elif str(platform).lower() in ["auto", "none", ""]:
            gb_sig = {"donation_id", "campaign_name", "fundraiser_by", "fundraiser_name", "campaign_url", "charge_id", "payment_method_type"}
            if len(gb_sig.intersection(set(df.columns))) >= 2:
                is_givebright = True

    if is_paysuite:
        # Classroom rethink village mapping
        if "Code" in df.columns:
            df["Code"] = df["Code"].astype(str).str.strip().replace({
                "classroom rethink village": "SYR-VIL-SCH",
                "classroom rethink village, Rethink Village": "SYR-VIL-SCH",
                "CLASSROOM !!!, Rethink Village": "SYR-VIL-SCH",
                "CLASSROOM !!!": "SYR-VIL-SCH"
            })

        # Rename standard columns
        df = df.rename(columns={
            "Bank Ref": "Donation ID",
            "Firstname": "First Name",
            "Surname": "Last Name",
            "Email": "Email",
            "Comments": "Comments",
            "Address": "Billing Address",
            "Post code": "Billing Zip",
        })

        if "Amount" in df.columns:
            df["Total Online Donations Net Amount in Settled Currency"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
            df["Donation Amount in Project Currency (May be approx.)"] = df["Total Online Donations Net Amount in Settled Currency"]
            df["Donation Amount (in Donation Currency)"] = df["Total Online Donations Net Amount in Settled Currency"]

        if "Date of collection" in df.columns:
            parsed_dates = pd.to_datetime(df["Date of collection"], dayfirst=True, errors="coerce")
            df["Created Date (UTC)"] = parsed_dates
            df["Created Time (UTC)"] = "00:00:00"

        if "Type" in df.columns:
            df["Payment Frequency"] = df["Type"].apply(lambda t: "Recurring Payment" if str(t).lower() == "regular" else "One-Time Payment")

        df["Platform"] = "Paysuite"
        df["Payment Type"] = "Direct Debit"
        df["Offline or online donation"] = "online"
        
        df["Campaign Name"] = df["Donation ID"]
        df["Community Name"] = "Paysuite"

        # Try to look up existing donor details (Email, Billing Address, Billing Zip) and classifications from database by Bank Ref
        existing_map = {}
        df_existing = load_data()
        if not df_existing.empty and "Donation ID" in df_existing.columns:
            ps_existing = df_existing[df_existing.get("Platform", pd.Series("", index=df_existing.index)).astype(str).str.lower() == "paysuite"]
            if not ps_existing.empty:
                mapping_df = ps_existing.drop_duplicates(subset=["Donation ID"], keep="last")
                for _, r in mapping_df.iterrows():
                    existing_map[str(r["Donation ID"]).strip().lower()] = {
                        "Email": r.get("Email") if pd.notna(r.get("Email")) else None,
                        "Billing Address": r.get("Billing Address") if pd.notna(r.get("Billing Address")) else None,
                        "Billing Zip": r.get("Billing Zip") if pd.notna(r.get("Billing Zip")) else None,
                        "Heading": r.get("Heading") if pd.notna(r.get("Heading")) else "Unassigned",
                        "Sub-Heading": r.get("Sub-Heading") if pd.notna(r.get("Sub-Heading")) else "Unassigned",
                        "Country": r.get("Country") if pd.notna(r.get("Country")) else "Unassigned",
                        "Code": r.get("Code") if pd.notna(r.get("Code")) else "Unassigned",
                        "Zakat Eligibility": r.get("Zakat Eligibility") if pd.notna(r.get("Zakat Eligibility")) else "Unassigned",
                    }

        # Apply or initialize classifications database for Paysuite
        init_classification_db()
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        try:
            db_matrix = pd.read_sql_query("SELECT * FROM paysuite_classifications", conn)
            rule_dict = {str(r["campaign_name"]).strip().lower(): r for _, r in db_matrix.iterrows()}
        except Exception:
            rule_dict = {}
        finally:
            conn.close()

        for col in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
            if col not in df.columns:
                df[col] = "Unassigned"

        bank_ref_lower = df["Donation ID"].astype(str).str.strip().str.lower()

        # Vectorized classification lookup from paysuite_classifications (< 5ms)
        for f in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
            db_f = f.lower().replace("-", "_").replace(" ", "_")
            mapped_vals = bank_ref_lower.map(lambda b: rule_dict.get(b, {}).get(db_f))
            valid_mask = mapped_vals.notna() & (~mapped_vals.astype(str).str.lower().isin(["", "nan", "none", "unassigned"]))
            if valid_mask.any():
                df.loc[valid_mask, f] = mapped_vals[valid_mask]

        # Seed new Paysuite bank refs into paysuite_classifications database in 1 vectorized pass
        unique_refs = df[["Donation ID", "Code", "Customer Ref"]].drop_duplicates(subset=["Donation ID"])
        new_rules = []
        for _, r in unique_refs.iterrows():
            b_ref = str(r["Donation ID"]).strip()
            b_ref_l = b_ref.lower()
            if b_ref and b_ref_l not in ["nan", "none", "n/a", ""] and b_ref_l not in rule_dict:
                c_code = str(r.get("Code") or "Unassigned").strip()
                if not c_code or c_code.lower() in ["nan", "none"]:
                    c_code = "Unassigned"
                if "hafiz" in str(r.get("Customer Ref") or "").lower():
                    c_code = "SYR-SPN-HUF"
                new_rules.append((b_ref, "Paysuite", "Unassigned", "Unassigned", "Unassigned", c_code, "Unassigned"))

        if new_rules:
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            try:
                conn.executemany("""
                    INSERT OR REPLACE INTO paysuite_classifications (campaign_name, community_name, heading, sub_heading, country, code, zakat_eligibility)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, new_rules)
                conn.commit()
            except Exception as e:
                print(f"Error seeding new paysuite rules: {e}")
            finally:
                conn.close()

    elif is_rethink_website:
        df["Platform"] = "Rethink Website"
        df["Payment Type"] = "Card / Stripe"
        df["Offline or online donation"] = "online"

        col_map = {
            "Reference": "Donation ID",
            "Donor First Name": "First Name",
            "Donor Last Name": "Last Name",
            "Donor Email": "Email",
            "Donor Phone": "Phone Number",
            "Donor Address Street 1": "Billing Address",
            "Donor Address Street 2": "Billing Address 2",
            "Donor Address City": "Billing City",
            "Donor Address Region": "Billing State",
            "Donor Address Postal Code": "Billing Zip",
            "Project Name": "Campaign Name",
            "Appeal Name": "Community Name",
            "Location": "Country",
            "Fees": "fee_amount",
            "Gross Amount": "Total Online Donation Gross Amount in Settled Currency",
            "Words of Support": "comment",
            "Processor": "gateway"
        }
        df.rename(columns=col_map, inplace=True)

        if "Amount" in df.columns:
            df["Total Online Donations Net Amount in Settled Currency"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
            df["Donation Amount in Project Currency (May be approx.)"] = df["Total Online Donations Net Amount in Settled Currency"]
            df["Donation Amount (in Donation Currency)"] = df["Total Online Donations Net Amount in Settled Currency"]

        if "Currency" in df.columns:
            df["Donation Currency (DC)"] = df["Currency"]
            df["Settlement Currency"] = df["Currency"]

        if "Subscription Reference" in df.columns:
            df["Payment Frequency"] = df["Subscription Reference"].apply(
                lambda s: "Recurring Payment" if pd.notna(s) and str(s).strip() not in ["", "nan", "None"] else "One-Time Payment"
            )
        else:
            df["Payment Frequency"] = "One-Time Payment"

        if "Gift Aid?" in df.columns:
            df["Gift Aid (yes or no)"] = df["Gift Aid?"].apply(
                lambda g: "Yes" if str(g).strip() in ["1", "true", "yes"] else "No"
            )

        if "Anonymous?" in df.columns:
            df["Anonymous or Public"] = df["Anonymous?"].apply(
                lambda a: "Anonymous" if str(a).strip() in ["1", "true", "yes"] else "Public"
            )

        if "Zakat Status" in df.columns and "Zakat Eligibility" not in df.columns:
            df["Zakat Eligibility"] = df["Zakat Status"].apply(
                lambda z: "Zakat" if str(z).strip().lower() == "zakat" else "Non-Zakat"
            )

        if "Donor Address Country Code" in df.columns:
            def safe_country(c):
                if pd.isna(c) or str(c).strip() in ["", "nan", "None", "NaN"]:
                    return "Unknown"
                c_str = str(c).strip()
                return COUNTRY_ISO_MAP.get(c_str.upper(), c_str)

            df["Billing Country"] = df["Donor Address Country Code"].apply(safe_country)

        if "Created At" in df.columns:
            parsed = pd.to_datetime(df["Created At"], errors="coerce")
            df["Created Date (UTC)"] = parsed.dt.date
            df["Created Time (UTC)"] = parsed.dt.time.astype(str)
        elif "Confirmed At" in df.columns:
            parsed = pd.to_datetime(df["Confirmed At"], errors="coerce")
            df["Created Date (UTC)"] = parsed.dt.date
            df["Created Time (UTC)"] = parsed.dt.time.astype(str)

        # Apply or initialize classifications database for Rethink Website
        init_classification_db()
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        try:
            db_matrix = pd.read_sql_query("SELECT * FROM rethink_website_classifications", conn)
            rule_dict = {str(r["campaign_name"]).strip().lower(): r for _, r in db_matrix.iterrows()}
        except Exception:
            rule_dict = {}
        finally:
            conn.close()

        for col in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
            if col not in df.columns:
                df[col] = "Unassigned"

        cname_series = df["Campaign Name"].astype(str).str.strip()
        cname_lower = cname_series.str.lower()

        # Vectorized classification rule mapping for Rethink Website (< 5ms)
        for f in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
            db_f = f.lower().replace("-", "_").replace(" ", "_")
            mapped_vals = cname_lower.map(lambda c: rule_dict.get(c, {}).get(db_f))
            valid_mask = mapped_vals.notna() & (~mapped_vals.astype(str).str.lower().isin(["", "nan", "none", "unassigned"]))
            if valid_mask.any():
                df.loc[valid_mask, f] = mapped_vals[valid_mask]

        # Seed new website projects into rethink_website_classifications
        unique_cnames = df[["Campaign Name", "Community Name", "Country", "Zakat Eligibility"]].drop_duplicates(subset=["Campaign Name"])
        new_rules = []
        for _, r in unique_cnames.iterrows():
            cn = str(r["Campaign Name"]).strip()
            cn_l = cn.lower()
            if cn and cn_l not in ["nan", "none", "n/a", ""] and cn_l not in rule_dict:
                cm = str(r.get("Community Name") or "N/A").strip()
                ct = str(r.get("Country") or "Unassigned").strip()
                zk = str(r.get("Zakat Eligibility") or "Unassigned").strip()
                new_rules.append((cn, cm, "Unassigned", "Unassigned", ct, "Unassigned", zk))

        if new_rules:
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            try:
                conn.executemany("""
                    INSERT OR REPLACE INTO rethink_website_classifications (campaign_name, community_name, heading, sub_heading, country, code, zakat_eligibility)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, new_rules)
                conn.commit()
            except Exception as e:
                print(f"Error seeding new website rules: {e}")
            finally:
                conn.close()

    elif is_givebright:
        df["Platform"] = "GiveBright"
        col_map = {
            "donation_id": "Donation ID",
            "campaign_name": "Campaign Name",
            "fundraiser_by": "Community Name",
            "campaign_url": "Campaign URL",
            "fundraiser_url": "Fundraiser URL",
            "url": "Campaign URL",
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
            parsed = pd.to_datetime(df["created_at"], errors="coerce")
            df["Created Date (UTC)"] = parsed.dt.date.astype(str)
            df["Created Time (UTC)"] = parsed.dt.time.astype(str)

        # Vectorized classification rule mapping for GiveBright (< 5ms)
        init_classification_db()
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        try:
            db_matrix = pd.read_sql_query("SELECT * FROM givebright_classifications", conn)
            rule_dict = {str(r["campaign_name"]).strip().lower(): r for _, r in db_matrix.iterrows()}
        except Exception:
            rule_dict = {}
        finally:
            conn.close()

        for col in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
            if col not in df.columns:
                df[col] = "Unassigned"

        if "Campaign Name" in df.columns:
            cname_series = df["Campaign Name"].astype(str).str.strip()
            cname_lower = cname_series.str.lower()

            for f in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
                db_f = f.lower().replace("-", "_").replace(" ", "_")
                mapped_vals = cname_lower.map(lambda c: rule_dict.get(c, {}).get(db_f))
                valid_mask = mapped_vals.notna() & (~mapped_vals.astype(str).str.lower().isin(["", "nan", "none", "unassigned"]))
                if valid_mask.any():
                    df.loc[valid_mask, f] = mapped_vals[valid_mask]

            # Seed new GiveBright campaigns into givebright_classifications database in 1 vectorized pass
            unique_cnames = df[["Campaign Name"]].drop_duplicates(subset=["Campaign Name"])
            new_rules = []
            for _, r in unique_cnames.iterrows():
                cn = str(r["Campaign Name"]).strip()
                cn_l = cn.lower()
                if cn and cn_l not in ["nan", "none", "n/a", ""] and cn_l not in rule_dict:
                    curl = str(r.get("Campaign URL") or "").strip() if "Campaign URL" in r else ""
                    new_rules.append((cn, curl, "Unassigned", "Unassigned", "Unassigned", "Unassigned", "Unassigned"))

            if new_rules:
                conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                try:
                    conn.executemany("""
                        INSERT OR REPLACE INTO givebright_classifications (campaign_name, campaign_url, heading, sub_heading, country, code, zakat_eligibility)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, new_rules)
                    conn.commit()
                except Exception as e:
                    print(f"Error seeding new givebright rules: {e}")
                finally:
                    conn.close()

    else:
        df["Platform"] = "LaunchGood"

    if "Total Online Donations Net Amount in Settled Currency" in df.columns and "Donation Amount in Project Currency (May be approx.)" in df.columns:
        df["Total Online Donations Net Amount in Settled Currency"] = df["Total Online Donations Net Amount in Settled Currency"].fillna(df["Donation Amount in Project Currency (May be approx.)"])
    elif "Total Online Donations Net Amount in Settled Currency" not in df.columns and "Donation Amount in Project Currency (May be approx.)" in df.columns:
        df["Total Online Donations Net Amount in Settled Currency"] = df["Donation Amount in Project Currency (May be approx.)"]

    col_amount = "Total Online Donations Net Amount in Settled Currency"
    if col_amount not in df.columns:
        col_amount = "Donation Amount in Project Currency (May be approx.)"
    if col_amount not in df.columns:
        col_amount = "Donation Amount (in Donation Currency)"

    df['email_clean'] = df['Email'].astype(str).str.strip().str.lower() if 'Email' in df.columns else pd.Series("", index=df.index)
    df['email_clean'] = df['email_clean'].where(~df['email_clean'].isin(['nan', 'none', '']), None)
    
    fname = df['First Name'].astype(str).str.strip().str.lower().replace({'nan': '', 'none': ''}) if 'First Name' in df.columns else pd.Series("", index=df.index)
    lname = df['Last Name'].astype(str).str.strip().str.lower().replace({'nan': '', 'none': ''}) if 'Last Name' in df.columns else pd.Series("", index=df.index)
    df['full_name_clean'] = (fname + " " + lname).str.strip()
    df['full_name_clean'] = df['full_name_clean'].where(~df['full_name_clean'].isin(['', 'nan', 'none']), None)

    bname_col = df['Billing Name'] if 'Billing Name' in df.columns else pd.Series(index=df.index, dtype=str)
    df['bname_clean'] = bname_col.astype(str).str.strip().str.lower()
    df['bname_clean'] = df['bname_clean'].where(~df['bname_clean'].isin(['nan', 'none', '']), None)

    valid = df.dropna(subset=['full_name_clean', 'email_clean'])
    name_to_email_map = valid.groupby('full_name_clean')['email_clean'].first() if not valid.empty else pd.Series(dtype=str)

    mapped_email_from_name = df['full_name_clean'].map(name_to_email_map) if not name_to_email_map.empty else pd.Series(None, index=df.index)
    mapped_email_from_billing = df['bname_clean'].map(name_to_email_map) if not name_to_email_map.empty else pd.Series(None, index=df.index)

    df['Donor ID'] = df['email_clean'] \
        .combine_first(mapped_email_from_name) \
        .combine_first(df['full_name_clean']) \
        .combine_first(mapped_email_from_billing) \
        .combine_first(df['bname_clean']) \
        .combine_first(df.get('Donation ID', pd.Series(range(len(df)), index=df.index)).astype(str))

    df.drop(columns=['email_clean', 'full_name_clean', 'bname_clean'], inplace=True, errors='ignore')

    if col_amount in df.columns:
        df[col_amount] = pd.to_numeric(df[col_amount], errors='coerce').fillna(0)
        ltv_map = df.groupby('Donor ID')[col_amount].sum()
        df['Total LTV'] = df['Donor ID'].map(ltv_map)
        df['Lifetime Donor Classification'] = df['Total LTV'].apply(classify_donor_amount)
        df['Transaction Donor Classification'] = df[col_amount].apply(classify_donor_amount)

    donor_counts = df['Donor ID'].value_counts()
    repeat_donors = set(donor_counts[donor_counts > 1].index)
    df['Payment Frequency'] = df['Donor ID'].map(
        lambda d: 'Recurring Payment' if d in repeat_donors else 'One-Time Payment'
    )

    df = deduplicate_dataframe_columns(df)

    # --- CLASSIFICATIONS MATRIX LOOKUP BY CAMPAIGN NAME (INDEPENDENT PER PLATFORM) ---
    target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
    for col in target_cols:
        if col not in df.columns:
            df[col] = "Unassigned"

    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        tbl_name = (
            "rethink_website_classifications" if is_rethink_website else
            "paysuite_classifications" if is_paysuite else
            "givebright_classifications" if is_givebright else
            "campaign_classifications"
        )
        db_matrix = pd.read_sql_query(f"SELECT * FROM {tbl_name}", conn)
        conn.close()

        if not db_matrix.empty and "campaign_name" in db_matrix.columns and "Campaign Name" in df.columns:
            rule_dict = {str(c).strip().lower(): r for c, r in zip(db_matrix["campaign_name"], db_matrix.to_dict('records'))}
            cname_series = df["Campaign Name"].astype(str).str.strip().str.lower()
            for f in target_cols:
                db_f = f.lower().replace("-", "_").replace(" ", "_")
                mapped_vals = cname_series.map(lambda c: rule_dict.get(c, {}).get(db_f))
                valid_mask = mapped_vals.notna() & (~mapped_vals.astype(str).str.lower().isin(["", "nan", "none", "unassigned"]))
                curr_unassigned = df[f].astype(str).str.strip().str.lower().isin(["", "unassigned", "nan", "none"])
                fill_mask = valid_mask & curr_unassigned
                if fill_mask.any():
                    df.loc[fill_mask, f] = mapped_vals[fill_mask]
    except Exception as e:
        print(f"Error mapping campaign classifications matrix: {e}")

    # Second Pass: Dynamic auto-assignment based on Code mapping across all platforms (< 5ms)
    code_map = get_code_to_classification_map()
    if code_map and "Code" in df.columns:
        code_series = df["Code"].astype(str).str.strip().str.lower()
        for tc in ["Heading", "Sub-Heading", "Country", "Zakat Eligibility"]:
            tc_map = {k: v[tc] for k, v in code_map.items() if tc in v and str(v[tc]).lower() not in ["unassigned", "nan", "none", ""]}
            mapped_vals = code_series.map(tc_map)
            curr_unassigned = df[tc].astype(str).str.strip().str.lower().isin(["", "unassigned", "nan", "none"])
            fill_mask = mapped_vals.notna() & curr_unassigned
            if fill_mask.any():
                df.loc[fill_mask, tc] = mapped_vals[fill_mask]

    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).apply(fix_mojibake)

    return df


def process_and_upload_excel(file_buffer, source_name=None, upload_mode="replace", platform="auto"):
    """Reads Excel/CSV, standardizes schema, enriches data, auto-classifies, and saves to database."""
    # Detect CSV format defensively
    is_csv = False
    if source_name and str(source_name).lower().endswith('.csv'):
        is_csv = True
    else:
        fname = getattr(file_buffer, 'name', '')
        if isinstance(fname, str) and fname.lower().endswith('.csv'):
            is_csv = True

    df = None
    if is_csv:
        try:
            df = pd.read_csv(file_buffer)
        except Exception:
            file_buffer.seek(0)
            try:
                sheets_dict = pd.read_excel(file_buffer, sheet_name=None)
                list_of_dfs = [sdf for sdf in sheets_dict.values() if not sdf.empty]
                df = pd.concat(list_of_dfs, ignore_index=True)
            except Exception as ex:
                raise ValueError(f"Could not parse uploaded CSV file: {ex}")
    else:
        try:
            file_buffer.seek(0)
            sheets_dict = pd.read_excel(file_buffer, sheet_name=None)
            list_of_dfs = []
            for sdf in sheets_dict.values():
                if not sdf.empty:
                    sdf.columns = [str(c).strip() for c in sdf.columns]
                    list_of_dfs.append(sdf)
            df = pd.concat(list_of_dfs, ignore_index=True)
        except Exception:
            file_buffer.seek(0)
            try:
                df = pd.read_csv(file_buffer)
            except Exception as ex:
                raise ValueError(f"Could not parse uploaded Excel/CSV file: {ex}")

    if df is None or df.empty:
        raise ValueError("Uploaded file contains no valid data rows.")

    df = deduplicate_dataframe_columns(df)

    batch_label = str(source_name).strip() if (source_name and str(source_name).strip()) else "Master Dataset"
    df["Source"] = batch_label

    # Enrich and Auto-Classify New Raw Data
    df_new = _enrich_dataframe(df, platform=platform)

    # Sync auto-assigned classifications for new upload batch ONLY (< 10ms)
    sync_donors_to_classification_matrix(df_new)

    # Merge or Replace dataset in database
    if upload_mode in ["merge", "append"] and os.path.exists(PARQUET_PATH):
        try:
            existing_df = pd.read_parquet(PARQUET_PATH)
            if existing_df is not None and not existing_df.empty:
                df_combined = pd.concat([existing_df, df_new], ignore_index=True)
                if "Donation ID" in df_combined.columns:
                    valid_mask = df_combined["Donation ID"].notna() & (~df_combined["Donation ID"].astype(str).str.strip().str.lower().isin(["", "nan", "none", "n/a", "<na>"]))
                    df_valid = df_combined[valid_mask].drop_duplicates(subset=["Donation ID"], keep="last")
                    df_invalid = df_combined[~valid_mask]
                    df_combined = pd.concat([df_valid, df_invalid], ignore_index=True)
                df_save = df_combined
            else:
                df_save = df_new
        except Exception as e:
            print(f"[Merge Data Notice]: {e}")
            df_save = df_new
    else:
        df_save = df_new

    df_save = sanitize_df_dtypes_for_parquet(df_save)
    df_save.to_parquet(PARQUET_PATH, index=False)

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    df_save.to_sql("donations", con=conn, if_exists="replace", index=False, chunksize=5000)
    conn.close()

    # Invalidate dataset cache so new rows show up instantly
    load_data(force_reload=True)

    return {
        "status": "success",
        "added": len(df_new),
        "total_records": len(df_save)
    }

def sync_donor_classifications_to_matrix(df_donations):
    """Synchronizes cell edits from donor records back into campaign classification rules."""
    if df_donations.empty or "Campaign Name" not in df_donations.columns:
        return
    try:
        target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
        available_cols = [c for c in target_cols if c in df_donations.columns]
        if not available_cols:
            return

        c_name = df_donations["Campaign Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})
        comm_name = df_donations["Community Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'}) if "Community Name" in df_donations.columns else pd.Series("N/A", index=df_donations.index)

        donor_df = pd.DataFrame({"Campaign Name": c_name, "Community Name": comm_name})
        for tc in available_cols:
            donor_df[tc] = df_donations[tc].values

        matrix_df = donor_df.groupby(["Campaign Name", "Community Name"], dropna=False)[available_cols].agg(_mode_or_last).reset_index()
        save_classification_matrix(matrix_df)
    except Exception as e:
        print(f"Donor to matrix sync notice: {e}")

def sync_matrix_classifications_to_donors(matrix_df):
    """Applies classification matrix rule changes directly to all matching donor donation records instantly."""
    if matrix_df.empty or "Campaign Name" not in matrix_df.columns:
        return 0

    df_donations = load_data()
    if df_donations.empty or "Campaign Name" not in df_donations.columns:
        return 0

    try:
        camp_rule_map = {}
        for _, r in matrix_df.iterrows():
            c_name = str(r["Campaign Name"]).strip().lower()
            camp_rule_map[c_name] = {
                "Heading": str(r.get("Heading", "Unassigned")),
                "Sub-Heading": str(r.get("Sub-Heading", "Unassigned")),
                "Country": str(r.get("Country", "Unassigned")),
                "Code": str(r.get("Code", "N/A")),
                "Zakat Eligibility": str(r.get("Zakat Eligibility", "Unassigned"))
            }

        c_keys = df_donations["Campaign Name"].astype(str).str.strip().str.lower()
        target_fields = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
        updated_count = 0

        for col in target_fields:
            if col in df_donations.columns:
                col_map = {k: v[col] for k, v in camp_rule_map.items()}
                mapped_series = c_keys.map(col_map)
                mask = mapped_series.notna()
                df_donations.loc[mask, col] = mapped_series[mask]
                updated_count = int(mask.sum())

        df_donations.to_parquet(PARQUET_PATH, index=False)
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        df_donations.to_sql("donations", con=conn, if_exists="replace", index=False)
        conn.close()

        return updated_count
    except Exception as e:
        print(f"Matrix to donor sync notice: {e}")
        return 0

def purge_all_data():
    """Purges all tables and cache files."""
    if os.path.exists(PARQUET_PATH):
        try:
            os.remove(PARQUET_PATH)
        except Exception:
            pass

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS donations")
    cursor.execute("DROP TABLE IF EXISTS campaign_classifications")
    cursor.execute("DROP TABLE IF EXISTS givebright_classifications")
    conn.commit()
    conn.close()

    st.cache_data.clear()
    st.cache_resource.clear()

def update_source_tag(old_tag, new_tag):
    """Renames an existing dataset source tag across Parquet and SQLite."""
    if not old_tag or not new_tag:
        return 0
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("UPDATE donations SET Source = ? WHERE Source = ?", (new_tag, old_tag))
    updated_count = cursor.rowcount
    conn.commit()
    conn.close()

    if os.path.exists(PARQUET_PATH):
        try:
            df = pd.read_parquet(PARQUET_PATH)
            if "Source" in df.columns:
                df["Source"] = df["Source"].replace({old_tag: new_tag})
                df.to_parquet(PARQUET_PATH, index=False)
                sync_to_cloud_async(df, mode="replace")
        except Exception as e:
            print(f"Parquet source tag update notice: {e}")

    return updated_count

def delete_single_dataset(source_tag):
    """Deletes all records matching a specific source tag."""
    if not source_tag:
        return 0

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM donations WHERE Source = ?", (source_tag,))
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    if os.path.exists(PARQUET_PATH):
        try:
            df = pd.read_parquet(PARQUET_PATH)
            if "Source" in df.columns:
                df = df[df["Source"] != source_tag]
                df.to_parquet(PARQUET_PATH, index=False)
                sync_to_cloud_async(df, mode="replace")
        except Exception as e:
            print(f"Parquet dataset delete notice: {e}")

    return deleted_count

def invalidate_data_cache():
    """Forces the in-memory dataset cache to be invalidated."""
    global _CACHED_DF, _CACHE_MTIME
    with _CACHE_LOCK:
        _CACHED_DF = None
        _CACHE_MTIME = 0.0


def set_cached_data(df: pd.DataFrame):
    """Sets the in-memory dataset cache directly."""
    global _CACHED_DF, _CACHE_MTIME
    with _CACHE_LOCK:
        _CACHED_DF = df
        try:
            if os.path.exists(PARQUET_PATH):
                _CACHE_MTIME = os.path.getmtime(PARQUET_PATH)
            else:
                _CACHE_MTIME = 0.0
        except Exception:
            _CACHE_MTIME = 0.0


def load_data(force_reload: bool = False) -> pd.DataFrame:
    """
    High-Performance Dataset Loader with In-Memory Singleton Caching.
    Returns the cached DataFrame in < 1ms when available and up-to-date on disk.
    Transparently falls back to Parquet, then SQLite, then empty DataFrame on error.
    """
    global _CACHED_DF, _CACHE_MTIME

    # Check if Parquet file exists and get its mtime
    current_mtime = 0.0
    if os.path.exists(PARQUET_PATH):
        try:
            current_mtime = os.path.getmtime(PARQUET_PATH)
        except Exception:
            current_mtime = 0.0

    # Return cached DataFrame if valid and not force_reload
    if not force_reload and _CACHED_DF is not None and len(_CACHED_DF) > 0:
        if current_mtime == _CACHE_MTIME or current_mtime == 0.0:
            return _CACHED_DF

    with _CACHE_LOCK:
        # Double-check inside lock
        if not force_reload and _CACHED_DF is not None and len(_CACHED_DF) > 0:
            if current_mtime == _CACHE_MTIME or current_mtime == 0.0:
                return _CACHED_DF

        # 1. Primary: Load from Parquet binary cache (Fast columnar format)
        if os.path.exists(PARQUET_PATH):
            try:
                df = pd.read_parquet(PARQUET_PATH)
                if not df.empty:
                    _CACHED_DF = df
                    _CACHE_MTIME = current_mtime
                    return _CACHED_DF
            except Exception as e:
                print(f"[CACHE NOTICE] Parquet read fallback: {e}")

        # 2. Secondary Fallback: Load from SQLite
        try:
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            df = pd.read_sql_query("SELECT * FROM donations", conn)
            conn.close()
            if not df.empty:
                try:
                    df.to_parquet(PARQUET_PATH, index=False)
                    if os.path.exists(PARQUET_PATH):
                        _CACHE_MTIME = os.path.getmtime(PARQUET_PATH)
                except Exception:
                    pass
                _CACHED_DF = df
                return _CACHED_DF
        except Exception as e:
            print(f"[CACHE NOTICE] SQLite read fallback: {e}")

        # 3. Tertiary Fallback: Return empty DataFrame
        return pd.DataFrame()

