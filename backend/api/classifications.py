import io
import os
import sqlite3
from datetime import datetime
from typing import List, Optional
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel

from config.settings import LOCAL_DB_PATH, PARQUET_PATH
from core.data_processor import (
    get_classification_matrix,
    load_data,
    save_classification_matrix,
    get_paysuite_classification_matrix,
    save_paysuite_classification_matrix,
    get_rethink_website_classification_matrix,
    save_rethink_website_classification_matrix,
    get_givebright_classification_matrix,
    save_givebright_classification_matrix,
    normalize_classification_import_df,
    get_code_to_classification_map,
    sync_matrix_classifications_to_donors,
)
try:
    from backend.api.payouts import invalidate_payouts_cache
except ImportError:
    try:
        from api.payouts import invalidate_payouts_cache
    except ImportError:
        def invalidate_payouts_cache():
            pass

router = APIRouter(prefix="/api/classifications", tags=["Campaign Classifications"])


def sanitize_text(val):
    """Repairs common UTF-8 mojibake and strips zero-width/soft-hyphen characters."""
    if not isinstance(val, str) or pd.isna(val):
        return val
    s = str(val).strip()
    try:
        if any(c in s for c in ["Ä", "Ã", "â", "\xad"]):
            s = s.encode("latin1").decode("utf-8")
    except Exception:
        pass
    s = s.replace("\xad", "").replace("\u200b", "").replace("\ufeff", "")
    return s


