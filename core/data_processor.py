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
        tables = ["campaign_classifications", "givebright_classifications", "paysuite_classifications"]
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



def sync_donors_to_classification_matrix(df_raw=None):
    """
    Synchronizes updated classifications (Code, Heading, Sub-Heading, Country, Zakat Eligibility)
    from active donor transactions into SQLite classification matrix tables
    (campaign_classifications, givebright_classifications, paysuite_classifications).
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

    try:
        platform_s = df.get("Platform", pd.Series("", index=df.index)).astype(str).str.lower()
        source_s = df.get("Source", pd.Series("", index=df.index)).astype(str).str.lower()

        # 1. Sync LaunchGood Campaigns
        lg_mask = (~platform_s.isin(["givebright", "paysuite"])) & (~source_s.str.contains("givebright|give_bright|paysuite|file-", na=False))
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
        gb_mask = (platform_s == "givebright") | source_s.str.contains("givebright|give_bright|file-", na=False)
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

                cursor.execute("""
                    UPDATE givebright_classifications 
                    SET campaign_url = COALESCE(NULLIF(?, ''), campaign_url), heading = ?, sub_heading = ?, country = ?, code = ?, zakat_eligibility = ?
                    WHERE campaign_name = ?
                """, (curl, heading, subheading, country, code, zakat, cname))
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO givebright_classifications (campaign_name, campaign_url, heading, sub_heading, country, code, zakat_eligibility)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (cname, curl, heading, subheading, country, code, zakat))
                synced_total += 1

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

def _enrich_dataframe(df, platform="auto"):
    """Pre-compute all derived columns (Donor ID, LTV, Classification, Payment Frequency) and apply classifications."""
    # 1. Platform Detection & Standardization
    is_paysuite = "Bank Ref" in df.columns and "Date of collection" in df.columns
    is_givebright = False
    
    if not is_paysuite:
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
            rule_map = {str(r["campaign_name"]).strip().lower(): r for _, r in db_matrix.iterrows()}
        except Exception:
            rule_map = {}
        finally:
            conn.close()

        # Add columns if not exist
        for col in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
            if col not in df.columns:
                df[col] = "Unassigned"

        new_rules_to_insert = []
        for idx, row in df.iterrows():
            bank_ref = str(row["Donation ID"]).strip()
            bank_ref_lower = bank_ref.lower()

            # 1. Fill in missing contact details from existing mapping
            if bank_ref_lower in existing_map:
                e_info = existing_map[bank_ref_lower]
                if pd.isna(row.get("Email")) or not str(row.get("Email")).strip() or str(row.get("Email")).strip().lower() in ["nan", "none"]:
                    df.at[idx, "Email"] = e_info.get("Email")
                if pd.isna(row.get("Billing Address")) or not str(row.get("Billing Address")).strip() or str(row.get("Billing Address")).strip().lower() in ["nan", "none"]:
                    df.at[idx, "Billing Address"] = e_info.get("Billing Address")
                if pd.isna(row.get("Billing Zip")) or not str(row.get("Billing Zip")).strip() or str(row.get("Billing Zip")).strip().lower() in ["nan", "none"]:
                    df.at[idx, "Billing Zip"] = e_info.get("Billing Zip")

            # 2. Fill in classifications from rule_map or existing database
            if bank_ref_lower in rule_map:
                r = rule_map[bank_ref_lower]
                df.at[idx, "Heading"] = r.get("heading") or "Unassigned"
                df.at[idx, "Sub-Heading"] = r.get("sub_heading") or "Unassigned"
                df.at[idx, "Country"] = r.get("country") or "Unassigned"
                df.at[idx, "Code"] = r.get("code") or "Unassigned"
                df.at[idx, "Zakat Eligibility"] = r.get("zakat_eligibility") or "Unassigned"
            elif bank_ref_lower in existing_map:
                e_info = existing_map[bank_ref_lower]
                df.at[idx, "Heading"] = e_info.get("Heading") or "Unassigned"
                df.at[idx, "Sub-Heading"] = e_info.get("Sub-Heading") or "Unassigned"
                df.at[idx, "Country"] = e_info.get("Country") or "Unassigned"
                df.at[idx, "Code"] = e_info.get("Code") or "Unassigned"
                df.at[idx, "Zakat Eligibility"] = e_info.get("Zakat Eligibility") or "Unassigned"
            else:
                csv_code = str(row.get("Code", "Unassigned")).strip()
                if not csv_code or csv_code.lower() in ["nan", "none"]:
                    csv_code = "Unassigned"

                # Check for "4x HAFIZ" in Customer Ref to auto-assign HUF
                cust_ref_str = str(row.get("Customer Ref", "")).strip().lower()
                if "hafiz" in cust_ref_str:
                    csv_code = "SYR-SPN-HUF"

                df.at[idx, "Code"] = csv_code
                rule_map[bank_ref_lower] = {
                    "campaign_name": bank_ref,
                    "community_name": "Paysuite",
                    "heading": "Unassigned",
                    "sub_heading": "Unassigned",
                    "country": "Unassigned",
                    "code": csv_code,
                    "zakat_eligibility": "Unassigned"
                }
                new_rules_to_insert.append((
                    bank_ref,
                    "Paysuite",
                    "Unassigned",
                    "Unassigned",
                    "Unassigned",
                    "csv_code",
                    "Unassigned"
                ))

        if new_rules_to_insert:
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            try:
                conn.executemany("""
                    INSERT OR REPLACE INTO paysuite_classifications (campaign_name, community_name, heading, sub_heading, country, code, zakat_eligibility)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, new_rules_to_insert)
                conn.commit()
            except Exception as e:
                print(f"Error seeding new rules: {e}")
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
            df["Created Date (UTC)"] = pd.to_datetime(df["created_at"], errors="coerce")
            df["Created Time (UTC)"] = df["Created Date (UTC)"].dt.time.astype(str)
            df["Created Date (UTC)"] = df["Created Date (UTC)"].dt.date

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

    # --- CLASSIFICATIONS MATRIX LOOKUP BY CAMPAIGN NAME ---
    target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
    for col in target_cols:
        if col not in df.columns:
            df[col] = "Unassigned"

    if not is_paysuite:
        try:
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            
            # Apply GiveBright classifications matrix for GiveBright records
            if is_givebright:
                db_matrix = pd.read_sql_query("SELECT * FROM givebright_classifications", conn)
                if not db_matrix.empty and "campaign_name" in db_matrix.columns:
                    gb_map = db_matrix.set_index("campaign_name")
                    for idx, row in df.iterrows():
                        camp = str(row.get("Campaign Name") or "").strip().lower()
                        if camp in gb_map.index:
                            r = gb_map.loc[camp]
                            if isinstance(r, pd.DataFrame):
                                r = r.iloc[-1]
                            for f in target_cols:
                                db_f = f.lower().replace("-", "_").replace(" ", "_")
                                val = str(r.get(db_f) or "Unassigned").strip()
                                if val and val.lower() not in ["", "nan", "none"]:
                                    df.at[idx, f] = val

            # Apply LaunchGood campaign classifications matrix for LaunchGood/default records
            else:
                db_matrix = pd.read_sql_query("SELECT * FROM campaign_classifications", conn)
                if not db_matrix.empty and "campaign_name" in db_matrix.columns:
                    lg_map = db_matrix.set_index("campaign_name")
                    for idx, row in df.iterrows():
                        camp = str(row.get("Campaign Name") or "").strip().lower()
                        if camp in lg_map.index:
                            r = lg_map.loc[camp]
                            if isinstance(r, pd.DataFrame):
                                r = r.iloc[-1]
                            for f in target_cols:
                                db_f = f.lower().replace("-", "_").replace(" ", "_")
                                val = str(r.get(db_f) or "Unassigned").strip()
                                if val and val.lower() not in ["", "nan", "none"]:
                                    df.at[idx, f] = val
                                    
            conn.close()
        except Exception as e:
            print(f"Error mapping campaign classifications matrix: {e}")

    # Second Pass: Dynamic auto-assignment based on Code mapping
    code_map = get_code_to_classification_map()
    for idx, row in df.iterrows():
        code = str(row.get("Code") or "").strip()
        code_lower = code.lower()
        if code and code_lower not in ["unassigned", "nan", "none", ""]:
            if code_lower in code_map:
                c_info = code_map[code_lower]
                for tc in ["Heading", "Sub-Heading", "Country", "Zakat Eligibility"]:
                    val = str(row.get(tc) or "").strip()
                    if not val or val.lower() in ["unassigned", "nan", "none"]:
                        df.at[idx, tc] = c_info[tc]

    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).apply(fix_mojibake)

    return df


def process_and_upload_excel(file_buffer, source_name=None, upload_mode="replace", platform="auto"):
    """Reads Excel/CSV, standardizes schema, enriches data, and saves to database."""
    is_csv = False
    fname = getattr(file_buffer, 'name', '')
    if isinstance(fname, str) and fname.lower().endswith('.csv'):
        is_csv = True

    if is_csv:
        df = pd.read_csv(file_buffer)
    else:
        sheets_dict = pd.read_excel(file_buffer, sheet_name=None)
        list_of_dfs = []
        for sdf in sheets_dict.values():
            if not sdf.empty:
                sdf.columns = [str(c).strip() for c in sdf.columns]
                list_of_dfs.append(sdf)
        df = pd.concat(list_of_dfs, ignore_index=True)

    batch_label = str(source_name).strip() if (source_name and str(source_name).strip()) else "Master Dataset"
    df["Source"] = batch_label

    df = _enrich_dataframe(df, platform=platform)
    df.to_parquet(PARQUET_PATH, index=False)

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    df.to_sql("donations", con=conn, if_exists="replace", index=False)
    conn.close()

    sync_to_cloud_async(df, mode="replace")
    return len(df)

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

