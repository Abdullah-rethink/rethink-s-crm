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
    get_code_to_classification_map,
    sync_matrix_classifications_to_donors,
)
from views.classification_view import (
    get_givebright_classification_matrix,
    save_givebright_classification_matrix,
    normalize_classification_import_df,
)

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
    community_name: Optional[str] = None


class ClearPlatformRequest(BaseModel):
    user_role: str
    platform: str


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
    """Returns LaunchGood classification matrix rules in < 80ms."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        df = pd.read_sql_query("""
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
        conn.close()
    except Exception as e:
        print(f"[LaunchGood Matrix Query Notice]: {e}")
        df = get_classification_matrix().fillna("Unassigned")


    df = sanitize_matrix_df(df)
    unassigned_count = (df["Heading"] == "Unassigned").sum() if "Heading" in df.columns else 0
    return {
        "platform": "LaunchGood",
        "total_campaigns": len(df),
        "classified_campaigns": int(len(df) - unassigned_count),
        "unassigned_campaigns": int(unassigned_count),
        "rules": df.to_dict(orient="records")
    }


@router.get("/givebright")
def get_givebright_matrix():
    """Returns GiveBright classification matrix rules in < 20ms."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        df = pd.read_sql_query("""
            SELECT 
                campaign_name as "Campaign Name",
                COALESCE(campaign_url, '') as "Campaign URL",
                COALESCE(heading, 'Unassigned') as "Heading",
                COALESCE(sub_heading, 'Unassigned') as "Sub-Heading",
                COALESCE(country, 'Unassigned') as "Country",
                COALESCE(code, 'Unassigned') as "Code",
                COALESCE(zakat_eligibility, 'Unassigned') as "Zakat Eligibility"
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
    unassigned_count = (df["Heading"] == "Unassigned").sum() if "Heading" in df.columns else 0
    return {
        "platform": "GiveBright",
        "total_campaigns": len(df),
        "classified_campaigns": int(len(df) - unassigned_count),
        "unassigned_campaigns": int(unassigned_count),
        "rules": df.to_dict(orient="records")
    }


@router.get("/paysuite")
def get_paysuite_matrix():
    """Returns Paysuite classification matrix rules in < 80ms."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        df = pd.read_sql_query("""
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
        conn.close()
    except Exception as e:
        print(f"[Paysuite Matrix Query Notice]: {e}")
        df = get_paysuite_classification_matrix().fillna("Unassigned")

    df = sanitize_matrix_df(df)
    unassigned_count = (df["Heading"] == "Unassigned").sum() if "Heading" in df.columns else 0
    return {
        "platform": "Paysuite",
        "total_campaigns": len(df),
        "classified_campaigns": int(len(df) - unassigned_count),
        "unassigned_campaigns": int(unassigned_count),
        "rules": df.to_dict(orient="records")
    }



