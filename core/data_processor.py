import os
import sqlite3
import threading
from typing import Optional

import pandas as pd

from config.settings import LOCAL_DB_PATH, PARQUET_PATH, PAYOUTS_PARQUET_PATH
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
    
    s = str(text)
    # Fast exit if standard clean ASCII
    if not any(c in s for c in ['â', 'Ã', 'Â', '\xa0', '\xad', '\x81', '\u200b', '\ufeff', '\ufffd', '’', '‘', '“', '”', '–', '—', 'ā', 'ū', 'ī']):
        return s

    replacements = {
        'â€™': "'",
        'â€˜': "'",
        'â€œ': '"',
        'â€\x9d': '"',
        'â€': '"',
        'â€“': '-',
        'â€”': '-',
        'Â': '',
        '\xa0': ' ',
        '\xad': '',
        '\u200b': '',
        '\ufeff': '',
        '\ufffd': '',
        '\x81': 'a',
        '’': "'",
        '‘': "'",
        '“': '"',
        '”': '"',
        '–': '-',
        '—': '-',
        'ā': 'a',
        'ū': 'u',
        'ī': 'i',
        'Abū': 'Abu'
    }
    for k, v in replacements.items():
        if k in s:
            s = s.replace(k, v)
            
    if any(c in s for c in ['â', 'Ã']):
        try:
            s = s.encode('latin1').decode('utf-8')
        except Exception:
            pass
        
    for k, v in replacements.items():
        if k in s:
            s = s.replace(k, v)
            
    return s

