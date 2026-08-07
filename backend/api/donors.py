import io
import math
import sqlite3
from datetime import datetime
from typing import List, Optional
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel

from config.settings import LOCAL_DB_PATH, PARQUET_PATH
from core.data_processor import load_data, sync_donor_classifications_to_matrix

router = APIRouter(prefix="/api/donors", tags=["Donors & Explorer"])


class BulkEditDonorsRequest(BaseModel):
    user_role: str
    target_columns: List[str]
    new_values: List[str]
    filter_search: Optional[str] = ""
    filter_payment_type: Optional[str] = None
    filter_tier: Optional[str] = None
    filter_source: Optional[str] = None
    filter_heading: Optional[str] = None
    filter_subheading: Optional[str] = None
    filter_country: Optional[str] = None
    filter_code: Optional[str] = None
    filter_zakat: Optional[str] = None
    filter_donor_country: Optional[str] = None
    filter_campaign_search: Optional[str] = None
    filter_gift_aid: Optional[str] = None
    can_edit_donors: Optional[bool] = False


@router.post("/bulk-edit")
def bulk_edit_donors(payload: BulkEditDonorsRequest):
    if payload.user_role != "super_admin" and not payload.can_edit_donors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editing donor records is restricted to authorized accounts."
        )

    df_raw = load_data()
    if df_raw.empty:
        raise HTTPException(status_code=400, detail="Donor dataset is empty.")

    # 1. Apply global filters to scope target dataframe
    filtered_df = _apply_filters(
        df_raw,
        payload.filter_payment_type,
        payload.filter_tier,
        payload.filter_source,
        payload.filter_heading,
        payload.filter_subheading,
        payload.filter_country,
        payload.filter_code,
        payload.filter_zakat,
        payload.filter_donor_country,
        payload.filter_campaign_search,
        payload.filter_gift_aid
    )

    # 2. Apply search filter
    if payload.filter_search and str(payload.filter_search).strip():
        term = str(payload.filter_search).strip().lower()
        search_cols = [c for c in ["First Name", "Last Name", "Display Name", "Email", "Campaign Name", "Community Name"] if c in filtered_df.columns]
        mask = pd.Series(False, index=filtered_df.index)
        for sc in search_cols:
            mask = mask | filtered_df[sc].astype(str).str.lower().str.contains(term, na=False)
        filtered_df = filtered_df.loc[mask]

    matching_indices = filtered_df.index
    if len(matching_indices) == 0:
        return {"status": "success", "message": "No matching records found to edit."}

    for col, val in zip(payload.target_columns, payload.new_values):
        if col and col in df_raw.columns:
            df_raw.loc[matching_indices, col] = val

    df_raw.to_parquet(PARQUET_PATH, index=False)
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    df_raw.to_sql("donations", con=conn, if_exists="replace", index=False)
    conn.close()

    from core.database import sync_to_cloud_async
    sync_to_cloud_async(df_raw, mode="replace")

    return {
        "status": "success",
        "message": f"Successfully updated {len(matching_indices):,} donor record(s)."
    }


