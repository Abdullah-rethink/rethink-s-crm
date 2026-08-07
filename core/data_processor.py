import os
import sqlite3

import pandas as pd
import streamlit as st

from config.settings import LOCAL_DB_PATH, PARQUET_PATH
from core.database import sync_to_cloud_async


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
    """Ensure SQLite campaign_classifications table exists."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_classifications (
                campaign_name TEXT PRIMARY KEY,
                community_name TEXT,
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
        print(f"Classification DB init notice: {e}")

def get_classification_matrix(df_raw=None):
    """Returns the campaign_classifications matrix DataFrame from active df_raw, Parquet & SQLite DB."""
    init_classification_db()
    target_cols_display = ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]
    matrix_df = pd.DataFrame(columns=["Campaign Name", "Community Name"] + target_cols_display)

    try:
        df_donations = df_raw
        if (df_donations is None or df_donations.empty) and os.path.exists(PARQUET_PATH):
            try:
                df_donations = pd.read_parquet(PARQUET_PATH)
            except Exception:
                df_donations = None

        if df_donations is not None and not df_donations.empty and "Campaign Name" in df_donations.columns:
            lg_mask = df_donations.get("Platform", pd.Series("", index=df_donations.index)).astype(str).str.lower() != "givebright"
            lg_df = df_donations[lg_mask] if lg_mask.any() else df_donations

            c_name = lg_df["Campaign Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})
            comm_name = lg_df["Community Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'}) if "Community Name" in lg_df.columns else pd.Series("N/A", index=lg_df.index)

            available_target_cols = [c for c in target_cols_display if c in lg_df.columns]
            donor_df = pd.DataFrame({"Campaign Name": c_name, "Community Name": comm_name})
            for tc in available_target_cols:
                donor_df[tc] = lg_df[tc].values

            matrix_df = donor_df.groupby(["Campaign Name", "Community Name"], dropna=False)[available_target_cols].first().reset_index()
                
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
                    db_matrix["Campaign Name"] = db_matrix["Campaign Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})
                    db_matrix["Community Name"] = db_matrix["Community Name"].astype(str).fillna("N/A").replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})
                    
                    # Merge saved DB rules over matrix_df
                    db_rule_map = {str(r["Campaign Name"]).strip().lower(): r for _, r in db_matrix.iterrows()}
                    for idx, row in matrix_df.iterrows():
                        c_key = str(row["Campaign Name"]).strip().lower()
                        if c_key in db_rule_map:
                            db_r = db_rule_map[c_key]
                            for tc in target_cols_display:
                                if tc in db_r and pd.notna(db_r[tc]) and str(db_r[tc]).strip() != "":
                                    matrix_df.at[idx, tc] = str(db_r[tc]).strip()

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

    return matrix_df


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

    if not rule_map:
        return 0

    campaign_series = df_raw["Campaign Name"].astype(str).str.strip().str.lower()
    for cname, rules in rule_map.items():
        mask = campaign_series == cname
        if mask.any():
            updated_count += int(mask.sum())
            for col_name, col_val in rules.items():
                df_raw.loc[mask, col_name] = col_val

    df_raw.to_parquet(PARQUET_PATH, index=False)
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    df_raw.to_sql("donations", con=conn, if_exists="replace", index=False)
    conn.close()

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
            INSERT INTO campaign_classifications (campaign_name, community_name, heading, sub_heading, country, code, zakat_eligibility)
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
    return len(clean_matrix)

def _enrich_dataframe(df):
    """Pre-compute all derived columns (Donor ID, LTV, Classification, Payment Frequency)."""
    if "Total Online Donations Net Amount in Settled Currency" in df.columns and "Donation Amount in Project Currency (May be approx.)" in df.columns:
        df["Total Online Donations Net Amount in Settled Currency"] = df["Total Online Donations Net Amount in Settled Currency"].fillna(df["Donation Amount in Project Currency (May be approx.)"])
    elif "Total Online Donations Net Amount in Settled Currency" not in df.columns and "Donation Amount in Project Currency (May be approx.)" in df.columns:
        df["Total Online Donations Net Amount in Settled Currency"] = df["Donation Amount in Project Currency (May be approx.)"]

    col_amount = "Total Online Donations Net Amount in Settled Currency"
    if col_amount not in df.columns:
        col_amount = "Donation Amount in Project Currency (May be approx.)"
    if col_amount not in df.columns:
        col_amount = "Donation Amount (in Donation Currency)"

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

    df = _enrich_dataframe(df)
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

def load_data():
    """Reads from local Parquet binary cache or SQLite database."""
    if os.path.exists(PARQUET_PATH):
        try:
            df = pd.read_parquet(PARQUET_PATH)
            if not df.empty:
                return df
        except Exception:
            pass

    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        df = pd.read_sql_query("SELECT * FROM donations", conn)
        conn.close()
        if not df.empty:
            df.to_parquet(PARQUET_PATH, index=False)
            return df
    except Exception:
        pass

    return pd.DataFrame()