def deduplicate_dataframe_columns(df_input):
    """
    Finds and merges duplicate columns case-insensitively.
    """
    if df_input is None or df_input.empty:
        return df_input
    
    # Handle duplicate column names positional-indexed
    res_df = pd.DataFrame(index=df_input.index)
    col_dict = {}
    
    for i, col in enumerate(df_input.columns):
        series = df_input.iloc[:, i]
        norm = str(col).strip()
        norm_key = norm.lower()
        if norm_key not in col_dict:
            col_dict[norm_key] = (norm, series)
        else:
            orig_name, existing_series = col_dict[norm_key]
            col_dict[norm_key] = (orig_name, existing_series.fillna(series))

    for norm_key, (orig_name, s) in col_dict.items():
        res_df[orig_name] = s

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
    """Ensure SQLite campaign_classifications, paysuite_classifications, and sponsorship_targets tables exist with composite (campaign_name, code) primary keys."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        cur = conn.cursor()
        
        # 1. Migrate / Initialize campaign_classifications with composite PRIMARY KEY (campaign_name, code)
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='campaign_classifications'")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(campaign_classifications)")
            cols_info = cur.fetchall()
            pk_cols = [c[1] for c in cols_info if c[5] > 0]
            if pk_cols != ["campaign_name", "code"]:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS campaign_classifications_new (
                        campaign_name TEXT NOT NULL,
                        code TEXT NOT NULL DEFAULT 'Unassigned',
                        community_name TEXT DEFAULT 'N/A',
                        campaign_url TEXT DEFAULT '',
                        heading TEXT DEFAULT 'Unassigned',
                        sub_heading TEXT DEFAULT 'Unassigned',
                        country TEXT DEFAULT 'Unassigned',
                        zakat_eligibility TEXT DEFAULT 'Unassigned',
                        PRIMARY KEY (campaign_name, code)
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO campaign_classifications_new (campaign_name, code, community_name, campaign_url, heading, sub_heading, country, zakat_eligibility)
                    SELECT 
                        TRIM(COALESCE(campaign_name, 'Unassigned')), 
                        TRIM(COALESCE(NULLIF(code, ''), 'Unassigned')), 
                        TRIM(COALESCE(community_name, 'N/A')), 
                        TRIM(COALESCE(campaign_url, '')), 
                        TRIM(COALESCE(heading, 'Unassigned')), 
                        TRIM(COALESCE(sub_heading, 'Unassigned')), 
                        TRIM(COALESCE(country, 'Unassigned')), 
                        TRIM(COALESCE(zakat_eligibility, 'Unassigned'))
                    FROM campaign_classifications
                """)
                conn.execute("DROP TABLE campaign_classifications")
                conn.execute("ALTER TABLE campaign_classifications_new RENAME TO campaign_classifications")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS campaign_classifications (
                    campaign_name TEXT NOT NULL,
                    code TEXT NOT NULL DEFAULT 'Unassigned',
                    community_name TEXT DEFAULT 'N/A',
                    campaign_url TEXT DEFAULT '',
                    heading TEXT DEFAULT 'Unassigned',
                    sub_heading TEXT DEFAULT 'Unassigned',
                    country TEXT DEFAULT 'Unassigned',
                    zakat_eligibility TEXT DEFAULT 'Unassigned',
                    PRIMARY KEY (campaign_name, code)
                );
            """)

        # 2. Migrate / Initialize givebright_classifications
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='givebright_classifications'")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(givebright_classifications)")
            cols_info = cur.fetchall()
            pk_cols = [c[1] for c in cols_info if c[5] > 0]
            if pk_cols != ["campaign_name", "code"]:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS givebright_classifications_new (
                        campaign_name TEXT NOT NULL,
                        code TEXT NOT NULL DEFAULT 'Unassigned',
                        campaign_url TEXT DEFAULT '',
                        heading TEXT DEFAULT 'Unassigned',
                        sub_heading TEXT DEFAULT 'Unassigned',
                        country TEXT DEFAULT 'Unassigned',
                        zakat_eligibility TEXT DEFAULT 'Unassigned',
                        PRIMARY KEY (campaign_name, code)
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO givebright_classifications_new (campaign_name, code, campaign_url, heading, sub_heading, country, zakat_eligibility)
                    SELECT 
                        TRIM(COALESCE(campaign_name, 'Unassigned')), 
                        TRIM(COALESCE(NULLIF(code, ''), 'Unassigned')), 
                        TRIM(COALESCE(campaign_url, '')), 
                        TRIM(COALESCE(heading, 'Unassigned')), 
                        TRIM(COALESCE(sub_heading, 'Unassigned')), 
                        TRIM(COALESCE(country, 'Unassigned')), 
                        TRIM(COALESCE(zakat_eligibility, 'Unassigned'))
                    FROM givebright_classifications
                """)
                conn.execute("DROP TABLE givebright_classifications")
                conn.execute("ALTER TABLE givebright_classifications_new RENAME TO givebright_classifications")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS givebright_classifications (
                    campaign_name TEXT NOT NULL,
                    code TEXT NOT NULL DEFAULT 'Unassigned',
                    campaign_url TEXT DEFAULT '',
                    heading TEXT DEFAULT 'Unassigned',
                    sub_heading TEXT DEFAULT 'Unassigned',
                    country TEXT DEFAULT 'Unassigned',
                    zakat_eligibility TEXT DEFAULT 'Unassigned',
                    PRIMARY KEY (campaign_name, code)
                );
            """)

        # 3. Migrate / Initialize paysuite_classifications
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paysuite_classifications'")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(paysuite_classifications)")
            cols_info = cur.fetchall()
            pk_cols = [c[1] for c in cols_info if c[5] > 0]
            if pk_cols != ["campaign_name", "code"]:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS paysuite_classifications_new (
                        campaign_name TEXT NOT NULL,
                        code TEXT NOT NULL DEFAULT 'Unassigned',
                        community_name TEXT DEFAULT 'N/A',
                        heading TEXT DEFAULT 'Unassigned',
                        sub_heading TEXT DEFAULT 'Unassigned',
                        country TEXT DEFAULT 'Unassigned',
                        zakat_eligibility TEXT DEFAULT 'Unassigned',
                        donor_name TEXT DEFAULT '',
                        donor_email TEXT DEFAULT '',
                        PRIMARY KEY (campaign_name, code)
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO paysuite_classifications_new (campaign_name, code, community_name, heading, sub_heading, country, zakat_eligibility, donor_name, donor_email)
                    SELECT 
                        TRIM(COALESCE(campaign_name, 'Unassigned')), 
                        TRIM(COALESCE(NULLIF(code, ''), 'Unassigned')), 
                        TRIM(COALESCE(community_name, 'N/A')), 
                        TRIM(COALESCE(heading, 'Unassigned')), 
                        TRIM(COALESCE(sub_heading, 'Unassigned')), 
                        TRIM(COALESCE(country, 'Unassigned')), 
                        TRIM(COALESCE(zakat_eligibility, 'Unassigned')),
                        TRIM(COALESCE(donor_name, '')),
                        TRIM(COALESCE(donor_email, ''))
                    FROM paysuite_classifications
                """)
                conn.execute("DROP TABLE paysuite_classifications")
                conn.execute("ALTER TABLE paysuite_classifications_new RENAME TO paysuite_classifications")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paysuite_classifications (
                    campaign_name TEXT NOT NULL,
                    code TEXT NOT NULL DEFAULT 'Unassigned',
                    community_name TEXT DEFAULT 'N/A',
                    heading TEXT DEFAULT 'Unassigned',
                    sub_heading TEXT DEFAULT 'Unassigned',
                    country TEXT DEFAULT 'Unassigned',
                    zakat_eligibility TEXT DEFAULT 'Unassigned',
                    donor_name TEXT DEFAULT '',
                    donor_email TEXT DEFAULT '',
                    PRIMARY KEY (campaign_name, code)
                );
            """)

        # 4. Migrate / Initialize rethink_website_classifications
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rethink_website_classifications'")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(rethink_website_classifications)")
            cols_info = cur.fetchall()
            pk_cols = [c[1] for c in cols_info if c[5] > 0]
            if pk_cols != ["campaign_name", "code"]:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS rethink_website_classifications_new (
                        campaign_name TEXT NOT NULL,
                        code TEXT NOT NULL DEFAULT 'Unassigned',
                        community_name TEXT DEFAULT 'N/A',
                        heading TEXT DEFAULT 'Unassigned',
                        sub_heading TEXT DEFAULT 'Unassigned',
                        country TEXT DEFAULT 'Unassigned',
                        zakat_eligibility TEXT DEFAULT 'Unassigned',
                        PRIMARY KEY (campaign_name, code)
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO rethink_website_classifications_new (campaign_name, code, community_name, heading, sub_heading, country, zakat_eligibility)
                    SELECT 
                        TRIM(COALESCE(campaign_name, 'Unassigned')), 
                        TRIM(COALESCE(NULLIF(code, ''), 'Unassigned')), 
                        TRIM(COALESCE(community_name, 'N/A')), 
                        TRIM(COALESCE(heading, 'Unassigned')), 
                        TRIM(COALESCE(sub_heading, 'Unassigned')), 
                        TRIM(COALESCE(country, 'Unassigned')), 
                        TRIM(COALESCE(zakat_eligibility, 'Unassigned'))
                    FROM rethink_website_classifications
                """)
                conn.execute("DROP TABLE rethink_website_classifications")
                conn.execute("ALTER TABLE rethink_website_classifications_new RENAME TO rethink_website_classifications")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rethink_website_classifications (
                    campaign_name TEXT NOT NULL,
                    code TEXT NOT NULL DEFAULT 'Unassigned',
                    community_name TEXT DEFAULT 'N/A',
                    heading TEXT DEFAULT 'Unassigned',
                    sub_heading TEXT DEFAULT 'Unassigned',
                    country TEXT DEFAULT 'Unassigned',
                    zakat_eligibility TEXT DEFAULT 'Unassigned',
                    PRIMARY KEY (campaign_name, code)
                );
            """)

        # Ensure is_primary column exists across all classification tables
        for tbl in ["campaign_classifications", "givebright_classifications", "paysuite_classifications", "rethink_website_classifications"]:
            try:
                cur.execute(f"PRAGMA table_info({tbl})")
                cols = [c[1] for c in cur.fetchall()]
                if "is_primary" not in cols and len(cols) > 0:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN is_primary INTEGER DEFAULT 0")
            except Exception:
                pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sponsorship_targets (
                sponsorship_type TEXT PRIMARY KEY,
                target_value REAL
            );
        """)
        # Seed default target values if not exists
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
    """Returns the campaign_classifications matrix DataFrame with unique (Campaign Name, Code) granularity."""
    init_classification_db()
    target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]

    # 1. Read existing saved rules directly from SQLite
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        db_matrix = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(campaign_url, '') as "Campaign URL",
                COALESCE(community_name, 'N/A') as "Community Name",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility"
            FROM campaign_classifications
        """, conn)
    except Exception:
        db_matrix = pd.DataFrame(columns=["Campaign Name", "Code", "Campaign URL", "Community Name"] + [c for c in target_cols if c != "Code"])
    finally:
        conn.close()

    # 2. Extract distinct (Campaign Name, Code, Community Name) pairs from donations
    donor_distinct = None
    try:
        from core.analytics_engine import get_duckdb_connection
        con = get_duckdb_connection()
        if con and os.path.exists(PARQUET_PATH):
            donor_distinct = con.execute(f"""
                SELECT DISTINCT
                    COALESCE(NULLIF(TRIM("Campaign Name"), ''), 'N/A') as "Campaign Name",
                    COALESCE(NULLIF(TRIM("Code"), ''), 'Unassigned') as "Code",
                    COALESCE(NULLIF(TRIM("Community Name"), ''), 'N/A') as "Community Name"
                FROM '{PARQUET_PATH.replace(chr(92), '/')}'
                WHERE LOWER(COALESCE("Platform", '')) NOT IN ('givebright', 'paysuite')
                  AND "Campaign Name" IS NOT NULL
            """).df()
    except Exception as e:
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
                code_val = lg_df.loc[c_name.index, "Code"].astype(str).str.strip().replace({'nan': 'Unassigned', '': 'Unassigned', 'None': 'Unassigned'}) if "Code" in lg_df.columns else pd.Series("Unassigned", index=c_name.index)
                donor_df = pd.DataFrame({"Campaign Name": c_name, "Code": code_val, "Community Name": comm_name})
                donor_distinct = donor_df.drop_duplicates(subset=["Campaign Name", "Code", "Community Name"])

    if donor_distinct is not None and not donor_distinct.empty:
        if db_matrix.empty:
            matrix_df = donor_distinct.fillna("Unassigned").reset_index(drop=True)
        else:
            merged = pd.merge(
                donor_distinct[["Campaign Name", "Code", "Community Name"]],
                db_matrix,
                on=["Campaign Name", "Code"],
                how="outer",
                suffixes=('', '_db')
            ).fillna("Unassigned")
            if "Community Name_db" in merged.columns:
                merged["Community Name"] = merged["Community Name"].replace("N/A", "").combine_first(merged["Community Name_db"]).replace("", "N/A")
                merged.drop(columns=["Community Name_db"], inplace=True)
            matrix_df = merged.drop_duplicates(subset=["Campaign Name", "Code"]).reset_index(drop=True)
    else:
        matrix_df = db_matrix

    # Dynamic auto-assignment based on Code mapping in < 5ms
    code_map = get_code_to_classification_map()
    if code_map and "Code" in matrix_df.columns:
        code_clean = matrix_df["Code"].astype(str).str.strip().str.lower()
        for tc in ["Heading", "Sub-Heading", "Country", "Zakat Eligibility"]:
            if tc in matrix_df.columns:
                target_map = {k: v[tc] for k, v in code_map.items() if tc in v and str(v[tc]).lower() != "unassigned"}
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
    from active donor transactions into SQLite classification matrix tables with (campaign_name, code) granularity.
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

        # 1. Sync LaunchGood Campaigns (Keyed by Campaign Name + Code)
        lg_df = df[lg_mask]
        if not lg_df.empty:
            lg_grouped = lg_df.groupby(["Campaign Name", "Code"], as_index=False).agg({
                "Community Name": "first" if "Community Name" in lg_df.columns else lambda x: "N/A",
                "Campaign URL": "first" if "Campaign URL" in lg_df.columns else lambda x: "",
                "Heading": "last",
                "Sub-Heading": "last",
                "Country": "last",
                "Zakat Eligibility": "last"
            })
            for _, r in lg_grouped.iterrows():
                cname = str(r["Campaign Name"]).strip()
                code = str(r.get("Code") or "Unassigned").strip()
                if not cname or cname.lower() in ["nan", "none", "n/a", ""]:
                    continue
                comm = str(r.get("Community Name") or "N/A").strip()
                curl = str(r.get("Campaign URL") or "").strip()
                heading = str(r.get("Heading") or "Unassigned").strip()
                subheading = str(r.get("Sub-Heading") or "Unassigned").strip()
                country = str(r.get("Country") or "Unassigned").strip()
                zakat = str(r.get("Zakat Eligibility") or "Unassigned").strip()

                cursor.execute("""
                    INSERT INTO campaign_classifications (campaign_name, code, community_name, campaign_url, heading, sub_heading, country, zakat_eligibility)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campaign_name, code) DO UPDATE SET
                        community_name = excluded.community_name,
                        campaign_url = COALESCE(NULLIF(excluded.campaign_url, ''), campaign_classifications.campaign_url),
                        heading = CASE WHEN excluded.heading != 'Unassigned' THEN excluded.heading ELSE campaign_classifications.heading END,
                        sub_heading = CASE WHEN excluded.sub_heading != 'Unassigned' THEN excluded.sub_heading ELSE campaign_classifications.sub_heading END,
                        country = CASE WHEN excluded.country != 'Unassigned' THEN excluded.country ELSE campaign_classifications.country END,
                        zakat_eligibility = CASE WHEN excluded.zakat_eligibility != 'Unassigned' THEN excluded.zakat_eligibility ELSE campaign_classifications.zakat_eligibility END
                """, (cname, code, comm, curl, heading, subheading, country, zakat))
                synced_total += 1

        # 2. Sync GiveBright Campaigns (Keyed by Campaign Name + Code)
        gb_df = df[gb_mask]
        if not gb_df.empty:
            gb_grouped = gb_df.groupby(["Campaign Name", "Code"], as_index=False).agg({
                "Campaign URL": "first" if "Campaign URL" in gb_df.columns else lambda x: "",
                "Heading": "last",
                "Sub-Heading": "last",
                "Country": "last",
                "Zakat Eligibility": "last"
            })
            for _, r in gb_grouped.iterrows():
                cname = str(r["Campaign Name"]).strip()
                code = str(r.get("Code") or "Unassigned").strip()
                if not cname or cname.lower() in ["nan", "none", "n/a", ""]:
                    continue
                curl = str(r.get("Campaign URL") or "").strip()
                heading = str(r.get("Heading") or "Unassigned").strip()
                subheading = str(r.get("Sub-Heading") or "Unassigned").strip()
                country = str(r.get("Country") or "Unassigned").strip()
                zakat = str(r.get("Zakat Eligibility") or "Unassigned").strip()

                cursor.execute("""
                    INSERT INTO givebright_classifications (campaign_name, code, campaign_url, heading, sub_heading, country, zakat_eligibility)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campaign_name, code) DO UPDATE SET
                        campaign_url = COALESCE(NULLIF(excluded.campaign_url, ''), givebright_classifications.campaign_url),
                        heading = CASE WHEN excluded.heading != 'Unassigned' THEN excluded.heading ELSE givebright_classifications.heading END,
                        sub_heading = CASE WHEN excluded.sub_heading != 'Unassigned' THEN excluded.sub_heading ELSE givebright_classifications.sub_heading END,
                        country = CASE WHEN excluded.country != 'Unassigned' THEN excluded.country ELSE givebright_classifications.country END,
                        zakat_eligibility = CASE WHEN excluded.zakat_eligibility != 'Unassigned' THEN excluded.zakat_eligibility ELSE givebright_classifications.zakat_eligibility END
                """, (cname, code, curl, heading, subheading, country, zakat))
                synced_total += 1

        # 3. Sync Paysuite Campaigns (Keyed by Campaign Name + Code)
        ps_mask = (platform_s == "paysuite") | source_s.str.contains("paysuite", na=False)
        ps_df = df[ps_mask]
        if not ps_df.empty:
            ps_grouped = ps_df.groupby(["Campaign Name", "Code"], as_index=False).agg({
                "Community Name": "first" if "Community Name" in ps_df.columns else lambda x: "N/A",
                "Heading": "last",
                "Sub-Heading": "last",
                "Country": "last",
                "Zakat Eligibility": "last",
                "First Name": "last" if "First Name" in ps_df.columns else lambda x: "",
                "Last Name": "last" if "Last Name" in ps_df.columns else lambda x: "",
                "Email": "last" if "Email" in ps_df.columns else lambda x: ""
            })
            for _, r in ps_grouped.iterrows():
                cname = str(r["Campaign Name"]).strip()
                code = str(r.get("Code") or "Unassigned").strip()
                if not cname or cname.lower() in ["nan", "none", "n/a", ""]:
                    continue
                comm = str(r.get("Community Name") or "N/A").strip()
                heading = str(r.get("Heading") or "Unassigned").strip()
                subheading = str(r.get("Sub-Heading") or "Unassigned").strip()
                country = str(r.get("Country") or "Unassigned").strip()
                zakat = str(r.get("Zakat Eligibility") or "Unassigned").strip()
                fname = str(r.get("First Name") or "").strip()
                lname = str(r.get("Last Name") or "").strip()
                donor_name = f"{fname} {lname}".strip()
                donor_email = str(r.get("Email") or "").strip()

                cursor.execute("""
                    INSERT INTO paysuite_classifications (campaign_name, code, community_name, heading, sub_heading, country, zakat_eligibility, donor_name, donor_email)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campaign_name, code) DO UPDATE SET
                        community_name = excluded.community_name,
                        heading = CASE WHEN excluded.heading != 'Unassigned' THEN excluded.heading ELSE paysuite_classifications.heading END,
                        sub_heading = CASE WHEN excluded.sub_heading != 'Unassigned' THEN excluded.sub_heading ELSE paysuite_classifications.sub_heading END,
                        country = CASE WHEN excluded.country != 'Unassigned' THEN excluded.country ELSE paysuite_classifications.country END,
                        zakat_eligibility = CASE WHEN excluded.zakat_eligibility != 'Unassigned' THEN excluded.zakat_eligibility ELSE paysuite_classifications.zakat_eligibility END,
                        donor_name = COALESCE(NULLIF(excluded.donor_name, ''), paysuite_classifications.donor_name),
                        donor_email = COALESCE(NULLIF(excluded.donor_email, ''), paysuite_classifications.donor_email)
                """, (cname, code, comm, heading, subheading, country, zakat, donor_name, donor_email))
                synced_total += 1

        # 4. Sync Rethink Website Campaigns (Keyed by Campaign Name + Code)
        ws_mask = platform_s.str.contains("rethink website|website", regex=True, na=False)
        ws_df = df[ws_mask]
        if not ws_df.empty:
            ws_grouped = ws_df.groupby(["Campaign Name", "Code"], as_index=False).agg({
                "Community Name": "first" if "Community Name" in ws_df.columns else lambda x: "N/A",
                "Heading": "last",
                "Sub-Heading": "last",
                "Country": "last",
                "Zakat Eligibility": "last"
            })
            for _, r in ws_grouped.iterrows():
                cname = str(r["Campaign Name"]).strip()
                code = str(r.get("Code") or "Unassigned").strip()
                if not cname or cname.lower() in ["nan", "none", "n/a", ""]:
                    continue
                comm = str(r.get("Community Name") or "N/A").strip()
                heading = str(r.get("Heading") or "Unassigned").strip()
                subheading = str(r.get("Sub-Heading") or "Unassigned").strip()
                country = str(r.get("Country") or "Unassigned").strip()
                zakat = str(r.get("Zakat Eligibility") or "Unassigned").strip()

                cursor.execute("""
                    INSERT INTO rethink_website_classifications (campaign_name, code, community_name, heading, sub_heading, country, zakat_eligibility)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campaign_name, code) DO UPDATE SET
                        community_name = excluded.community_name,
                        heading = CASE WHEN excluded.heading != 'Unassigned' THEN excluded.heading ELSE rethink_website_classifications.heading END,
                        sub_heading = CASE WHEN excluded.sub_heading != 'Unassigned' THEN excluded.sub_heading ELSE rethink_website_classifications.sub_heading END,
                        country = CASE WHEN excluded.country != 'Unassigned' THEN excluded.country ELSE rethink_website_classifications.country END,
                        zakat_eligibility = CASE WHEN excluded.zakat_eligibility != 'Unassigned' THEN excluded.zakat_eligibility ELSE rethink_website_classifications.zakat_eligibility END
                """, (cname, code, comm, heading, subheading, country, zakat))
                synced_total += 1

        conn.commit()
    finally:
        conn.close()

    return synced_total


def sync_matrix_classifications_to_donors(matrix_df):
    """
    Updates matching donor records and payout settlements in Parquet and SQLite DB
    with saved classification matrix rules using (Campaign Name, Code) precision.
    """
    if matrix_df is None or matrix_df.empty:
        return 0

    df_raw = load_data()
    if df_raw.empty or "Campaign Name" not in df_raw.columns:
        return 0

    updated_count = 0
    campaign_series = df_raw["Campaign Name"].astype(str).str.strip().str.lower()
    code_series = df_raw["Code"].astype(str).str.strip().str.lower() if "Code" in df_raw.columns else pd.Series("unassigned", index=df_raw.index)

    # Group rules by campaign_name to accurately handle single-rule vs multi-rule campaigns
    cname_to_rules = {}
    for _, row in matrix_df.iterrows():
        cname = str(row.get("Campaign Name", "")).strip().lower()
        if cname and cname not in ["n/a", "none", "nan", ""]:
            if cname not in cname_to_rules:
                cname_to_rules[cname] = []
            cname_to_rules[cname].append(row)

    for cname, rules_list in cname_to_rules.items():
        c_mask = (campaign_series == cname)
        if not c_mask.any():
            continue

        if len(rules_list) == 1:
            # Single-rule campaign: update ALL records for this campaign unconditionally
            row = rules_list[0]
            col_vals = {
                "Heading": str(row.get("Heading", "Unassigned")),
                "Sub-Heading": str(row.get("Sub-Heading", "Unassigned")),
                "Country": str(row.get("Country", "Unassigned")),
                "Code": str(row.get("Code", "Unassigned")),
                "Zakat Eligibility": str(row.get("Zakat Eligibility", "Unassigned")),
            }
            if "Campaign URL" in row and str(row.get("Campaign URL") or "").strip():
                col_vals["Campaign URL"] = str(row.get("Campaign URL")).strip()

            for col_name, col_val in col_vals.items():
                if col_name in df_raw.columns:
                    df_raw.loc[c_mask, col_name] = col_val
            updated_count += int(c_mask.sum())
        else:
            # Multi-code campaign:
            primary_row = next((r for r in rules_list if bool(r.get("is_primary") in [1, True, "1", "true", "True"])), rules_list[0])
            valid_codes = [str(r.get("Code", "")).strip().lower() for r in rules_list if str(r.get("Code", "")).strip().lower() not in ["", "unassigned", "nan", "none", "n/a"]]

            # 1. Update matching exact code rows
            for row in rules_list:
                code = str(row.get("Code", "")).strip().lower()
                if not code or code in ["unassigned", "nan", "none", "n/a"]:
                    continue
                code_mask = c_mask & (code_series == code)
                if code_mask.any():
                    for col in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
                        if col in df_raw.columns:
                            df_raw.loc[code_mask, col] = str(row.get(col, "Unassigned"))
                    updated_count += int(code_mask.sum())

            # 2. Update any leftover or unassigned transactions of this campaign to the Primary variant
            leftover_mask = c_mask & (~code_series.isin(valid_codes))
            if leftover_mask.any():
                for col in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
                    if col in df_raw.columns:
                        df_raw.loc[leftover_mask, col] = str(primary_row.get(col, "Unassigned"))
                updated_count += int(leftover_mask.sum())

    df_raw = sanitize_df_dtypes_for_parquet(df_raw)
    df_raw.to_parquet(PARQUET_PATH, index=False)
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    df_raw.to_sql("donations", con=conn, if_exists="replace", index=False)

    # Also update payouts_cache.parquet & payout_settlements table in SQLite
    try:
        from config.settings import PAYOUTS_PARQUET_PATH
        if os.path.exists(PAYOUTS_PARQUET_PATH):
            pdf = pd.read_parquet(PAYOUTS_PARQUET_PATH)
            if not pdf.empty:
                p_cname = pdf.get("Campaign Name", pdf.get("Project Name", pd.Series("", index=pdf.index))).astype(str).str.strip().str.lower()
                p_code = pdf.get("Code", pd.Series("unassigned", index=pdf.index)).astype(str).str.strip().str.lower()

                for cname, rules_list in cname_to_rules.items():
                    pc_mask = (p_cname == cname)
                    if not pc_mask.any():
                        continue

                    if len(rules_list) == 1:
                        row = rules_list[0]
                        for col in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
                            if col in pdf.columns:
                                pdf.loc[pc_mask, col] = str(row.get(col, "Unassigned"))
                    else:
                        primary_row = next((r for r in rules_list if bool(r.get("is_primary") in [1, True, "1", "true", "True"])), rules_list[0])
                        valid_codes = [str(r.get("Code", "")).strip().lower() for r in rules_list if str(r.get("Code", "")).strip().lower() not in ["", "unassigned", "nan", "none", "n/a"]]

                        for row in rules_list:
                            code = str(row.get("Code", "")).strip().lower()
                            if not code or code in ["unassigned", "nan", "none", "n/a"]:
                                continue
                            pcode_mask = pc_mask & (p_code == code)
                            if pcode_mask.any():
                                for col in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
                                    if col in pdf.columns:
                                        pdf.loc[pcode_mask, col] = str(row.get(col, "Unassigned"))

                        leftover_pmask = pc_mask & (~p_code.isin(valid_codes))
                        if leftover_pmask.any():
                            for col in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
                                if col in pdf.columns:
                                    pdf.loc[leftover_pmask, col] = str(primary_row.get(col, "Unassigned"))

                pdf = sanitize_df_dtypes_for_parquet(pdf)
                pdf.to_parquet(PAYOUTS_PARQUET_PATH, index=False)
                pdf.to_sql("payout_settlements", con=conn, if_exists="replace", index=False)
    except Exception as e:
        print(f"[Payout settlement sync notice]: {e}")

    conn.close()
    invalidate_data_cache()
    from core.data_processor import invalidate_payouts_cache
    invalidate_payouts_cache()
    try:
        from backend.api.expenses import clear_expenses_cache
        clear_expenses_cache()
    except Exception:
        pass
    return updated_count


def save_classification_matrix(matrix_df):
    """Saves updated LaunchGood classification matrix with unique (Campaign Name, Code) granularity."""
    init_classification_db()
    if matrix_df.empty:
        return 0

    clean_matrix = matrix_df.copy()
    if "Campaign Name" not in clean_matrix.columns:
        clean_matrix["Campaign Name"] = "Unassigned"
    if "Code" not in clean_matrix.columns:
        clean_matrix["Code"] = "Unassigned"
    if "Community Name" not in clean_matrix.columns:
        clean_matrix["Community Name"] = "N/A"

    clean_matrix["Campaign Name"] = clean_matrix["Campaign Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})
    clean_matrix["Code"] = clean_matrix["Code"].astype(str).fillna("Unassigned").replace({'nan': 'Unassigned', '': 'Unassigned', 'None': 'Unassigned'})
    clean_matrix["Community Name"] = clean_matrix["Community Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)

    # 1. Reconcile codes per campaign: remove any codes in DB that are NOT in the submitted matrix for these campaigns
    cname_to_codes = {}
    for _, row in clean_matrix.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned")).strip().replace("’", "'").replace("‘", "'")
        code = str(row.get("Code", "Unassigned")).strip()
        if cname and cname.lower() not in ["nan", "none", "n/a", "", "campaign_name", "campaign name"]:
            cname_to_codes.setdefault(cname.lower(), set()).add(code.lower())

    for cname_lower, codes in cname_to_codes.items():
        placeholders = ','.join(['?'] * len(codes))
        conn.execute(f"DELETE FROM campaign_classifications WHERE LOWER(campaign_name) = ? AND LOWER(code) NOT IN ({placeholders})", [cname_lower] + list(codes))

    for _, row in clean_matrix.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned")).strip().replace("’", "'").replace("‘", "'")
        code = str(row.get("Code", "Unassigned")).strip()
        if not cname or cname.lower() in ["nan", "none", "n/a", "", "campaign_name", "campaign name"]:
            continue

        conn.execute("DELETE FROM campaign_classifications WHERE LOWER(campaign_name) = ? AND LOWER(code) = ?", (cname.lower(), code.lower()))
        conn.execute("""
            INSERT INTO campaign_classifications (campaign_name, code, community_name, campaign_url, heading, sub_heading, country, zakat_eligibility, is_primary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cname,
            code,
            str(row.get("Community Name", "N/A")),
            str(row.get("Campaign URL", "") or ""),
            str(row.get("Heading", "Unassigned")),
            str(row.get("Sub-Heading", "Unassigned")),
            str(row.get("Country", "Unassigned")),
            str(row.get("Zakat Eligibility", "Unassigned")),
            1 if row.get("is_primary") in [1, True, "1", "true", "True"] else 0
        ))
    conn.commit()
    conn.close()

    # Save to JSON config as well
    try:
        json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "campaign_classifications_launchgood.json")
        json_df = clean_matrix.drop_duplicates(subset=["Campaign Name", "Code"])
        with open(json_path, "w", encoding="utf-8") as f:
            import json
            json.dump(json_df.to_dict(orient="records"), f, indent=2)
    except Exception as e:
        print(f"Error saving JSON classifications: {e}")

    return len(clean_matrix)