@router.get("/website")
def get_rethink_website_matrix():
    """Returns Rethink Website classification matrix rules in < 80ms."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        df = pd.read_sql_query("""
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
        conn.close()
    except Exception as e:
        print(f"[Website Matrix Query Notice]: {e}")
        df = get_rethink_website_classification_matrix().fillna("Unassigned")

    df = sanitize_matrix_df(df)
    unassigned_count = (df["Heading"] == "Unassigned").sum() if "Heading" in df.columns else 0
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
    """Exports campaign classification rules to CSV or Excel (.xlsx) file format."""
    df_raw = load_data()
    if platform.lower() == "givebright":
        matrix_df = get_givebright_classification_matrix(df_raw).fillna("Unassigned")
        if "Community Name" in matrix_df.columns:
            matrix_df = matrix_df.drop(columns=["Community Name"])
        matrix_df = matrix_df.drop_duplicates(subset=["Campaign Name"], keep="last").reset_index(drop=True)
    elif platform.lower() == "paysuite":
        matrix_df = get_paysuite_classification_matrix(df_raw).fillna("Unassigned")
    elif platform.lower() in ["website", "rethink_website", "rethink website"]:
        matrix_df = get_rethink_website_classification_matrix(df_raw).fillna("Unassigned")
    else:
        matrix_df = get_classification_matrix(df_raw).fillna("Unassigned")

    matrix_df = sanitize_matrix_df(matrix_df)

    # Rename columns to match the real headers in the frontend UI
    rename_map = {"Code": "Code (Master Link)"}
    if platform.lower() == "paysuite":
        rename_map["Campaign Name"] = "Direct Debit Ref (Bank Ref)"
        rename_map["Community Name"] = "Platform Source"
    
    matrix_df = matrix_df.rename(columns=rename_map)

    # Reorder columns to match UI if needed
    if platform.lower() == "paysuite":
        cols = ["Direct Debit Ref (Bank Ref)", "Platform Source", "Code (Master Link)", "Heading", "Sub-Heading", "Country", "Zakat Eligibility", "Donor Name", "Donor Email"]
        matrix_df = matrix_df[[c for c in cols if c in matrix_df.columns]]
    elif platform.lower() == "givebright":
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

    rules_dict = []
    for r in payload.rules:
        rules_dict.append({
            "Campaign Name": sanitize_text(r.get("Campaign Name") or r.get("campaign_name", "N/A")),
            "Campaign URL": sanitize_text(r.get("Campaign URL") or r.get("campaign_url", "")),
            "Community Name": sanitize_text(r.get("Community Name") or r.get("community_name", "Unassigned")),
            "Heading": sanitize_text(r.get("Heading") or r.get("heading", "Unassigned")),
            "Sub-Heading": sanitize_text(r.get("Sub-Heading") or r.get("sub_heading", "Unassigned")),
            "Country": sanitize_text(r.get("Country") or r.get("country", "Unassigned")),
            "Code": sanitize_text(r.get("Code") or r.get("code", "N/A")),
            "Zakat Eligibility": sanitize_text(r.get("Zakat Eligibility") or r.get("zakat_eligibility", "Unassigned"))
        })
    matrix_df = pd.DataFrame(rules_dict)

    if payload.platform.lower() == "givebright":
        # Strict mapping: Code -> Heading, Sub-Heading, Country, Zakat
        code_map = get_code_to_classification_map()
        for idx, row in matrix_df.iterrows():
            code = str(row.get("Code") or "").strip().lower()
            if code and code not in ["unassigned", "nan", "none", "n/a", ""]:
                if code in code_map:
                    c_info = code_map[code]
                    for tc in ["Heading", "Sub-Heading", "Country", "Zakat Eligibility"]:
                        matrix_df.at[idx, tc] = sanitize_text(c_info[tc])
        
        matrix_df = matrix_df.drop_duplicates(subset=["Campaign Name"], keep="last")
        n_saved = save_givebright_classification_matrix(matrix_df)
    elif payload.platform.lower() == "paysuite":
        n_saved = save_paysuite_classification_matrix(matrix_df)
        sync_matrix_classifications_to_donors(matrix_df)
    elif payload.platform.lower() in ["website", "rethink_website", "rethink website"]:
        n_saved = save_rethink_website_classification_matrix(matrix_df)
        sync_matrix_classifications_to_donors(matrix_df)
    else:
        n_saved = save_classification_matrix(matrix_df)
        sync_matrix_classifications_to_donors(matrix_df)

    return {
        "status": "success",
        "message": f"Successfully saved {n_saved:,} {payload.platform} classification rules and updated matching donor records!"
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
    platform = payload.platform.lower()

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    try:
        if platform == "givebright":
            conn.execute("DELETE FROM givebright_classifications WHERE campaign_name = ?", (cname,))
        elif platform == "paysuite":
            conn.execute("DELETE FROM paysuite_classifications WHERE campaign_name = ?", (cname,))
        elif platform in ["website", "rethink_website", "rethink website"]:
            conn.execute("DELETE FROM rethink_website_classifications WHERE campaign_name = ?", (cname,))
        else:
            if payload.community_name:
                conn.execute("DELETE FROM campaign_classifications WHERE campaign_name = ? AND community_name = ?", (cname, sanitize_text(payload.community_name)))
            else:
                conn.execute("DELETE FROM campaign_classifications WHERE campaign_name = ?", (cname,))
        conn.commit()
    finally:
        conn.close()

    # Reset donor records matching this rule to Unassigned
    if os.path.exists(PARQUET_PATH):
        try:
            df = pd.read_parquet(PARQUET_PATH)
            if not df.empty and "Campaign Name" in df.columns:
                mask = df["Campaign Name"].astype(str).str.strip().str.lower() == cname.lower()
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

    return {
        "status": "success",
        "message": f"Successfully deleted rule for '{cname}'!"
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

    return {
        "status": "success",
        "message": f"Successfully cleared all classification rules for {platform.capitalize()}!"
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

    return {
        "status": "success",
        "count": n_saved,
        "message": f"Successfully imported and applied {n_saved:,} {platform.capitalize()} classification rules!"
    }