def _apply_filters(df, payment_type=None, tier=None, source=None, heading=None, subheading=None, country=None, code=None, zakat=None, donor_country=None, campaign_search=None, gift_aid=None):
    if df.empty:
        return df
    filtered_df = df.copy()

    if payment_type and payment_type != "All Payment Types" and "Payment Frequency" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Payment Frequency"] == payment_type]

    if tier and tier != "All Classifications" and "Lifetime Donor Classification" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Lifetime Donor Classification"] == tier]

    if source and source != "All Sources (Combined)" and "Source" in filtered_df.columns:
        sources_list = [s.strip() for s in str(source).split(",") if s.strip()]
        if sources_list:
            filtered_df = filtered_df[filtered_df["Source"].isin(sources_list)]

    if heading and heading != "All Headings" and "Heading" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Heading"].astype(str).str.strip() == heading]

    if subheading and subheading != "All Sub-Headings" and "Sub-Heading" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Sub-Heading"].astype(str).str.strip() == subheading]

    if country and country != "All Project Countries" and "Country" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Country"].astype(str).str.contains(country, case=False, regex=False, na=False)]

    if code and code != "All Codes" and "Code" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Code"].astype(str).str.strip() == code]

    if zakat and zakat != "All Zakat Status" and "Zakat Eligibility" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Zakat Eligibility"].astype(str).str.strip() == zakat]

    if donor_country and donor_country != "All Donor Countries":
        for dc_col in ["Donor Country", "Billing Country", "Country Code"]:
            if dc_col in filtered_df.columns:
                filtered_df = filtered_df[filtered_df[dc_col].astype(str).str.contains(donor_country, case=False, regex=False, na=False)]
                break

    if campaign_search and str(campaign_search).strip():
        term = str(campaign_search).strip().lower()
        c_mask = pd.Series(False, index=filtered_df.index)
        for cs_col in ["Campaign Name", "Community Name"]:
            if cs_col in filtered_df.columns:
                c_mask = c_mask | filtered_df[cs_col].astype(str).str.lower().str.contains(term, na=False)
        filtered_df = filtered_df[c_mask]

    if gift_aid and gift_aid != "All Gift Aid Status":
        ga_col = "Gift Aid (yes or no)" if "Gift Aid (yes or no)" in filtered_df.columns else ("is_giftaid" if "is_giftaid" in filtered_df.columns else None)
        if ga_col:
            val_str = str(gift_aid).strip().lower()
            if val_str in ["yes", "1", "true"]:
                filtered_df = filtered_df[filtered_df[ga_col].astype(str).str.lower().isin(["yes", "1", "1.0", "true"])]
            elif val_str in ["no", "0", "false"]:
                filtered_df = filtered_df[filtered_df[ga_col].astype(str).str.lower().isin(["no", "0", "0.0", "false"])]

    return filtered_df