def get_paysuite_classification_matrix(df_raw=None):
    """Returns the paysuite_classifications matrix DataFrame with (Campaign Name, Code) granularity."""
    init_classification_db()
    target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        db_matrix = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(community_name, 'N/A') as "Community Name",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility",
                COALESCE(donor_name, '') as "Donor Name",
                COALESCE(donor_email, '') as "Donor Email"
            FROM paysuite_classifications
        """, conn)
    except Exception:
        db_matrix = pd.DataFrame(columns=["Campaign Name", "Code", "Community Name"] + [c for c in target_cols if c != "Code"] + ["Donor Name", "Donor Email"])
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
            code_val = ps_df.loc[c_name.index, "Code"].astype(str).str.strip().replace({'nan': 'Unassigned', '': 'Unassigned', 'None': 'Unassigned'}) if "Code" in ps_df.columns else pd.Series("Unassigned", index=c_name.index)
            
            donor_df = pd.DataFrame({"Campaign Name": c_name, "Code": code_val, "Community Name": comm_name})
            donor_distinct = donor_df.drop_duplicates(subset=["Campaign Name", "Code"])

            if db_matrix.empty:
                return donor_distinct.fillna("Unassigned").reset_index(drop=True)

            merged = pd.merge(
                donor_distinct[["Campaign Name", "Code", "Community Name"]],
                db_matrix,
                on=["Campaign Name", "Code"],
                how="outer",
                suffixes=('', '_db')
            ).fillna("Unassigned")
            return merged.drop_duplicates(subset=["Campaign Name", "Code"]).reset_index(drop=True)

    if not db_matrix.empty:
        return db_matrix.fillna("Unassigned").reset_index(drop=True)

    return pd.DataFrame(columns=["Campaign Name", "Code", "Community Name"] + [c for c in target_cols if c != "Code"])


def save_paysuite_classification_matrix(matrix_df):
    """Saves updated Paysuite classification matrix to SQLite with (campaign_name, code) primary key."""
    init_classification_db()
    if matrix_df.empty:
        return 0
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)

    # 1. Reconcile codes per campaign: remove any codes in DB that are NOT in the submitted matrix for these campaigns
    cname_to_codes = {}
    for _, row in matrix_df.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned")).strip().replace("’", "'").replace("‘", "'")
        code = str(row.get("Code", "Unassigned")).strip()
        if cname and cname.lower() not in ["nan", "none", "n/a", "", "campaign_name", "campaign name"]:
            cname_to_codes.setdefault(cname.lower(), set()).add(code.lower())

    for cname_lower, codes in cname_to_codes.items():
        placeholders = ','.join(['?'] * len(codes))
        conn.execute(f"DELETE FROM paysuite_classifications WHERE LOWER(campaign_name) = ? AND LOWER(code) NOT IN ({placeholders})", [cname_lower] + list(codes))

    for _, row in matrix_df.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned")).strip().replace("’", "'").replace("‘", "'")
        code = str(row.get("Code", "Unassigned")).strip()
        if not cname or cname.lower() in ["nan", "none", "n/a", "", "campaign_name", "campaign name"]:
            continue

        d_name = str(row.get("Donor Name") or "").strip()
        d_email = str(row.get("Donor Email") or "").strip()

        # If donor name or email is blank in the incoming row, preserve existing values from DB
        if not d_name or not d_email or d_name.lower() == 'n/a' or d_email.lower() == 'n/a':
            cur = conn.execute("SELECT donor_name, donor_email FROM paysuite_classifications WHERE LOWER(campaign_name) = ? AND donor_name != '' AND donor_name != 'N/A' LIMIT 1", (cname.lower(),))
            res = cur.fetchone()
            if res:
                if (not d_name or d_name.lower() == 'n/a') and res[0]:
                    d_name = res[0]
                if (not d_email or d_email.lower() == 'n/a') and res[1]:
                    d_email = res[1]

        conn.execute("DELETE FROM paysuite_classifications WHERE LOWER(campaign_name) = ? AND LOWER(code) = ?", (cname.lower(), code.lower()))
        conn.execute("""
            INSERT INTO paysuite_classifications (campaign_name, code, community_name, heading, sub_heading, country, zakat_eligibility, donor_name, donor_email, is_primary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cname,
            code,
            str(row.get("Community Name", "N/A")),
            str(row.get("Heading", "Unassigned")),
            str(row.get("Sub-Heading", "Unassigned")),
            str(row.get("Country", "Unassigned")),
            str(row.get("Zakat Eligibility", "Unassigned")),
            d_name,
            d_email,
            1 if row.get("is_primary") in [1, True, "1", "true", "True"] else 0
        ))
    conn.commit()
    conn.close()
    return len(matrix_df)