def sanitize_matrix_df(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized sanitizer for matrix tables in < 2ms."""
    if df.empty:
        return df
    clean_df = df.copy()
    for col in clean_df.columns:
        if clean_df[col].dtype == object or pd.api.types.is_string_dtype(clean_df[col]):
            clean_df[col] = (
                clean_df[col]
                .astype(str)
                .str.strip()
                .str.replace("\xad", "", regex=False)
                .str.replace("\u200b", "", regex=False)
                .str.replace("\ufeff", "", regex=False)
                .str.replace("AshbÄ\xad", "Ashbā", regex=False)
                .str.replace("AshbÄ", "Ashbā", regex=False)
            )
    return clean_df



class SaveRulesRequest(BaseModel):
    user_role: str
    platform: str  # "launchgood", "givebright", or "paysuite"
    rules: List[dict]
    can_edit_matrix: Optional[bool] = False


class DeleteRuleRequest(BaseModel):
    user_role: str
    platform: str
    campaign_name: str
    code: Optional[str] = None
    community_name: Optional[str] = None


class ClearPlatformRequest(BaseModel):
    user_role: str
    platform: str


def _enrich_rules_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """Enriches rules DataFrame with variants_count, status ('single_code' | 'multi_code' | 'unassigned'), and is_primary boolean flag."""
    if df.empty:
        return df

    # Normalize column is_primary
    if "is_primary" not in df.columns:
        df["is_primary"] = 0

    # Count distinct valid codes per campaign name
    c_series = df["Campaign Name"].astype(str).str.strip().str.lower()
    code_series = df["Code"].astype(str).str.strip().str.upper()

    camp_code_map = {}
    for c_name, c_code in zip(c_series, code_series):
        if c_name not in ["nan", "none", "n/a", ""]:
            if c_name not in camp_code_map:
                camp_code_map[c_name] = set()
            if c_code not in ["UNASSIGNED", "N/A", "NONE", "NAN", ""]:
                camp_code_map[c_name].add(c_code)

    variants_counts = []
    statuses = []
    is_primary_flags = []
    seen_camps_primary = set()

    for idx, row in df.iterrows():
        c_name = str(row.get("Campaign Name") or "").strip().lower()
        c_code = str(row.get("Code") or "").strip().upper()
        h_val = str(row.get("Heading") or "").strip().lower()

        distinct_codes = camp_code_map.get(c_name, set())
        v_count = len(distinct_codes)
        variants_counts.append(v_count)

        if h_val in ["unassigned", "nan", "none", ""] or c_code in ["UNASSIGNED", "N/A", "NONE", "NAN", ""]:
            statuses.append("unassigned")
        elif v_count > 1:
            statuses.append("multi_code")
        else:
            statuses.append("single_code")

        # Determine is_primary flag
        raw_prim = row.get("is_primary")
        is_prim = bool(raw_prim in [1, True, "1", "true", "True"])
        if is_prim:
            is_primary_flags.append(True)
            seen_camps_primary.add(c_name)
        elif c_name not in seen_camps_primary and c_code not in ["UNASSIGNED", "N/A", "NONE", "NAN", ""]:
            is_primary_flags.append(True)
            seen_camps_primary.add(c_name)
        else:
            is_primary_flags.append(False)

    df["variants_count"] = variants_counts
    df["status"] = statuses
    df["is_primary"] = is_primary_flags
    return df


@router.get("/campaign-codes")
def get_campaign_codes_lookup(platform: str = "all"):
    """
    Returns a fast lookup mapping every Campaign Name to its list of valid code variant objects:
    { "ashbal orphanage": [ { "code": "GAZ-SPN-ORP", "heading": "Orphans", "sub_heading": "Gaza Orphan Sponsorship", "country": "Palestine", "zakat_eligibility": "Zakat", "is_primary": true } ] }
    """
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    tables = ["campaign_classifications", "givebright_classifications", "paysuite_classifications", "rethink_website_classifications"]
    if platform.lower() == "launchgood":
        tables = ["campaign_classifications"]
    elif platform.lower() == "givebright":
        tables = ["givebright_classifications"]
    elif platform.lower() == "paysuite":
        tables = ["paysuite_classifications"]
    elif platform.lower() in ["website", "rethink_website"]:
        tables = ["rethink_website_classifications"]

    lookup = {}
    try:
        for tbl in tables:
            try:
                df = pd.read_sql_query(f"SELECT * FROM {tbl}", conn)
                for _, r in df.iterrows():
                    c_name = sanitize_text(r.get("campaign_name", ""))
                    c_code = sanitize_text(r.get("code", "Unassigned"))
                    if not c_name or c_name.lower() in ["unassigned", "n/a", "none", "nan", ""]:
                        continue
                    if not c_code or c_code.lower() in ["unassigned", "n/a", "none", "nan", ""]:
                        continue
                    
                    c_key = c_name.strip().lower()
                    if c_key not in lookup:
                        lookup[c_key] = []
                    
                    is_prim = bool(r.get("is_primary") in [1, True, "1", "true", "True"])
                    
                    if not any(item["code"].upper() == c_code.upper() for item in lookup[c_key]):
                        lookup[c_key].append({
                            "campaign_name": c_name,
                            "code": c_code.upper(),
                            "heading": sanitize_text(r.get("heading", "Unassigned")),
                            "sub_heading": sanitize_text(r.get("sub_heading", "Unassigned")),
                            "country": sanitize_text(r.get("country", "Unassigned")),
                            "zakat_eligibility": sanitize_text(r.get("zakat_eligibility", "Unassigned")),
                            "is_primary": is_prim
                        })
            except Exception:
                pass
    finally:
        conn.close()

    return lookup


@router.get("/code-map")
def get_code_map():
    """Returns the central mapping of Code -> {Heading, Sub-Heading, Country, Zakat Eligibility}."""
    raw_map = get_code_to_classification_map()
    clean_map = {}
    for code, info in raw_map.items():
        clean_map[code.strip().lower()] = {
            "Heading": sanitize_text(info.get("Heading", "Unassigned")),
            "Sub-Heading": sanitize_text(info.get("Sub-Heading", "Unassigned")),
            "Country": sanitize_text(info.get("Country", "Unassigned")),
            "Zakat Eligibility": sanitize_text(info.get("Zakat Eligibility", "Unassigned"))
        }
    return clean_map


@router.get("/launchgood")
def get_launchgood_matrix():
    """Returns LaunchGood classification matrix rules with (Campaign Name, Code) granularity."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        df = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(campaign_url, '') as "Campaign URL",
                COALESCE(community_name, 'N/A') as "Community Name",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility",
                COALESCE(is_primary, 0) as "is_primary"
            FROM campaign_classifications
        """, conn)
        conn.close()
    except Exception as e:
        print(f"[LaunchGood Matrix Query Notice]: {e}")
        df = get_classification_matrix().fillna("Unassigned")

    df = sanitize_matrix_df(df)
    df = _enrich_rules_metadata(df)
    unassigned_count = (df["status"] == "unassigned").sum() if "status" in df.columns else 0
    return {
        "platform": "LaunchGood",
        "total_campaigns": len(df),
        "classified_campaigns": int(len(df) - unassigned_count),
        "unassigned_campaigns": int(unassigned_count),
        "rules": df.to_dict(orient="records")
    }


@router.get("/givebright")
def get_givebright_matrix():
    """Returns GiveBright classification matrix rules with (Campaign Name, Code) granularity."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        df = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(campaign_url, '') as "Campaign URL",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility",
                COALESCE(is_primary, 0) as "is_primary"
            FROM givebright_classifications
        """, conn)
        conn.close()
    except Exception as e:
        print(f"[GiveBright Matrix Query Notice]: {e}")
        df = get_givebright_classification_matrix().fillna("Unassigned")

    # Strict mapping: Code -> Heading, Sub-Heading, Country, Zakat Eligibility
    code_map = get_code_to_classification_map()
    if code_map and "Code" in df.columns:
        code_clean = df["Code"].astype(str).str.strip().str.lower()
        for tc in ["Heading", "Sub-Heading", "Country", "Zakat Eligibility"]:
            if tc in df.columns:
                target_map = {k: v[tc] for k, v in code_map.items() if tc in v and v[tc] != "Unassigned"}
                mask_unassigned = df[tc].astype(str).str.strip().str.lower().isin(["", "unassigned", "nan", "none"])
                mapped_vals = code_clean.map(target_map)
                fill_mask = mask_unassigned & mapped_vals.notna()
                if fill_mask.any():
                    df.loc[fill_mask, tc] = mapped_vals[fill_mask]

    df = sanitize_matrix_df(df)
    df = _enrich_rules_metadata(df)
    unassigned_count = (df["status"] == "unassigned").sum() if "status" in df.columns else 0
    return {
        "platform": "GiveBright",
        "total_campaigns": len(df),
        "classified_campaigns": int(len(df) - unassigned_count),
        "unassigned_campaigns": int(unassigned_count),
        "rules": df.to_dict(orient="records")
    }


@router.get("/paysuite")
def get_paysuite_matrix():
    """Returns Paysuite classification matrix rules with (Campaign Name, Code) granularity."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        df = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(community_name, 'N/A') as "Community Name",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility",
                COALESCE(donor_name, '') as "Donor Name",
                COALESCE(donor_email, '') as "Donor Email",
                COALESCE(is_primary, 0) as "is_primary"
            FROM paysuite_classifications
        """, conn)
        conn.close()
    except Exception as e:
        print(f"[Paysuite Matrix Query Notice]: {e}")
        df = get_paysuite_classification_matrix().fillna("Unassigned")

    df = sanitize_matrix_df(df)
    df = _enrich_rules_metadata(df)
    unassigned_count = (df["status"] == "unassigned").sum() if "status" in df.columns else 0
    return {
        "platform": "Paysuite",
        "total_campaigns": len(df),
        "classified_campaigns": int(len(df) - unassigned_count),
        "unassigned_campaigns": int(unassigned_count),
        "rules": df.to_dict(orient="records")
    }



@router.get("/website")
def get_rethink_website_matrix():
    """Returns Rethink Website classification matrix rules with (Campaign Name, Code) granularity."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        df = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(community_name, 'N/A') as "Community Name",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility",
                COALESCE(is_primary, 0) as "is_primary"
            FROM rethink_website_classifications
        """, conn)
        conn.close()
    except Exception as e:
        print(f"[Website Matrix Query Notice]: {e}")
        df = get_rethink_website_classification_matrix().fillna("Unassigned")

    df = sanitize_matrix_df(df)
    df = _enrich_rules_metadata(df)
    unassigned_count = (df["status"] == "unassigned").sum() if "status" in df.columns else 0
    return {
        "platform": "Rethink Website",
        "total_campaigns": len(df),
        "classified_campaigns": int(len(df) - unassigned_count),
        "unassigned_campaigns": int(unassigned_count),
        "rules": df.to_dict(orient="records")
    }


@router.get("/export")
def export_classifications(
    platform: str = Query("launchgood", pattern="^(launchgood|givebright|paysuite|website|rethink_website)$"),
    format: str = Query("csv", pattern="^(csv|xlsx)$")
):
    """Exports active campaign classification matrix rules matching the UI exactly to CSV or Excel (.xlsx)."""
    p_clean = platform.lower().strip()
    if p_clean == "givebright":
        res = get_givebright_matrix()
    elif p_clean == "paysuite":
        res = get_paysuite_matrix()
    elif p_clean in ["website", "rethink_website", "rethink website"]:
        res = get_rethink_website_matrix()
    else:
        res = get_launchgood_matrix()

    matrix_df = pd.DataFrame(res.get("rules", []))
    if matrix_df.empty:
        raise HTTPException(status_code=400, detail="No classification rules available to export.")

    matrix_df = sanitize_matrix_df(matrix_df)

    # Rename columns to match the real headers in the frontend UI
    rename_map = {"Code": "Code (Master Link)"}
    if p_clean == "paysuite":
        rename_map["Campaign Name"] = "Direct Debit Ref (Bank Ref)"
        rename_map["Community Name"] = "Platform Source"
    
    matrix_df = matrix_df.rename(columns=rename_map)

    # Reorder columns to match UI exactly
    if p_clean == "paysuite":
        cols = ["Direct Debit Ref (Bank Ref)", "Platform Source", "Code (Master Link)", "Heading", "Sub-Heading", "Country", "Zakat Eligibility", "Donor Name", "Donor Email"]
        matrix_df = matrix_df[[c for c in cols if c in matrix_df.columns]]
    elif p_clean == "givebright":
        cols = ["Campaign Name", "Campaign URL", "Code (Master Link)", "Heading", "Sub-Heading", "Country", "Zakat Eligibility"]
        matrix_df = matrix_df[[c for c in cols if c in matrix_df.columns]]
    else:
        cols = ["Campaign Name", "Community Name", "Code (Master Link)", "Heading", "Sub-Heading", "Country", "Zakat Eligibility"]
        matrix_df = matrix_df[[c for c in cols if c in matrix_df.columns]]

    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    if format.lower() == "xlsx":
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            matrix_df.to_excel(writer, index=False, sheet_name=f"{platform.capitalize()} Rules")
        buffer.seek(0)
        headers = {"Content-Disposition": f'attachment; filename="classifications_{platform}_{date_str}.xlsx"'}
        return Response(
            content=buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )
    else:
        csv_bytes = matrix_df.to_csv(index=False).encode('utf-8-sig')
        headers = {"Content-Disposition": f'attachment; filename="classifications_{platform}_{date_str}.csv"'}
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers=headers
        )


@router.post("/save")
def save_matrix_rules(payload: SaveRulesRequest):
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Modifying campaign classification matrix rules is restricted to Super Admin accounts."
        )

    # 1. Collect non-unassigned classification metadata for every Code from submitted payload and existing map
    code_map = get_code_to_classification_map(force_reload=True).copy()
    
    for r in payload.rules:
        code_str = str(r.get("Code") or r.get("code") or "").strip().lower()
        if code_str and code_str not in ["unassigned", "nan", "none", "n/a", ""]:
            h = sanitize_text(r.get("Heading") or r.get("heading", "Unassigned"))
            sh = sanitize_text(r.get("Sub-Heading") or r.get("sub_heading", "Unassigned"))
            c = sanitize_text(r.get("Country") or r.get("country", "Unassigned"))
            z = sanitize_text(r.get("Zakat Eligibility") or r.get("zakat_eligibility", "Unassigned"))

            if any(v != "Unassigned" for v in [h, sh, c, z]):
                if code_str not in code_map:
                    code_map[code_str] = {"Heading": "Unassigned", "Sub-Heading": "Unassigned", "Country": "Unassigned", "Zakat Eligibility": "Unassigned"}
                if h != "Unassigned": code_map[code_str]["Heading"] = h
                if sh != "Unassigned": code_map[code_str]["Sub-Heading"] = sh
                if c != "Unassigned": code_map[code_str]["Country"] = c
                if z != "Unassigned": code_map[code_str]["Zakat Eligibility"] = z

    # 2. Build DataFrame and auto-fill any row that has a recognized Code
    rules_dict = []
    for r in payload.rules:
        code_raw = sanitize_text(r.get("Code") or r.get("code", "Unassigned"))
        code_lower = code_raw.strip().lower()
        
        h = sanitize_text(r.get("Heading") or r.get("heading", "Unassigned"))
        sh = sanitize_text(r.get("Sub-Heading") or r.get("sub_heading", "Unassigned"))
        c = sanitize_text(r.get("Country") or r.get("country", "Unassigned"))
        z = sanitize_text(r.get("Zakat Eligibility") or r.get("zakat_eligibility", "Unassigned"))

        if code_lower in code_map:
            c_info = code_map[code_lower]
            if h == "Unassigned" and c_info.get("Heading") != "Unassigned": h = c_info["Heading"]
            if sh == "Unassigned" and c_info.get("Sub-Heading") != "Unassigned": sh = c_info["Sub-Heading"]
            if c == "Unassigned" and c_info.get("Country") != "Unassigned": c = c_info["Country"]
            if z == "Unassigned" and c_info.get("Zakat Eligibility") != "Unassigned": z = c_info["Zakat Eligibility"]

        d_name = sanitize_text(r.get("Donor Name") or r.get("donor_name", ""))
        d_email = sanitize_text(r.get("Donor Email") or r.get("donor_email", ""))

        rules_dict.append({
            "Campaign Name": sanitize_text(r.get("Campaign Name") or r.get("campaign_name", "N/A")),
            "Campaign URL": sanitize_text(r.get("Campaign URL") or r.get("campaign_url", "")),
            "Community Name": sanitize_text(r.get("Community Name") or r.get("community_name", "Unassigned")),
            "Donor Name": d_name,
            "Donor Email": d_email,
            "Heading": h,
            "Sub-Heading": sh,
            "Country": c,
            "Code": code_raw,
            "Zakat Eligibility": z,
            "is_primary": 1 if r.get("is_primary") in [1, True, "1", "true", "True"] else 0
        })
    matrix_df = pd.DataFrame(rules_dict)

    if payload.platform.lower() == "givebright":
        matrix_df = matrix_df.drop_duplicates(subset=["Campaign Name", "Code"], keep="last")
        n_saved = save_givebright_classification_matrix(matrix_df)
    elif payload.platform.lower() == "paysuite":
        matrix_df = matrix_df.drop_duplicates(subset=["Campaign Name", "Code"], keep="last")
        n_saved = save_paysuite_classification_matrix(matrix_df)
        sync_matrix_classifications_to_donors(matrix_df)
    elif payload.platform.lower() in ["website", "rethink_website", "rethink website"]:
        matrix_df = matrix_df.drop_duplicates(subset=["Campaign Name", "Code"], keep="last")
        n_saved = save_rethink_website_classification_matrix(matrix_df)
        sync_matrix_classifications_to_donors(matrix_df)
    else:
        matrix_df = matrix_df.drop_duplicates(subset=["Campaign Name", "Code"], keep="last")
        n_saved = save_classification_matrix(matrix_df)
        sync_matrix_classifications_to_donors(matrix_df)

    # Reload central code dictionary after save
    get_code_to_classification_map(force_reload=True)
    invalidate_payouts_cache()

    try:
        from backend.api.expenses import clear_expenses_cache
        clear_expenses_cache()
        from backend.api.events import broadcast_event_sync
        broadcast_event_sync("MATRIX_UPDATED", {"platform": payload.platform})
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Successfully saved {n_saved:,} {payload.platform} classification rules and updated matching records in real time!"
    }


@router.post("/delete-rule")
def delete_single_rule(payload: DeleteRuleRequest):
    """Deletes a single classification rule (Super Admin only)."""
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Deleting classification rules is restricted to Super Admin accounts."
        )

    cname = sanitize_text(payload.campaign_name.strip())
    code = sanitize_text(payload.code.strip()) if payload.code else None
    platform = payload.platform.lower()

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    try:
        tbl = (
            "givebright_classifications" if platform == "givebright" else
            "paysuite_classifications" if platform == "paysuite" else
            "rethink_website_classifications" if platform in ["website", "rethink_website", "rethink website"] else
            "campaign_classifications"
        )
        if code:
            conn.execute(f"DELETE FROM {tbl} WHERE campaign_name = ? AND code = ?", (cname, code))
        else:
            conn.execute(f"DELETE FROM {tbl} WHERE campaign_name = ?", (cname,))
        conn.commit()
    finally:
        conn.close()

    # Reset donor records matching this rule to Unassigned
    if os.path.exists(PARQUET_PATH):
        try:
            df = pd.read_parquet(PARQUET_PATH)
            if not df.empty and "Campaign Name" in df.columns:
                mask = df["Campaign Name"].astype(str).str.strip().str.lower() == cname.lower()
                if code and "Code" in df.columns:
                    mask = mask & (df["Code"].astype(str).str.strip().str.lower() == code.lower())
                if payload.community_name and "Community Name" in df.columns:
                    mask = mask & (df["Community Name"].astype(str).str.strip().str.lower() == payload.community_name.strip().lower())
                
                for f in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
                    if f in df.columns:
                        df.loc[mask, f] = "Unassigned"
                
                df.to_parquet(PARQUET_PATH, index=False)
                conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                df.to_sql("donations", con=conn, if_exists="replace", index=False)
                conn.close()
        except Exception as e:
            print(f"Error updating donors on delete: {e}")

    invalidate_payouts_cache()
    try:
        from backend.api.expenses import clear_expenses_cache
        clear_expenses_cache()
        from backend.api.events import broadcast_event_sync
        broadcast_event_sync("MATRIX_UPDATED", {"platform": payload.platform, "action": "delete"})
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Successfully deleted rule for '{cname}' ({code or 'all codes'})"
    }


@router.post("/clear-platform")
def clear_platform_rules(payload: ClearPlatformRequest):
    """Completely wipes classification rules for a platform (Super Admin only)."""
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wiping classification rules is restricted to Super Admin accounts."
        )

    platform = payload.platform.lower()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    try:
        if platform == "givebright":
            conn.execute("DELETE FROM givebright_classifications;")
        elif platform == "paysuite":
            conn.execute("DELETE FROM paysuite_classifications;")
        elif platform in ["website", "rethink_website", "rethink website"]:
            conn.execute("DELETE FROM rethink_website_classifications;")
        else:
            conn.execute("DELETE FROM campaign_classifications;")
        conn.commit()
    finally:
        conn.close()

    # Reset platform donor records to Unassigned
    if os.path.exists(PARQUET_PATH):
        try:
            df = pd.read_parquet(PARQUET_PATH)
            if not df.empty and "Platform" in df.columns:
                p_mask = df["Platform"].astype(str).str.lower() == platform
                if platform == "launchgood":
                    p_mask = p_mask | (df["Platform"].astype(str).str.lower().isin(["", "none", "nan"]))
                
                for f in ["Heading", "Sub-Heading", "Country", "Code", "Zakat Eligibility"]:
                    if f in df.columns:
                        df.loc[p_mask, f] = "Unassigned"
                
                df.to_parquet(PARQUET_PATH, index=False)
                conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
                df.to_sql("donations", con=conn, if_exists="replace", index=False)
                conn.close()
        except Exception as e:
            print(f"Error resetting donors on clear: {e}")

    invalidate_payouts_cache()
    try:
        from backend.api.expenses import clear_expenses_cache
        clear_expenses_cache()
        from backend.api.events import broadcast_event_sync
        broadcast_event_sync("MATRIX_UPDATED", {"platform": payload.platform, "action": "clear"})
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Successfully wiped all classification rules and reset matching donor records for platform: {payload.platform}"
    }


@router.post("/import")
async def import_classification_file(
    file: UploadFile = File(...),
    platform: str = Form("launchgood"),
    user_role: str = Form("admin"),
    mode: str = Form("merge")
):
    """Bulk uploads and applies a classification file (.csv or .xlsx) (Super Admin only)."""
    if user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bulk uploading classification files is restricted to Super Admin accounts."
        )

    contents = await file.read()
    try:
        if file.filename.lower().endswith(".csv"):
            raw_df = pd.read_csv(io.BytesIO(contents))
        else:
            raw_df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse uploaded file: {str(e)}")

    norm_df = normalize_classification_import_df(raw_df)
    norm_df = sanitize_matrix_df(norm_df)
    platform_clean = platform.lower()

    if mode == "merge":
        if platform_clean == "givebright":
            existing = get_givebright_classification_matrix().fillna("Unassigned")
            merged = pd.concat([existing, norm_df], ignore_index=True).drop_duplicates(subset=["Campaign Name"], keep="last")
        elif platform_clean == "paysuite":
            existing = get_paysuite_classification_matrix().fillna("Unassigned")
            merged = pd.concat([existing, norm_df], ignore_index=True).drop_duplicates(subset=["Campaign Name", "Community Name"], keep="last")
        else:
            existing = get_classification_matrix().fillna("Unassigned")
            merged = pd.concat([existing, norm_df], ignore_index=True).drop_duplicates(subset=["Campaign Name", "Community Name"], keep="last")
    else:
        merged = norm_df

    if platform_clean == "givebright":
        # Strict mapping: Code -> Heading, Sub-Heading, Country, Zakat
        code_map = get_code_to_classification_map()
        for idx, row in merged.iterrows():
            code = str(row.get("Code") or "").strip().lower()
            if code and code not in ["unassigned", "nan", "none", "n/a", ""]:
                if code in code_map:
                    c_info = code_map[code]
                    for tc in ["Heading", "Sub-Heading", "Country", "Zakat Eligibility"]:
                        merged.at[idx, tc] = sanitize_text(c_info[tc])

        merged = merged.drop_duplicates(subset=["Campaign Name"], keep="last")
        n_saved = save_givebright_classification_matrix(merged)
    elif platform_clean == "paysuite":
        n_saved = save_paysuite_classification_matrix(merged)
        sync_matrix_classifications_to_donors(merged)
    else:
        n_saved = save_classification_matrix(merged)
        sync_matrix_classifications_to_donors(merged)

    invalidate_payouts_cache()

    return {
        "status": "success",
        "count": n_saved,
        "message": f"Successfully imported and applied {n_saved:,} {platform.capitalize()} classification rules!"
    }