@router.get("")
def get_donors_paginated(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    search: Optional[str] = "",
    payment_type: Optional[str] = None,
    tier: Optional[str] = None,
    source: Optional[str] = None,
    heading: Optional[str] = None,
    subheading: Optional[str] = None,
    country: Optional[str] = None,
    code: Optional[str] = None,
    zakat: Optional[str] = None,
    donor_country: Optional[str] = None,
    campaign_search: Optional[str] = None,
    gift_aid: Optional[str] = None
):
    """Returns paginated donor records using direct SQL queries on SQLite for maximum performance and low RAM usage."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='donations'")
        if cursor.fetchone():
            where_clauses = []
            params = []

            if payment_type and payment_type != "All Payment Types":
                where_clauses.append('"Payment Frequency" = ?')
                params.append(payment_type)

            if tier and tier != "All Classifications":
                where_clauses.append('"Lifetime Donor Classification" = ?')
                params.append(tier)

            if source and source != "All Sources (Combined)":
                where_clauses.append('"Source" = ?')
                params.append(source)

            if heading and heading != "All Headings":
                where_clauses.append('"Heading" = ?')
                params.append(heading)

            if subheading and subheading != "All Sub-Headings":
                where_clauses.append('"Sub-Heading" = ?')
                params.append(subheading)

            if country and country != "All Project Countries":
                where_clauses.append('"Country" = ?')
                params.append(country)

            if code and code != "All Codes":
                where_clauses.append('"Code" = ?')
                params.append(code)

            if zakat and zakat != "All Zakat Status":
                where_clauses.append('"Zakat Eligibility" = ?')
                params.append(zakat)

            if donor_country and donor_country != "All Donor Countries":
                where_clauses.append('("Donor Country" LIKE ? OR "Billing Country" LIKE ? OR "Country Code" LIKE ?)')
                pattern = f"%{donor_country}%"
                params.extend([pattern, pattern, pattern])

            if campaign_search and str(campaign_search).strip():
                term = f"%{str(campaign_search).strip()}%"
                where_clauses.append('("Campaign Name" LIKE ? OR "Community Name" LIKE ?)')
                params.extend([term, term])

            if gift_aid and gift_aid != "All Gift Aid Status":
                where_clauses.append('("Gift Aid (yes or no)" LIKE ? OR "is_giftaid" = ?)')
                params.extend([f"%{gift_aid}%", 1 if gift_aid.lower() == "yes" else 0])

            if search and search.strip():
                term = f"%{search.strip()}%"
                search_parts = ['"First Name" LIKE ?', '"Last Name" LIKE ?', '"Display Name" LIKE ?', '"Email" LIKE ?', '"Campaign Name" LIKE ?', '"Community Name" LIKE ?']
                where_clauses.append(f"({' OR '.join(search_parts)})")
                params.extend([term] * len(search_parts))

            where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            # Count matching records
            count_sql = f"SELECT COUNT(*) FROM donations{where_sql}"
            cursor.execute(count_sql, params)
            total_records = cursor.fetchone()[0]

            total_pages = max(1, math.ceil(total_records / page_size))
            page = min(page, total_pages)
            offset = (page - 1) * page_size

            # Query requested page with LIMIT & OFFSET
            query_sql = f"SELECT * FROM donations{where_sql} LIMIT ? OFFSET ?"
            query_params = params + [page_size, offset]
            page_df = pd.read_sql_query(query_sql, conn, params=query_params)
            
            cursor.execute("PRAGMA table_info(donations)")
            avail_cols = [col[1] for col in cursor.fetchall()]
            conn.close()

            float_cols = page_df.select_dtypes(include=['float', 'float64']).columns
            for fc in float_cols:
                page_df[fc] = page_df[fc].round(2)

            page_df = page_df.fillna("")
            records = page_df.to_dict(orient="records")

            return {
                "total_records": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "available_columns": avail_cols,
                "records": records
            }
        conn.close()
    except Exception as e:
        print(f"SQL Pagination fallback notice: {e}")

    df_raw = load_data()
    if df_raw.empty:
        return {
            "total_records": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "donors": []
        }

    filtered_df = _apply_filters(df_raw, payment_type, tier, source, heading, subheading, country, code, zakat, donor_country, campaign_search)
    display_df = filtered_df

    if search and search.strip():
        term = search.strip().lower()
        search_cols_avail = [c for c in ["First Name", "Last Name", "Display Name", "Email", "Campaign Name", "Community Name"] if c in display_df.columns]
        mask = pd.Series(False, index=display_df.index)
        for sc in search_cols_avail:
            mask = mask | display_df[sc].astype(str).str.lower().str.contains(term, na=False)
        display_df = display_df.loc[mask]

    total_records = len(display_df)
    total_pages = max(1, math.ceil(total_records / page_size))
    page = min(page, total_pages)

    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_records)

    page_df = display_df.iloc[start_idx:end_idx].copy()
    float_cols = page_df.select_dtypes(include=['float', 'float64']).columns
    for fc in float_cols:
        page_df[fc] = page_df[fc].round(2)

    page_df = page_df.fillna("")
    records = page_df.to_dict(orient="records")

    return {
        "total_records": total_records,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "available_columns": df_raw.columns.tolist(),
        "records": records
    }


@router.get("/export")
def export_donors(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    search: Optional[str] = "",
    payment_type: Optional[str] = None,
    tier: Optional[str] = None,
    source: Optional[str] = None,
    heading: Optional[str] = None,
    subheading: Optional[str] = None,
    country: Optional[str] = None,
    code: Optional[str] = None,
    zakat: Optional[str] = None,
    donor_country: Optional[str] = None,
    campaign_search: Optional[str] = None,
    gift_aid: Optional[str] = None
):
    """Exports filtered donor rows to CSV or Excel (.xlsx) file format."""
    df_raw = load_data()
    if df_raw.empty:
        raise HTTPException(status_code=400, detail="No donor data available to export.")

    filtered_df = _apply_filters(df_raw, payment_type, tier, source, heading, subheading, country, code, zakat, donor_country, campaign_search, gift_aid)
    display_df = filtered_df

    if search and search.strip():
        term = search.strip().lower()
        search_cols_avail = [c for c in ["First Name", "Last Name", "Display Name", "Email", "Campaign Name", "Community Name"] if c in display_df.columns]
        mask = pd.Series(False, index=display_df.index)
        for sc in search_cols_avail:
            mask = mask | display_df[sc].astype(str).str.lower().str.contains(term, na=False)
        display_df = display_df.loc[mask]

    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    if format.lower() == "xlsx":
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            display_df.to_excel(writer, index=False, sheet_name="Filtered Donors")
        buffer.seek(0)
        headers = {"Content-Disposition": f'attachment; filename="filtered_donors_{date_str}.xlsx"'}
        return Response(
            content=buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )
    else:
        csv_bytes = display_df.to_csv(index=False).encode('utf-8-sig')
        headers = {"Content-Disposition": f'attachment; filename="filtered_donors_{date_str}.csv"'}
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers=headers
        )


@router.get("/kanban")
def get_donors_kanban(
    payment_type: Optional[str] = None,
    tier: Optional[str] = None,
    source: Optional[str] = None,
    heading: Optional[str] = None,
    subheading: Optional[str] = None,
    country: Optional[str] = None,
    code: Optional[str] = None,
    zakat: Optional[str] = None,
    donor_country: Optional[str] = None,
    campaign_search: Optional[str] = None,
    gift_aid: Optional[str] = None
):
    """Returns donor cards grouped by LTV Tier for the Kanban Pipeline Board with column total sums."""
    df_raw = load_data()
    df = _apply_filters(df_raw, payment_type, tier, source, heading, subheading, country, code, zakat, donor_country, campaign_search, gift_aid)

    if df.empty or "Lifetime Donor Classification" not in df.columns:
        return {}

    # Pre-calculate true cumulative LTV & total transaction count for all donors across the entire dataset!
    col_amount = "Total Online Donations Net Amount in Settled Currency"
    if col_amount not in df_raw.columns:
        col_amount = "Donation Amount in Project Currency (May be approx.)"

    group_col = "Email" if "Email" in df_raw.columns else "Display Name"
    df_raw_copy = df_raw.copy()
    df_raw_copy["_clean_key"] = df_raw_copy[group_col].astype(str).str.strip().str.lower()
    donor_overall_stats = df_raw_copy.groupby("_clean_key").agg(
        true_ltv=(col_amount, "sum"),
        true_count=(col_amount, "count")
    ).to_dict(orient="index")

    tiers = ["Low End", "Medium Low", "Medium", "High", "Super High"]
    kanban_data = {}
    for t in tiers:
        t_df = df[df["Lifetime Donor Classification"] == t]
        
        # Calculate Total Sum Amount for the Column Header!
        total_sum_amount = float(t_df[col_amount].sum()) if (not t_df.empty and col_amount in t_df.columns) else 0.0

        if not t_df.empty:
            donor_summary = t_df.groupby(group_col).agg(
                name=("Display Name", "first") if "Display Name" in t_df.columns else (group_col, "first"),
                email=("Email", "first") if "Email" in t_df.columns else (group_col, "first"),
                tier=("Lifetime Donor Classification", "first"),
                txn_tier=("Transaction Donor Classification", "first") if "Transaction Donor Classification" in t_df.columns else ("Lifetime Donor Classification", "first")
            ).reset_index()

            records = []
            for _, r in donor_summary.head(30).iterrows():
                r_name = str(r["name"]) if (pd.notna(r["name"]) and str(r["name"]).strip().lower() not in ["nan", "none", "null"]) else "Anonymous Donor"
                r_email = str(r["email"]) if (pd.notna(r["email"]) and str(r["email"]).strip().lower() not in ["nan", "none", "null"]) else ""
                r_tier = str(r["tier"]) if (pd.notna(r["tier"]) and str(r["tier"]).strip().lower() not in ["nan", "none", "null"]) else "Unassigned"
                r_txntier = str(r["txn_tier"]) if (pd.notna(r["txn_tier"]) and str(r["txn_tier"]).strip().lower() not in ["nan", "none", "null"]) else "Unassigned"
                
                clean_key = r_email.strip().lower() if r_email else r_name.strip().lower()
                st = donor_overall_stats.get(clean_key, {})
                records.append({
                    "name": r_name,
                    "email": r_email,
                    "total_ltv": round(float(st.get("true_ltv", 0.0)), 2) if st else 0.0,
                    "donation_count": int(st.get("true_count", 1)) if st else 1,
                    "tier": r_tier,
                    "txn_tier": r_txntier
                })
            cards = records
        else:
            cards = []

        kanban_data[t] = {
            "tier_name": t,
            "total_donors": len(t_df),
            "total_sum_amount": round(total_sum_amount, 2),
            "cards": cards
        }

    return kanban_data


@router.get("/profile/{donor_id_or_email:path}")
def get_donor_360_profile(donor_id_or_email: str):
    """Returns complete 360° Donor Profile payload with all donor details, dual classifications, and full transaction history."""
    df = load_data()
    if df.empty:
        raise HTTPException(status_code=404, detail="Donor dataset is empty.")

    identity = donor_id_or_email.strip().lower()
    
    match_mask = pd.Series(False, index=df.index)
    for col in ["Email", "Donor ID", "Display Name", "First Name", "Last Name"]:
        if col in df.columns:
            match_mask = match_mask | (df[col].astype(str).str.strip().str.lower() == identity)

    donor_txns = df.loc[match_mask]
    if donor_txns.empty:
        raise HTTPException(status_code=404, detail=f"Donor '{donor_id_or_email}' not found.")

    col_amount = "Total Online Donations Net Amount in Settled Currency"
    if col_amount not in df.columns:
        col_amount = "Donation Amount in Project Currency (May be approx.)"

    first_row = donor_txns.iloc[0]
    total_ltv = float(donor_txns[col_amount].sum()) if col_amount in donor_txns.columns else 0.0
    avg_donation = float(donor_txns[col_amount].mean()) if col_amount in donor_txns.columns else 0.0

    # Dual Classification: Lifetime Donor Tier AND Transaction Donor Tier!
    lifetime_tier = str(first_row.get("Lifetime Donor Classification", "Unassigned"))
    transaction_tier = str(first_row.get("Transaction Donor Classification", "Unassigned"))

    # Extract all details
    details = {
        "donor_id": str(first_row.get("Donor ID", "N/A")),
        "display_name": str(first_row.get("Display Name", "N/A")),
        "first_name": str(first_row.get("First Name", "N/A")),
        "last_name": str(first_row.get("Last Name", "N/A")),
        "email": str(first_row.get("Email", "N/A")),
        "phone": str(first_row.get("Phone", "N/A")),
        
        # Dual Classification Tiers
        "lifetime_tier": lifetime_tier,
        "transaction_tier": transaction_tier,

        # Billing & Address Details
        "billing_address_1": str(first_row.get("Billing Address Line 1", first_row.get("Billing Address", "N/A"))),
        "billing_address_2": str(first_row.get("Billing Address 2", "N/A")),
        "billing_city": str(first_row.get("Billing City", "N/A")),
        "billing_state": str(first_row.get("Billing State", "N/A")),
        "billing_postcode": str(first_row.get("Billing Post Code", first_row.get("Billing Zip", "N/A"))),
        "billing_country": str(first_row.get("Billing Country", "N/A")),

        # Financial Summary
        "total_ltv": round(total_ltv, 2),
        "avg_donation": round(avg_donation, 2),
        "total_donations_count": len(donor_txns),

        # Marketing, Tax & Metadata
        "marketing_consent": str(first_row.get("Marketing Consent", "N/A")),
        "gift_aid": str(first_row.get("Gift Aid (yes or no)", "N/A")),
        "tax_receipt_requested": str(first_row.get("Tax Receipt requested", "N/A")),
        "anonymous_public": str(first_row.get("Anonymous or Public", "N/A")),

        # Payment Details
        "payment_frequency": str(first_row.get("Payment Frequency", "N/A")),
        "payment_type": str(first_row.get("Payment Type", "N/A")),
        "settlement_currency": str(first_row.get("Settlement Currency", "N/A")),
        "source": str(first_row.get("Source", "N/A")),
        "platform": str(first_row.get("Platform", "N/A"))
    }

    # Format complete transaction timeline
    timeline_cols = [c for c in [
        "Created Date (UTC)", "Campaign Name", "Heading", "Sub-Heading", 
        "Donation Currency (DC)", "Donation Amount (in Donation Currency)", 
        col_amount, "Payment Frequency", "Source"
    ] if c in donor_txns.columns]

    timeline_df = donor_txns[timeline_cols].copy()
    timeline_df = timeline_df.fillna("N/A")
    if col_amount in timeline_df.columns:
        timeline_df[col_amount] = pd.to_numeric(timeline_df[col_amount], errors='coerce').fillna(0.0).round(2)

    history = timeline_df.to_dict(orient="records")

    # Payment breakdown by Heading & Sub-Heading
    category_breakdown = []
    if "Heading" in donor_txns.columns:
        col_sub = "Sub-Heading" if "Sub-Heading" in donor_txns.columns else "Heading"
        donor_txns_copy = donor_txns.copy()
        donor_txns_copy["Heading"] = donor_txns_copy["Heading"].fillna("Unassigned")
        donor_txns_copy[col_sub] = donor_txns_copy[col_sub].fillna("Unassigned")
        
        b_df = donor_txns_copy.groupby(["Heading", col_sub])[col_amount].agg(["sum", "count"]).reset_index()
        b_df.columns = ["heading", "subheading", "total_amount", "count"]
        b_df["total_amount"] = pd.to_numeric(b_df["total_amount"], errors='coerce').fillna(0.0).round(2)
        b_df["percentage"] = (b_df["total_amount"] / total_ltv * 100).round(1) if total_ltv > 0 else 0.0
        b_df = b_df.sort_values(by="total_amount", ascending=False)
        category_breakdown = b_df.to_dict(orient="records")

    details["history"] = history
    details["category_breakdown"] = category_breakdown
    return details