def get_rethink_website_classification_matrix(df_raw=None):
    """Returns the rethink_website_classifications matrix DataFrame with (Campaign Name, Code) granularity."""
    init_classification_db()
    target_cols = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        db_matrix = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(community_name, 'N/A') as "Community Name",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility"
            FROM rethink_website_classifications
        """, conn)
    except Exception:
        db_matrix = pd.DataFrame(columns=["Campaign Name", "Code", "Community Name"] + [c for c in target_cols if c != "Code"])
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
            code_val = ws_df.loc[c_name.index, "Code"].astype(str).str.strip().replace({'nan': 'Unassigned', '': 'Unassigned', 'None': 'Unassigned'}) if "Code" in ws_df.columns else pd.Series("Unassigned", index=c_name.index)
            
            donor_df = pd.DataFrame({"Campaign Name": c_name, "Code": code_val, "Community Name": comm_name})
            donor_distinct = donor_df.drop_duplicates(subset=["Campaign Name", "Code"])

            if db_matrix.empty:
                return donor_distinct.fillna("Unassigned").reset_index(drop=True)

            merged = pd.merge(
                donor_distinct[["Campaign Name", "Code", "Community Name"]],
                db_matrix,
                on=["Campaign Name", "Code"],
                how="outer",
                suffixes=('', '_db')
            ).fillna("Unassigned")
            return merged.drop_duplicates(subset=["Campaign Name", "Code"]).reset_index(drop=True)

    if not db_matrix.empty:
        return db_matrix.fillna("Unassigned").reset_index(drop=True)

    return pd.DataFrame(columns=["Campaign Name", "Code", "Community Name"] + [c for c in target_cols if c != "Code"])


def save_rethink_website_classification_matrix(matrix_df):
    """Saves updated Rethink Website classification matrix to SQLite with (campaign_name, code) primary key."""
    init_classification_db()
    if matrix_df.empty:
        return 0
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)

    # 1. Reconcile codes per campaign: remove any codes in DB that are NOT in the submitted matrix for these campaigns
    cname_to_codes = {}
    for _, row in matrix_df.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned")).strip().replace("’", "'").replace("‘", "'")
        code = str(row.get("Code", "Unassigned")).strip()
        if cname and cname.lower() not in ["nan", "none", "n/a", "", "campaign_name", "campaign name"]:
            cname_to_codes.setdefault(cname.lower(), set()).add(code.lower())

    for cname_lower, codes in cname_to_codes.items():
        placeholders = ','.join(['?'] * len(codes))
        conn.execute(f"DELETE FROM rethink_website_classifications WHERE LOWER(campaign_name) = ? AND LOWER(code) NOT IN ({placeholders})", [cname_lower] + list(codes))

    for _, row in matrix_df.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned")).strip().replace("’", "'").replace("‘", "'")
        code = str(row.get("Code", "Unassigned")).strip()
        if not cname or cname.lower() in ["nan", "none", "n/a", "", "campaign_name", "campaign name"]:
            continue

        conn.execute("DELETE FROM rethink_website_classifications WHERE LOWER(campaign_name) = ? AND LOWER(code) = ?", (cname.lower(), code.lower()))
        conn.execute("""
            INSERT INTO rethink_website_classifications (campaign_name, code, community_name, heading, sub_heading, country, zakat_eligibility, is_primary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cname,
            code,
            str(row.get("Community Name", "N/A")),
            str(row.get("Heading", "Unassigned")),
            str(row.get("Sub-Heading", "Unassigned")),
            str(row.get("Country", "Unassigned")),
            str(row.get("Zakat Eligibility", "Unassigned")),
            1 if row.get("is_primary") in [1, True, "1", "true", "True"] else 0
        ))
    conn.commit()
    conn.close()
    return len(matrix_df)


def _enrich_dataframe(df, platform="auto"):
    """Pre-compute all derived columns (Donor ID, LTV, Classification, Payment Frequency) and apply classifications."""
    if df is None or df.empty:
        return df

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
        avail_ps_cols = [c for c in ["Donation ID", "Code", "Customer Ref"] if c in df.columns]
        unique_refs = df[avail_ps_cols].drop_duplicates(subset=["Donation ID"]) if "Donation ID" in df.columns else pd.DataFrame()
        new_rules = []
        for _, r in unique_refs.iterrows():
            b_ref = str(r.get("Donation ID", "")).strip()
            b_ref_l = b_ref.lower()
            if b_ref and b_ref_l not in ["nan", "none", "n/a", ""] and b_ref_l not in rule_dict:
                c_code = str(r.get("Code") or "Unassigned").strip()
                if not c_code or c_code.lower() in ["nan", "none"]:
                    c_code = "Unassigned"
                if "hafiz" in str(r.get("Customer Ref") or "").lower():
                    c_code = "SYR-SPN-HUF"
                new_rules.append((b_ref, c_code, "Paysuite", "Unassigned", "Unassigned", "Unassigned", "Unassigned", 0))

        if new_rules:
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            try:
                conn.executemany("""
                    INSERT OR IGNORE INTO paysuite_classifications (campaign_name, code, community_name, heading, sub_heading, country, zakat_eligibility, is_primary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        avail_ws_cols = [c for c in ["Campaign Name", "Community Name", "Country", "Zakat Eligibility", "Code"] if c in df.columns]
        unique_cnames = df[avail_ws_cols].drop_duplicates(subset=["Campaign Name"]) if "Campaign Name" in df.columns else pd.DataFrame()
        new_rules = []
        for _, r in unique_cnames.iterrows():
            cn = str(r.get("Campaign Name", "")).strip()
            cn_l = cn.lower()
            if cn and cn_l not in ["nan", "none", "n/a", ""] and cn_l not in rule_dict:
                cm = str(r.get("Community Name") or "N/A").strip()
                ct = str(r.get("Country") or "Unassigned").strip()
                cd = str(r.get("Code") or "Unassigned").strip()
                zk = str(r.get("Zakat Eligibility") or "Unassigned").strip()
                new_rules.append((cn, cd, cm, "Unassigned", "Unassigned", ct, zk, 0))

        if new_rules:
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            try:
                conn.executemany("""
                    INSERT OR IGNORE INTO rethink_website_classifications (campaign_name, code, community_name, heading, sub_heading, country, zakat_eligibility, is_primary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            parsed = pd.to_datetime(df["created_at"], errors="coerce", dayfirst=True)
            if parsed.isna().sum() > 0:
                parsed_fallback = pd.to_datetime(df["created_at"][parsed.isna()], errors="coerce", format="mixed")
                parsed.update(parsed_fallback)
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
        is_payout_file = ("Settlement Gross (SC)" in df.columns or "Transfer Amount (SC)" in df.columns or "Transfer ID" in df.columns)
        if is_payout_file or str(platform).lower() in ["payout", "launchgood payout", "payouts"]:
            df["Platform"] = "LaunchGood Payout"
            if "Code" in df.columns and "Giving Level Fund Code" in df.columns:
                df.drop(columns=["Giving Level Fund Code"], inplace=True, errors="ignore")
            df.rename(columns={
                "Project Name": "Campaign Name",
                "Settlement Gross (SC)": "Total Online Donation Gross Amount in Settled Currency",
                "Settlement Processing Fees (SC)": "Total Processing Fees Paid by CC In Settled Currency",
                "Transfer Amount (SC)": "Total Online Donations Net Amount in Settled Currency",
                "Transfer ID": "Transfer ID",
                "Type": "Type",
                "Gift Aid": "Gift Aid (yes or no)",
                "Giving Level Fund Code": "Code"
            }, inplace=True)
            df = deduplicate_dataframe_columns(df)

            if "Created Date" in df.columns:
                parsed_d = pd.to_datetime(df["Created Date"], errors="coerce")
                df["Created Date (UTC)"] = parsed_d.dt.date.astype(str)
            if "Created Time" in df.columns:
                df["Created Time (UTC)"] = df["Created Time"].astype(str)

            df["Payout Settled"] = "Yes"

            # Synthetic Donation ID for non-donation summary rows
            if "Donation ID" in df.columns:
                df["Donation ID"] = df["Donation ID"].fillna("").astype(str).str.strip()
                invalid_id_mask = df["Donation ID"].isin(["", "nan", "none", "n/a", "<na>", "0", "0.0"])
                if invalid_id_mask.any():
                    tid_s = df.get("Transfer ID", pd.Series("34579", index=df.index)).fillna("34579").astype(str).str.replace(".0", "", regex=False)
                    synthetic_ids = ["PAYOUT-" + str(tid_s.iloc[idx]) + "-" + str(idx + 1) for idx, is_invalid in enumerate(invalid_id_mask) if is_invalid]
                    df.loc[invalid_id_mask, "Donation ID"] = synthetic_ids

            # Direct Donation ID Classification Mapping from existing database records (< 10ms vectorized)
            try:
                df_existing = load_data()
                if df_existing is not None and not df_existing.empty and "Donation ID" in df_existing.columns:
                    valid_existing = df_existing.dropna(subset=["Donation ID"])
                    if not valid_existing.empty:
                        did_series = df["Donation ID"].astype(str).str.strip().str.lower()
                        existing_dedup = valid_existing.drop_duplicates(subset=["Donation ID"], keep="last").copy()
                        existing_dedup["_did_key"] = existing_dedup["Donation ID"].astype(str).str.strip().str.lower()
                        existing_indexed = existing_dedup.set_index("_did_key")
                        
                        for f in ["Campaign Name", "Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
                            if f in existing_indexed.columns:
                                col_map = existing_indexed[f].dropna().to_dict()
                                if f not in df.columns:
                                    df[f] = "Unassigned"
                                mapped = did_series.map(col_map)
                                valid_m = mapped.notna() & (~mapped.astype(str).str.lower().isin(["", "nan", "none", "unassigned"]))
                                if valid_m.any():
                                    df.loc[valid_m, f] = mapped[valid_m]
            except Exception as ex:
                print(f"[Notice] Donation ID classification mapping notice: {ex}")
        else:
            df["Platform"] = "LaunchGood"

    if "Payout Settled" not in df.columns:
        df["Payout Settled"] = "No"

    if "Total Online Donations Net Amount in Settled Currency" in df.columns and "Donation Amount in Project Currency (May be approx.)" in df.columns:
        df["Total Online Donations Net Amount in Settled Currency"] = df["Total Online Donations Net Amount in Settled Currency"].fillna(df["Donation Amount in Project Currency (May be approx.)"])
    elif "Total Online Donations Net Amount in Settled Currency" not in df.columns and "Donation Amount in Project Currency (May be approx.)" in df.columns:
        df["Total Online Donations Net Amount in Settled Currency"] = df["Donation Amount in Project Currency (May be approx.)"]

    col_amount = "Total Online Donations Net Amount in Settled Currency"
    if col_amount not in df.columns:
        col_amount = "Donation Amount in Project Currency (May be approx.)"
    if col_amount not in df.columns:
        col_amount = "Donation Amount (in Donation Currency)"

    GENERIC_DONOR_NAMES = {
        'anonymous', 'anonymous kind soul', 'anonymous donor', 'kind soul', 
        'donation boost', 'unnamed donor', 'nan', 'none', 'null', '', 'unassigned',
        'mr', 'mrs', 'miss', 'dr', 'ms', 'm', 's', 'a', 'n'
    }

    df['email_clean'] = df['Email'].fillna("").astype(str).str.strip().str.lower() if 'Email' in df.columns else pd.Series("", index=df.index, dtype=str)
    df['email_clean'] = df['email_clean'].where(~df['email_clean'].isin(['nan', 'none', '', 'unassigned', 'null']), None)
    
    fname = df['First Name'].fillna("").astype(str).str.strip().str.lower().replace({'nan': '', 'none': ''}) if 'First Name' in df.columns else pd.Series("", index=df.index, dtype=str)
    lname = df['Last Name'].fillna("").astype(str).str.strip().str.lower().replace({'nan': '', 'none': ''}) if 'Last Name' in df.columns else pd.Series("", index=df.index, dtype=str)
    df['full_name_clean'] = (fname.astype(str) + " " + lname.astype(str)).str.strip()
    df['full_name_clean'] = df['full_name_clean'].where(~df['full_name_clean'].isin(GENERIC_DONOR_NAMES), None)

    bname_col = df['Billing Name'] if 'Billing Name' in df.columns else pd.Series("", index=df.index, dtype=str)
    df['bname_clean'] = bname_col.fillna("").astype(str).str.strip().str.lower()
    df['bname_clean'] = df['bname_clean'].where(~df['bname_clean'].isin(GENERIC_DONOR_NAMES), None)

    # Only map authentic human full names (at least 2 words or distinct non-generic names) to email
    valid = pd.DataFrame({'name': df['full_name_clean'], 'email': df['email_clean']}).dropna()
    valid = valid[valid['name'].str.contains(' ') & (~valid['name'].isin(GENERIC_DONOR_NAMES))]
    name_to_email_map = valid.groupby('name')['email'].first() if not valid.empty else pd.Series(dtype=str)

    mapped_email_from_name = df['full_name_clean'].map(name_to_email_map) if not name_to_email_map.empty else pd.Series(None, index=df.index)
    mapped_email_from_billing = df['bname_clean'].map(name_to_email_map) if not name_to_email_map.empty else pd.Series(None, index=df.index)

    did_series = df['Donation ID'].astype(str) if 'Donation ID' in df.columns else pd.Series(range(len(df)), index=df.index).astype(str)

    df['Donor ID'] = df['email_clean'] \
        .combine_first(mapped_email_from_name) \
        .combine_first(mapped_email_from_billing) \
        .combine_first(df['full_name_clean']) \
        .combine_first(df['bname_clean']) \
        .combine_first(did_series)

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
            if "is_primary" in db_matrix.columns:
                db_sorted = db_matrix.sort_values(by="is_primary", ascending=False)
            else:
                db_sorted = db_matrix
            rule_dict = {}
            for _, r in db_sorted.iterrows():
                c_k = str(r["campaign_name"]).strip().lower()
                if c_k not in rule_dict:
                    rule_dict[c_k] = r.to_dict()
                elif r.get("is_primary") in [1, True, "1", "true", "True"]:
                    rule_dict[c_k] = r.to_dict()
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

    # Check if uploaded file is a Payout report vs Raw Donor report
    is_payout_file = (
        str(platform).lower() == "launchgood payout" or
        "Settlement Gross (SC)" in df.columns or
        "Transfer Amount (SC)" in df.columns or
        ("Transfer ID" in df.columns and "Type" in df.columns)
    )

    if is_payout_file:
        return process_payout_settlement_upload(df, source_name=batch_label, upload_mode=upload_mode)

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

def extract_and_sync_launchgood_payout_classifications(df_raw, sync_donors: bool = True):
    """
    Extracts all Project Name -> Code pairs from a payout file, resolves 5-tier classification
    (Heading, Sub-Heading, Country, Code, Zakat Eligibility) via get_code_to_classification_map(),
    upserts into campaign_classifications SQLite table & campaign_classifications_launchgood.json,
    and optionally auto-syncs raw donor records and payout settlement records in real time.
    """
    if df_raw.empty:
        return 0

    p_col = None
    for candidate in ["Project Name", "Campaign Name"]:
        if candidate in df_raw.columns:
            p_col = candidate
            break

    c_col = None
    for candidate in ["Code", "Giving Level Fund Code"]:
        if candidate in df_raw.columns:
            c_col = candidate
            break

    if not p_col or not c_col:
        return 0

    pairs_df = df_raw[[p_col, c_col]].drop_duplicates().dropna()
    code_map = get_code_to_classification_map()
    
    updated_rules = []
    for _, r in pairs_df.iterrows():
        p_name = str(r[p_col]).strip()
        c_code = str(r[c_col]).strip().lower()
        if not p_name or p_name.lower() in ["nan", "none", "n/a", ""]:
            continue
        if not c_code or c_code.lower() in ["nan", "none", "n/a", "", "unassigned"]:
            continue
        
        info = code_map.get(c_code, {})
        # Only seed into classification matrix if the code is a recognized master code in the dictionary
        if info and any(v not in ["Unassigned", "", None] for v in [info.get("Heading"), info.get("Country")]):
            updated_rules.append({
                "campaign_name": p_name,
                "community_name": "N/A",
                "campaign_url": "",
                "heading": info.get("Heading", "Unassigned"),
                "sub_heading": info.get("Sub-Heading", "Unassigned"),
                "country": info.get("Country", "Unassigned"),
                "code": str(r[c_col]).strip().upper(),
                "zakat_eligibility": info.get("Zakat Eligibility", "Unassigned"),
                "is_primary": 0
            })

    if not updated_rules:
        return 0

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    try:
        df_rules = pd.DataFrame(updated_rules)
        try:
            existing_matrix = pd.read_sql_query("SELECT * FROM campaign_classifications", conn)
            if not existing_matrix.empty and "campaign_name" in existing_matrix.columns:
                existing_dict = {(str(r["campaign_name"]).strip().lower(), str(r.get("code", "Unassigned")).strip().upper()): r.to_dict() for _, r in existing_matrix.iterrows()}
                for r in updated_rules:
                    k = (str(r["campaign_name"]).strip().lower(), str(r.get("code", "Unassigned")).strip().upper())
                    if k not in existing_dict:
                        existing_dict[k] = r
                    else:
                        # Only fill fields that are currently unassigned in existing_dict
                        for f in ["heading", "sub_heading", "country", "zakat_eligibility"]:
                            old_val = str(existing_dict[k].get(f, "")).strip().lower()
                            new_val = str(r.get(f, "")).strip()
                            if old_val in ["", "nan", "none", "unassigned"] and new_val.lower() not in ["", "nan", "none", "unassigned"]:
                                existing_dict[k][f] = new_val
                df_rules = pd.DataFrame(list(existing_dict.values()))
        except Exception:
            pass

        if "is_primary" not in df_rules.columns:
            df_rules["is_primary"] = 0
        if "campaign_url" not in df_rules.columns:
            df_rules["campaign_url"] = ""

        df_rules.to_sql("campaign_classifications", con=conn, if_exists="replace", index=False)
        conn.close()

        # Save to JSON file as well
        json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "campaign_classifications_launchgood.json")
        json_df = df_rules.rename(columns={
            "campaign_name": "Campaign Name",
            "community_name": "Community Name",
            "heading": "Heading",
            "sub_heading": "Sub-Heading",
            "country": "Country",
            "code": "Code",
            "zakat_eligibility": "Zakat Eligibility"
        })
        with open(json_path, "w", encoding="utf-8") as f:
            import json
            json.dump(json_df.to_dict(orient="records"), f, indent=2)

        if sync_donors:
            sync_matrix_classifications_to_donors(json_df)

        return len(updated_rules)
    except Exception as e:
        print(f"Error extracting payout classifications: {e}")
        return 0

def process_payout_settlement_upload(df_raw, source_name="LaunchGood Payout.xlsx", upload_mode="replace"):
    """
    Processes and saves Payout settlement records into the isolated payout_settlements SQLite table
    and payouts_cache.parquet without polluting raw donor contribution data in the donations table.
    """
    df_new = _enrich_dataframe(df_raw, platform="launchgood payout")
    
    # 1. Extract Campaign Code Mappings from Payout File and Update LaunchGood Matrix (without redundant donor loop)
    extract_and_sync_launchgood_payout_classifications(df_raw, sync_donors=False)

    # 2. Save Payout Settlement Dataset independently
    if upload_mode in ["merge", "append"] and os.path.exists(PAYOUTS_PARQUET_PATH):
        try:
            existing_payouts = pd.read_parquet(PAYOUTS_PARQUET_PATH)
            if existing_payouts is not None and not existing_payouts.empty:
                df_combined = pd.concat([existing_payouts, df_new], ignore_index=True)
                if "Donation ID" in df_combined.columns:
                    valid_mask = df_combined["Donation ID"].notna() & (~df_combined["Donation ID"].astype(str).str.strip().str.lower().isin(["", "nan", "none", "n/a", "<na>"]))
                    df_valid = df_combined[valid_mask].drop_duplicates(subset=["Donation ID"], keep="last")
                    df_invalid = df_combined[~valid_mask]
                    df_combined = pd.concat([df_valid, df_invalid], ignore_index=True)
                df_save = df_combined
            else:
                df_save = df_new
        except Exception as e:
            print(f"[Payout Merge Notice]: {e}")
            df_save = df_new
    else:
        df_save = df_new

    df_save = sanitize_df_dtypes_for_parquet(df_save)
    df_save.to_parquet(PAYOUTS_PARQUET_PATH, index=False)

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    df_save.to_sql("payout_settlements", con=conn, if_exists="replace", index=False, chunksize=5000)
    conn.close()

    # 3. Fast Vectorized Update on raw donor records in Parquet and SQLite DB (< 0.5s)
    try:
        settled_ids = set(df_new[df_new["Donation ID"].notna()]["Donation ID"].astype(str).str.strip().str.lower())
        if settled_ids and os.path.exists(PARQUET_PATH):
            donations_df = pd.read_parquet(PARQUET_PATH)
            if not donations_df.empty and "Donation ID" in donations_df.columns:
                m = donations_df["Donation ID"].astype(str).str.strip().str.lower().isin(settled_ids)
                if m.any():
                    if "Payout Settled" not in donations_df.columns:
                        donations_df["Payout Settled"] = "No"
                    donations_df.loc[m, "Payout Settled"] = "Yes"
                    donations_df = sanitize_df_dtypes_for_parquet(donations_df)
                    donations_df.to_parquet(PARQUET_PATH, index=False)
                    
                    try:
                        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
                        cursor = conn.cursor()
                        cursor.executemany("UPDATE donations SET \"Payout Settled\" = 'Yes' WHERE \"Donation ID\" = ?", [(sid,) for sid in settled_ids])
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
            
            load_data(force_reload=True)
    except Exception as e:
        print(f"[Payout Fast Sync Notice]: {e}")

    load_payouts_data(force_reload=True)
    try:
        from backend.api.payouts import invalidate_payouts_cache
        invalidate_payouts_cache()
    except Exception:
        pass

    try:
        from backend.api.expenses import clear_expenses_cache
        clear_expenses_cache()
        from backend.api.events import broadcast_event_sync
        broadcast_event_sync("PAYOUTS_UPDATED", {"source": "upload"})
    except Exception:
        pass

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
    """Applies classification matrix rule changes directly to all matching donor donation records and payout settlement records instantly (Single Source of Truth)."""
    if matrix_df.empty or "Campaign Name" not in matrix_df.columns:
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

        target_fields = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
        updated_count = 0

        # 1. Update Raw Donor Records in donations table
        df_donations = load_data(force_reload=True)
        if not df_donations.empty and "Campaign Name" in df_donations.columns:
            c_keys = df_donations["Campaign Name"].astype(str).str.strip().str.lower()
            for col in target_fields:
                if col in df_donations.columns:
                    col_map = {k: v[col] for k, v in camp_rule_map.items()}
                    mapped_series = c_keys.map(col_map)
                    mask = mapped_series.notna()
                    df_donations.loc[mask, col] = mapped_series[mask]
                    updated_count = int(mask.sum())

            df_donations = sanitize_df_dtypes_for_parquet(df_donations)
            df_donations.to_parquet(PARQUET_PATH, index=False)
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
            df_donations.to_sql("donations", con=conn, if_exists="replace", index=False, chunksize=5000)
            conn.close()

        # 2. Update Payout Settlement Records in payout_settlements table
        if os.path.exists(PAYOUTS_PARQUET_PATH):
            try:
                df_payouts = pd.read_parquet(PAYOUTS_PARQUET_PATH)
                if not df_payouts.empty and "Campaign Name" in df_payouts.columns:
                    p_keys = df_payouts["Campaign Name"].astype(str).str.strip().str.lower()
                    for col in target_fields:
                        if col in df_payouts.columns:
                            col_map = {k: v[col] for k, v in camp_rule_map.items()}
                            mapped_series = p_keys.map(col_map)
                            mask = mapped_series.notna()
                            df_payouts.loc[mask, col] = mapped_series[mask]

                    df_payouts = sanitize_df_dtypes_for_parquet(df_payouts)
                    df_payouts.to_parquet(PAYOUTS_PARQUET_PATH, index=False)
                    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                    df_payouts.to_sql("payout_settlements", con=conn, if_exists="replace", index=False, chunksize=5000)
                    conn.close()
            except Exception as e:
                print(f"Payout matrix sync notice: {e}")

        load_data(force_reload=True)
        return updated_count
    except Exception as e:
        print(f"Matrix to donor/payout sync notice: {e}")
        return 0

def purge_all_data():
    """Purges active transaction datasets (donations and payout settlements) while keeping campaign classification rules 100% intact."""
    if os.path.exists(PARQUET_PATH):
        try:
            os.remove(PARQUET_PATH)
        except Exception:
            pass

    if os.path.exists(PAYOUTS_PARQUET_PATH):
        try:
            os.remove(PAYOUTS_PARQUET_PATH)
        except Exception:
            pass

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS donations")
    cursor.execute("DROP TABLE IF EXISTS payout_settlements")
    # NOTE: Classification tables are permanently preserved and never dropped during transaction purge
    conn.commit()
    conn.close()

    invalidate_data_cache()
    invalidate_payouts_cache()
    try:
        from backend.api.payouts import invalidate_payouts_cache as inv_p
        inv_p()
    except Exception:
        pass

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
        _CACHE_MTIME = time.time()


def purge_payout_data():
    """Purges all LaunchGood Payout settlement records from SQLite (payout_settlements) & Parquet cache."""
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cursor = conn.cursor()

    # 1. Count and delete from isolated payout_settlements table
    payout_count = 0
    cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='payout_settlements'")
    if cursor.fetchone()[0] > 0:
        cursor.execute("SELECT COUNT(*) FROM payout_settlements")
        payout_count = cursor.fetchone()[0]
        cursor.execute("DROP TABLE IF EXISTS payout_settlements")

    # 2. Also remove any legacy payout rows from donations table
    cursor.execute("""
        DELETE FROM donations 
        WHERE "Platform" LIKE '%Payout%' 
           OR "Source" LIKE '%Payout%' 
           OR "Type" IN ('payout', 'reserve', 'fx', 'adjustment')
    """)
    legacy_donations_deleted = cursor.rowcount
    deleted_count = payout_count + (legacy_donations_deleted if legacy_donations_deleted > 0 else 0)

    # 3. Reset Payout Settled flag on remaining raw donor records if table exists
    cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='donations'")
    if cursor.fetchone()[0] > 0:
        cursor.execute("UPDATE donations SET \"Payout Settled\" = 'No' WHERE \"Payout Settled\" = 'Yes'")
    
    conn.commit()
    conn.close()

    # 4. Remove isolated payouts parquet cache
    if os.path.exists(PAYOUTS_PARQUET_PATH):
        try:
            if payout_count == 0:
                payout_count = len(pd.read_parquet(PAYOUTS_PARQUET_PATH))
                deleted_count = max(deleted_count, payout_count)
            os.remove(PAYOUTS_PARQUET_PATH)
        except Exception as e:
            print(f"Payouts parquet removal notice: {e}")

    # 5. Clean legacy rows and reset Payout Settled in donations parquet
    if os.path.exists(PARQUET_PATH):
        try:
            df = pd.read_parquet(PARQUET_PATH)
            if not df.empty:
                p_mask = pd.Series(False, index=df.index)
                if "Platform" in df.columns:
                    p_mask = p_mask | df["Platform"].astype(str).str.lower().str.contains("payout", na=False)
                if "Source" in df.columns:
                    p_mask = p_mask | df["Source"].astype(str).str.lower().str.contains("payout", na=False)
                if "Type" in df.columns:
                    p_mask = p_mask | df["Type"].astype(str).str.lower().isin(["payout", "reserve", "fx", "adjustment"])
                
                df_clean = df[~p_mask].copy()
                if "Payout Settled" in df_clean.columns:
                    df_clean["Payout Settled"] = "No"
                df_clean = sanitize_df_dtypes_for_parquet(df_clean)
                df_clean.to_parquet(PARQUET_PATH, index=False)
        except Exception as e:
            print(f"Parquet payout purge notice: {e}")

    # 6. Invalidate all caches
    invalidate_data_cache()
    invalidate_payouts_cache()
    load_data(force_reload=True)
    load_payouts_data(force_reload=True)
    try:
        from backend.api.payouts import invalidate_payouts_cache as inv_p
        inv_p()
    except Exception:
        pass

    return deleted_count


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


_CACHED_PAYOUTS_DF = None
_CACHE_PAYOUTS_MTIME = 0.0
_CACHE_PAYOUTS_LOCK = threading.Lock()

def invalidate_payouts_cache():
    """Forces the in-memory payouts dataset cache to be invalidated."""
    global _CACHED_PAYOUTS_DF, _CACHE_PAYOUTS_MTIME
    with _CACHE_PAYOUTS_LOCK:
        _CACHED_PAYOUTS_DF = None
        _CACHE_PAYOUTS_MTIME = 0.0

def load_payouts_data(force_reload: bool = False) -> pd.DataFrame:
    """Thread-safe cached loader for payout settlements dataset."""
    global _CACHED_PAYOUTS_DF, _CACHE_PAYOUTS_MTIME

    current_mtime = 0.0
    if os.path.exists(PAYOUTS_PARQUET_PATH):
        try:
            current_mtime = os.path.getmtime(PAYOUTS_PARQUET_PATH)
        except Exception:
            current_mtime = 0.0

    if not force_reload and _CACHED_PAYOUTS_DF is not None and len(_CACHED_PAYOUTS_DF) > 0:
        if current_mtime == _CACHE_PAYOUTS_MTIME or current_mtime == 0.0:
            return _CACHED_PAYOUTS_DF

    with _CACHE_PAYOUTS_LOCK:
        if not force_reload and _CACHED_PAYOUTS_DF is not None and len(_CACHED_PAYOUTS_DF) > 0:
            if current_mtime == _CACHE_PAYOUTS_MTIME or current_mtime == 0.0:
                return _CACHED_PAYOUTS_DF

        if os.path.exists(PAYOUTS_PARQUET_PATH):
            try:
                df = pd.read_parquet(PAYOUTS_PARQUET_PATH)
                if not df.empty:
                    _CACHED_PAYOUTS_DF = df
                    _CACHE_PAYOUTS_MTIME = current_mtime
                    return _CACHED_PAYOUTS_DF
            except Exception as e:
                print(f"[CACHE NOTICE] Payouts parquet read fallback: {e}")

        try:
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=15.0)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payout_settlements'")
            if cursor.fetchone():
                df = pd.read_sql_query("SELECT * FROM payout_settlements", conn)
                conn.close()
                if not df.empty:
                    try:
                        df.to_parquet(PAYOUTS_PARQUET_PATH, index=False)
                        if os.path.exists(PAYOUTS_PARQUET_PATH):
                            _CACHE_PAYOUTS_MTIME = os.path.getmtime(PAYOUTS_PARQUET_PATH)
                    except Exception:
                        pass
                    _CACHED_PAYOUTS_DF = df
                    return _CACHED_PAYOUTS_DF
            else:
                conn.close()
        except Exception as e:
            print(f"[CACHE NOTICE] Payouts SQLite read fallback: {e}")

        return pd.DataFrame()


def ensure_database_indexes():
    """Ensures database indexes exist on donations and payout_settlements for instant query performance."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_donor_id ON donations(\"Donor ID\")")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_camp_name ON donations(\"Campaign Name\")")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_code ON donations(\"Code\")")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_platform ON donations(\"Platform\")")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_created_date ON donations(\"Created Date (UTC)\")")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_payout_settled ON donations(\"Payout Settled\")")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payout_settlements'")
        if cursor.fetchone():
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_payouts_transfer_id ON payout_settlements(\"Transfer ID\")")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_payouts_donation_id ON payout_settlements(\"Donation ID\")")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_payouts_camp_name ON payout_settlements(\"Campaign Name\")")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Index Notice]: {e}")


def get_givebright_classification_matrix(df_raw=None):
    """Returns GiveBright classification matrix DataFrame with (Campaign Name, Code) granularity."""
    target_cols_display = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]

    # 1. Read SQLite stored GiveBright classifications
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        db_matrix = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(campaign_url, '') as "Campaign URL",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility"
            FROM givebright_classifications
        """, conn)
    except Exception:
        db_matrix = pd.DataFrame(columns=["Campaign Name", "Code", "Campaign URL"] + [c for c in target_cols_display if c != "Code"])
    finally:
        conn.close()

    # 2. Extract distinct GiveBright campaigns from in-memory cached donations
    df_donations = df_raw if (df_raw is not None and not df_raw.empty) else load_data()
    if df_donations is not None and not df_donations.empty and "Campaign Name" in df_donations.columns:
        platform_s = df_donations.get("Platform", pd.Series("", index=df_donations.index)).astype(str).str.lower()
        source_s = df_donations.get("Source", pd.Series("", index=df_donations.index)).astype(str).str.lower()
        gb_mask = (platform_s == "givebright") | source_s.str.contains("givebright|give_bright|file-", na=False)
        gb_df = df_donations[gb_mask] if gb_mask.any() else df_donations.iloc[0:0]

        if not gb_df.empty:
            c_name = gb_df["Campaign Name"].astype(str).str.strip()
            c_name = c_name[~c_name.str.lower().isin(['nan', 'none', 'n/a', '', 'unassigned'])]
            code_val = gb_df.loc[c_name.index, "Code"].astype(str).str.strip().replace({'nan': 'Unassigned', '': 'Unassigned', 'None': 'Unassigned'}) if "Code" in gb_df.columns else pd.Series("Unassigned", index=c_name.index)
            
            url_series = pd.Series("", index=gb_df.index)
            for u_col in ["Campaign URL", "campaign_url", "URL", "url"]:
                if u_col in gb_df.columns:
                    url_series = gb_df[u_col].fillna("").astype(str).replace({'nan': '', 'None': ''})
                    break

            donor_df = pd.DataFrame({"Campaign Name": c_name, "Code": code_val, "Campaign URL": url_series.loc[c_name.index]})
            for tc in target_cols_display:
                if tc in gb_df.columns and tc != "Code":
                    donor_df[tc] = gb_df.loc[c_name.index, tc].values

            donor_distinct = donor_df.drop_duplicates(subset=["Campaign Name", "Code"])

            if db_matrix.empty:
                return donor_distinct.fillna("Unassigned").reset_index(drop=True)

            merged = pd.merge(
                donor_distinct[["Campaign Name", "Code", "Campaign URL"]],
                db_matrix,
                on=["Campaign Name", "Code"],
                how="outer",
                suffixes=('', '_db')
            ).fillna("Unassigned")
            return merged.drop_duplicates(subset=["Campaign Name", "Code"]).reset_index(drop=True)

    if not db_matrix.empty:
        return db_matrix.fillna("Unassigned").reset_index(drop=True)

    return pd.DataFrame(columns=["Campaign Name", "Code", "Campaign URL"] + [c for c in target_cols_display if c != "Code"])


def save_givebright_classification_matrix(matrix_df):
    """Saves updated GiveBright classification matrix to SQLite and synchronizes to active donation records."""
    if matrix_df.empty:
        return 0

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)

    # 1. Reconcile codes per campaign
    cname_to_codes = {}
    for _, row in matrix_df.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned")).strip().replace("’", "'").replace("‘", "'")
        code = str(row.get("Code", "Unassigned")).strip()
        if cname and cname.lower() not in ["nan", "none", "n/a", "", "campaign_name", "campaign name"]:
            cname_to_codes.setdefault(cname.lower(), set()).add(code.lower())

    for cname_lower, codes in cname_to_codes.items():
        placeholders = ','.join(['?'] * len(codes))
        conn.execute(f"DELETE FROM givebright_classifications WHERE LOWER(campaign_name) = ? AND LOWER(code) NOT IN ({placeholders})", [cname_lower] + list(codes))

    for _, row in matrix_df.iterrows():
        cname = str(row.get("Campaign Name", "Unassigned")).strip().replace("’", "'").replace("‘", "'")
        code = str(row.get("Code", "Unassigned")).strip()
        curl = str(row.get("Campaign URL") or row.get("campaign_url") or "")
        if not cname or cname.lower() in ["nan", "none", "n/a", "", "campaign_name", "campaign name"]:
            continue

        conn.execute("DELETE FROM givebright_classifications WHERE LOWER(campaign_name) = ? AND LOWER(code) = ?", (cname.lower(), code.lower()))
        conn.execute("""
            INSERT INTO givebright_classifications (campaign_name, code, campaign_url, heading, sub_heading, country, zakat_eligibility, is_primary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cname,
            code,
            curl,
            str(row.get("Heading", "Unassigned")),
            str(row.get("Sub-Heading", "Unassigned")),
            str(row.get("Country", "Unassigned")),
            str(row.get("Zakat Eligibility", "Unassigned")),
            1 if row.get("is_primary") in [1, True, "1", "true", "True"] else 0
        ))
    conn.commit()
    conn.close()

    # Re-apply to active dataset in Parquet and SQLite using sync_matrix_classifications_to_donors
    sync_matrix_classifications_to_donors(matrix_df)

    return len(matrix_df)


def normalize_classification_import_df(raw_df):
    """Standardizes imported column names and auto-fills missing fields from recognized Codes."""
    col_mapping = {}
    for col in raw_df.columns:
        c_clean = str(col).strip().lower().replace("_", " ").replace("-", " ")
        if c_clean in ["campaign", "campaign name", "fundraiser name", "fundraiser", "bank ref", "direct debit ref", "project", "project name"]:
            col_mapping[col] = "Campaign Name"
        elif c_clean in ["community", "community name", "fundraiser by", "platform source"]:
            col_mapping[col] = "Community Name"
        elif c_clean in ["code", "campaign code", "project code", "cost code", "item code", "giving level fund code", "giving level campaign code", "fund code", "accounting code"]:
            col_mapping[col] = "Code"
        elif c_clean in ["heading", "main heading", "category", "main category"]:
            col_mapping[col] = "Heading"
        elif c_clean in ["sub heading", "subheading", "sub category", "subcategory", "sub_heading"]:
            col_mapping[col] = "Sub-Heading"
        elif c_clean in ["country", "beneficiary country", "target country"]:
            col_mapping[col] = "Country"
        elif c_clean in ["zakat eligibility", "zakat", "zakat eligibilty", "zakat status", "zakat_eligibility"]:
            col_mapping[col] = "Zakat Eligibility"
        elif c_clean in ["campaign url", "campaign link", "campaign page", "url", "link"]:
            col_mapping[col] = "Campaign URL"
        elif c_clean in ["fundraiser url", "fundraiser link", "fundraiser page"]:
            col_mapping[col] = "Fundraiser URL"

    df_norm = raw_df.rename(columns=col_mapping).copy()

    # Ensure required Campaign Name column exists
    if "Campaign Name" not in df_norm.columns:
        if len(df_norm.columns) > 0:
            df_norm.rename(columns={df_norm.columns[0]: "Campaign Name"}, inplace=True)

    if "Campaign URL" not in df_norm.columns:
        df_norm["Campaign URL"] = ""

    if "Community Name" not in df_norm.columns:
        df_norm["Community Name"] = "Unassigned"

    return df_norm

