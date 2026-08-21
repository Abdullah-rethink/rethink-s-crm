import os
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from config.settings import LOCAL_DB_PATH, PARQUET_PATH, PAYOUTS_PARQUET_PATH
from core.data_processor import load_data, load_payouts_data, get_code_to_classification_map
from backend.api.events import broadcast_event_sync

router = APIRouter(prefix="/api/fundraisers", tags=["Fundraiser Tracking"])


def init_fundraiser_db():
    """Initializes fundraisers and fundraiser_campaigns SQLite tables."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fundraisers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                target_goal REAL DEFAULT 0.0,
                start_date TEXT DEFAULT '',
                status TEXT DEFAULT 'ACTIVE',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fundraiser_campaigns (
                id TEXT PRIMARY KEY,
                fundraiser_id TEXT NOT NULL,
                campaign_name TEXT NOT NULL,
                code TEXT NOT NULL DEFAULT 'ALL',
                platform TEXT DEFAULT 'ALL',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (fundraiser_id) REFERENCES fundraisers(id) ON DELETE CASCADE
            );
        """)
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Fundraiser DB init notice: {e}")


init_fundraiser_db()


class CampaignAssignment(BaseModel):
    campaign_name: str
    code: Optional[str] = "ALL"
    platform: Optional[str] = "ALL"


class CreateFundraiserRequest(BaseModel):
    user_role: str
    can_edit_donors: Optional[bool] = False
    name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    target_goal: Optional[float] = 0.0
    start_date: Optional[str] = ""
    status: Optional[str] = "ACTIVE"
    notes: Optional[str] = ""
    assigned_campaigns: Optional[List[CampaignAssignment]] = []


class UpdateFundraiserRequest(BaseModel):
    user_role: str
    can_edit_donors: Optional[bool] = False
    name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    target_goal: Optional[float] = 0.0
    start_date: Optional[str] = ""
    status: Optional[str] = "ACTIVE"
    notes: Optional[str] = ""
    assigned_campaigns: Optional[List[CampaignAssignment]] = []


class DeleteFundraiserRequest(BaseModel):
    user_role: str
    can_edit_donors: Optional[bool] = False


def _check_super_admin(user_role: str, can_edit_donors: bool = False):
    """Strictly enforces that only Super Admin accounts can manage fundraisers."""
    role_clean = str(user_role or "").strip().lower()
    if role_clean != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Managing fundraisers is strictly restricted to Super Admin accounts."
        )


def _validate_no_campaign_assignment_conflicts(cur, requested_assignments: List[CampaignAssignment], current_fundraiser_id: Optional[str] = None):
    """
    Enforces that a campaign (or specific campaign code) can ONLY be assigned to ONE fundraiser.
    If a campaign is already assigned to Fundraiser A, Fundraiser B cannot claim it.
    """
    if not requested_assignments:
        return

    cur.execute("""
        SELECT fc.fundraiser_id, fc.campaign_name, fc.code, f.name 
        FROM fundraiser_campaigns fc 
        JOIN fundraisers f ON fc.fundraiser_id = f.id
    """)
    existing = cur.fetchall()

    for req in requested_assignments:
        req_cname = str(req.campaign_name).strip().lower()
        req_code = str(req.code or "ALL").strip().lower()

        for ex_fid, ex_cname, ex_code, ex_fname in existing:
            if current_fundraiser_id and ex_fid == current_fundraiser_id:
                continue  # Re-assigning to the same fundraiser is permitted

            ex_cname_clean = str(ex_cname).strip().lower()
            ex_code_clean = str(ex_code or "ALL").strip().lower()

            if req_cname == ex_cname_clean:
                # Check for overlap: either one claims 'ALL' or specific codes match
                if req_code in ["all", "", "unassigned"] or ex_code_clean in ["all", "", "unassigned"] or req_code == ex_code_clean:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Campaign '{req.campaign_name}' (Code: {req.code or 'ALL'}) is already assigned to fundraiser '{ex_fname}'. A campaign can only be assigned to one fundraiser."
                    )


@router.get("/campaigns-list")
def get_available_campaigns_list():
    """
    Returns unique list of all (Campaign Name, Code, Platform, Heading) combinations
    across donations, payout settlements, and all 4 classification tables in real-time,
    along with assignment status indicating which fundraiser (if any) currently owns the campaign.
    """
    init_fundraiser_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    cur = conn.cursor()
    
    unique_pairs = set()
    campaign_items = []

    try:
        # Fetch existing assignments map
        cur.execute("""
            SELECT fc.fundraiser_id, fc.campaign_name, fc.code, f.name 
            FROM fundraiser_campaigns fc 
            JOIN fundraisers f ON fc.fundraiser_id = f.id
        """)
        assigned_map = {}
        for fid, cname, code, fname in cur.fetchall():
            cname_key = str(cname).strip().lower()
            code_key = str(code or "ALL").strip().lower()
            assigned_map[(cname_key, code_key)] = {
                "fundraiser_id": fid,
                "fundraiser_name": fname,
                "code": code
            }

        # 1. From donations cached dataset
        try:
            df_don = load_data()
            if df_don is not None and not df_don.empty and "Campaign Name" in df_don.columns:
                target_cols = [c for c in ["Campaign Name", "Code", "Platform", "Heading", "Sub-Heading", "Country"] if c in df_don.columns]
                df_unique = df_don[df_don["Campaign Name"].notna() & (df_don["Campaign Name"].astype(str).str.strip() != "")][target_cols].drop_duplicates(subset=["Campaign Name", "Code"] if "Code" in target_cols else ["Campaign Name"])
                for _, r in df_unique.iterrows():
                    cname_str = str(r.get("Campaign Name") or "").strip()
                    code_str = str(r.get("Code") or "Unassigned").strip() if "Code" in r else "Unassigned"
                    plat_str = str(r.get("Platform") or "LaunchGood").strip() if "Platform" in r else "LaunchGood"
                    head = str(r.get("Heading") or "Unassigned").strip() if "Heading" in r else "Unassigned"
                    subhead = str(r.get("Sub-Heading") or "Unassigned").strip() if "Sub-Heading" in r else "Unassigned"
                    country = str(r.get("Country") or "Unassigned").strip() if "Country" in r else "Unassigned"
                    key = (cname_str.lower(), code_str.lower())
                    if key not in unique_pairs and cname_str:
                        unique_pairs.add(key)
                        assigned_info = assigned_map.get(key) or assigned_map.get((cname_str.lower(), "all"))

                        campaign_items.append({
                            "campaign_name": cname_str,
                            "code": code_str,
                            "platform": plat_str,
                            "heading": head,
                            "sub_heading": subhead,
                            "country": country,
                            "is_assigned": bool(assigned_info),
                            "assigned_to": assigned_info
                        })
        except Exception as e:
            print(f"[Fundraiser Campaign List Notice]: {e}")

        # 2. From payout_settlements table
        try:
            cur.execute("""
                SELECT DISTINCT 
                    [Campaign Name], 
                    COALESCE(Code, 'Unassigned'), 
                    'LaunchGood Payout', 
                    COALESCE(Heading, 'Unassigned'),
                    COALESCE([Sub-Heading], 'Unassigned'),
                    COALESCE(Country, 'Unassigned')
                FROM payout_settlements 
                WHERE [Campaign Name] IS NOT NULL AND TRIM([Campaign Name]) != ''
            """)
            for cname, code, plat, head, subhead, country in cur.fetchall():
                cname_str = str(cname).strip()
                code_str = str(code).strip() if code else "Unassigned"
                key = (cname_str.lower(), code_str.lower())
                if key not in unique_pairs and cname_str:
                    unique_pairs.add(key)
                    assigned_info = assigned_map.get(key) or assigned_map.get((cname_str.lower(), "all"))

                    campaign_items.append({
                        "campaign_name": cname_str,
                        "code": code_str,
                        "platform": "LaunchGood Payout",
                        "heading": str(head or "Unassigned"),
                        "sub_heading": str(subhead or "Unassigned"),
                        "country": str(country or "Unassigned"),
                        "is_assigned": bool(assigned_info),
                        "assigned_to": assigned_info
                    })
        except Exception:
            pass

        # 3. From all 4 classification matrix tables
        matrix_tables = [
            ("campaign_classifications", "LaunchGood"),
            ("givebright_classifications", "GiveBright"),
            ("paysuite_classifications", "Paysuite"),
            ("rethink_website_classifications", "Rethink Website")
        ]
        for tbl, plat_name in matrix_tables:
            try:
                cur.execute(f"""
                    SELECT DISTINCT 
                        campaign_name, 
                        COALESCE(code, 'Unassigned'), 
                        heading, 
                        sub_heading, 
                        country 
                    FROM {tbl} 
                    WHERE campaign_name IS NOT NULL AND TRIM(campaign_name) != ''
                """)
                for cname, code, head, subhead, country in cur.fetchall():
                    cname_str = str(cname).strip()
                    code_str = str(code).strip() if code else "Unassigned"
                    key = (cname_str.lower(), code_str.lower())
                    if key not in unique_pairs and cname_str:
                        unique_pairs.add(key)
                        assigned_info = assigned_map.get(key) or assigned_map.get((cname_str.lower(), "all"))

                        campaign_items.append({
                            "campaign_name": cname_str,
                            "code": code_str,
                            "platform": plat_name,
                            "heading": str(head or "Unassigned"),
                            "sub_heading": str(subhead or "Unassigned"),
                            "country": str(country or "Unassigned"),
                            "is_assigned": bool(assigned_info),
                            "assigned_to": assigned_info
                        })
            except Exception:
                pass
    finally:
        conn.close()

    campaign_items.sort(key=lambda x: (x["campaign_name"].lower(), x["code"].lower()))
    return campaign_items


@router.get("")
def get_fundraisers_list(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status_filter: Optional[str] = "ALL"
):
    """
    Returns list of all fundraisers with live aggregated metrics across donations and payouts.
    Calculates total raised all-time, total raised in period ('since Z date'), progress %, donor counts.
    """
    status_clean = str(status_filter or "ALL").strip().upper()
    if status_clean in ["NONE", "", "NAN", "UNDEFINED"]:
        status_clean = "ALL"

    init_fundraiser_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        # 1. Fetch fundraisers
        query = "SELECT * FROM fundraisers"
        params = []
        if status_clean != "ALL":
            query += " WHERE status = ?"
            params.append(status_clean)
        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
        fundraiser_rows = [dict(r) for r in cur.fetchall()]

        # 2. Fetch campaign assignments for all fundraisers
        cur.execute("SELECT fundraiser_id, campaign_name, code, platform FROM fundraiser_campaigns")
        assignments = cur.fetchall()
        f_campaign_map = {}
        for r in assignments:
            fid = r["fundraiser_id"]
            if fid not in f_campaign_map:
                f_campaign_map[fid] = []
            f_campaign_map[fid].append({
                "campaign_name": r["campaign_name"],
                "code": r["code"],
                "platform": r["platform"]
            })
    finally:
        conn.close()

    if not fundraiser_rows:
        return {
            "summary": {
                "total_fundraisers": 0,
                "total_raised_all_time": 0.0,
                "total_raised_period": 0.0,
                "total_target_goal": 0.0,
                "overall_progress_pct": 0.0,
                "total_donors": 0,
                "total_transactions": 0
            },
            "fundraisers": []
        }

    # 3. Load live transaction data from donations and payouts
    df_donations = load_data()
    df_payouts = load_payouts_data()

    # Clean dates for filtering
    for df in [df_donations, df_payouts]:
        if df is not None and not df.empty:
            if "Created Date (UTC)" in df.columns:
                df["_parsed_date"] = pd.to_datetime(df["Created Date (UTC)"], errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
            else:
                df["_parsed_date"] = ""

    amount_col = "Total Online Donations Net Amount in Settled Currency"

    fundraisers_result = []
    total_raised_all_time_sum = 0.0
    total_raised_period_sum = 0.0
    total_target_goal_sum = 0.0
    global_donor_emails = set()
    total_txns_sum = 0

    for f in fundraiser_rows:
        fid = f["id"]
        c_list = f_campaign_map.get(fid, [])
        target_goal = float(f.get("target_goal") or 0.0)
        f_start_date = str(f.get("start_date") or "").strip()

        # Build mask for assigned campaigns
        f_donations_sub = pd.DataFrame()
        f_payouts_sub = pd.DataFrame()

        if c_list:
            # Donations match
            if df_donations is not None and not df_donations.empty and "Campaign Name" in df_donations.columns:
                don_masks = []
                cname_series = df_donations["Campaign Name"].astype(str).str.strip().str.lower()
                code_series = df_donations.get("Code", pd.Series("", index=df_donations.index)).astype(str).str.strip().str.lower()

                for c_item in c_list:
                    target_cname = str(c_item["campaign_name"]).strip().lower()
                    target_code = str(c_item.get("code") or "ALL").strip().lower()
                    
                    if target_code in ["all", "", "unassigned"]:
                        don_masks.append(cname_series == target_cname)
                    else:
                        don_masks.append((cname_series == target_cname) & (code_series == target_code))

                if don_masks:
                    combined_mask = don_masks[0]
                    for m in don_masks[1:]:
                        combined_mask = combined_mask | m
                    f_donations_sub = df_donations[combined_mask]

            # Payouts match
            if df_payouts is not None and not df_payouts.empty and "Campaign Name" in df_payouts.columns:
                pay_masks = []
                p_cname_series = df_payouts["Campaign Name"].astype(str).str.strip().str.lower()
                p_code_series = df_payouts.get("Code", pd.Series("", index=df_payouts.index)).astype(str).str.strip().str.lower()

                for c_item in c_list:
                    target_cname = str(c_item["campaign_name"]).strip().lower()
                    target_code = str(c_item.get("code") or "ALL").strip().lower()

                    if target_code in ["all", "", "unassigned"]:
                        pay_masks.append(p_cname_series == target_cname)
                    else:
                        pay_masks.append((p_cname_series == target_cname) & (p_code_series == target_code))

                if pay_masks:
                    combined_pmask = pay_masks[0]
                    for m in pay_masks[1:]:
                        combined_pmask = combined_pmask | m
                    f_payouts_sub = df_payouts[combined_pmask]

        # Calculate All-time Raised
        all_time_raised = 0.0
        donor_emails = set()
        txn_count = 0
        first_donation_date = None
        latest_donation_date = None

        if not f_donations_sub.empty:
            if amount_col in f_donations_sub.columns:
                all_time_raised += float(pd.to_numeric(f_donations_sub[amount_col], errors="coerce").fillna(0.0).sum())
            txn_count += len(f_donations_sub)
            if "Email" in f_donations_sub.columns:
                valid_emails = f_donations_sub["Email"].dropna().astype(str).str.strip().str.lower()
                valid_emails = valid_emails[~valid_emails.isin(["", "nan", "none", "n/a"])]
                donor_emails.update(valid_emails)
            
            # Find true first and latest donation dates from donor data
            if "_parsed_date" in f_donations_sub.columns:
                valid_dates = f_donations_sub["_parsed_date"].dropna()
                valid_dates = valid_dates[valid_dates != ""]
                if not valid_dates.empty:
                    first_donation_date = str(valid_dates.min())
                    latest_donation_date = str(valid_dates.max())

        # Inception date: Priority 1 is first donation date from data, Priority 2 is stored start_date
        inception_date = first_donation_date or f_start_date or "N/A"

        # Calculate Period Raised (from Date X to Date Y)
        is_custom_filtered = bool(start_date or end_date)
        period_raised = all_time_raised
        period_txns = txn_count
        period_donors = len(donor_emails)

        if is_custom_filtered:
            if not f_donations_sub.empty and "_parsed_date" in f_donations_sub.columns:
                date_mask = pd.Series(True, index=f_donations_sub.index)
                if start_date:
                    date_mask = date_mask & (f_donations_sub["_parsed_date"] >= start_date)
                if end_date:
                    date_mask = date_mask & (f_donations_sub["_parsed_date"] <= end_date)
                
                period_sub = f_donations_sub[date_mask]
                period_raised = float(pd.to_numeric(period_sub[amount_col], errors="coerce").fillna(0.0).sum()) if amount_col in period_sub.columns else 0.0
                period_txns = len(period_sub)
                if "Email" in period_sub.columns:
                    p_emails = period_sub["Email"].dropna().astype(str).str.strip().str.lower()
                    p_emails = p_emails[~p_emails.isin(["", "nan", "none", "n/a"])]
                    period_donors = len(set(p_emails))
                else:
                    period_donors = 0
            else:
                period_raised = 0.0
                period_txns = 0
                period_donors = 0

        # Progress calculation
        progress_pct = round((all_time_raised / target_goal * 100.0), 1) if target_goal > 0 else (100.0 if all_time_raised > 0 else 0.0)
        period_progress_pct = round((period_raised / target_goal * 100.0), 1) if target_goal > 0 else 0.0
        avg_donation = round(all_time_raised / txn_count, 2) if txn_count > 0 else 0.0

        fundraiser_obj = {
            "id": fid,
            "name": f.get("name", "Unnamed"),
            "email": f.get("email", ""),
            "phone": f.get("phone", ""),
            "target_goal": round(target_goal, 2),
            "first_donation_date": first_donation_date or "N/A",
            "latest_donation_date": latest_donation_date or "N/A",
            "inception_date": inception_date,
            "start_date": inception_date,
            "status": f.get("status", "ACTIVE"),
            "notes": f.get("notes", ""),
            "created_at": f.get("created_at", ""),
            "assigned_campaigns": c_list,
            "total_raised_all_time": round(all_time_raised, 2),
            "total_raised_period": round(period_raised, 2),
            "is_custom_filtered": is_custom_filtered,
            "filter_start_date": start_date or "",
            "filter_end_date": end_date or "",
            "progress_percentage": min(progress_pct, 999.9),
            "period_progress_percentage": min(period_progress_pct, 999.9),
            "total_donors": len(donor_emails),
            "period_donors": period_donors,
            "total_donations_count": txn_count,
            "period_donations_count": period_txns,
            "avg_donation": avg_donation
        }

        fundraisers_result.append(fundraiser_obj)
        total_raised_all_time_sum += all_time_raised
        total_raised_period_sum += period_raised
        total_target_goal_sum += target_goal
        global_donor_emails.update(donor_emails)
        total_txns_sum += txn_count

    overall_progress = round((total_raised_all_time_sum / total_target_goal_sum * 100.0), 1) if total_target_goal_sum > 0 else 0.0

    return {
        "summary": {
            "total_fundraisers": len(fundraiser_rows),
            "total_raised_all_time": round(total_raised_all_time_sum, 2),
            "total_raised_period": round(total_raised_period_sum, 2),
            "total_target_goal": round(total_target_goal_sum, 2),
            "overall_progress_pct": min(overall_progress, 999.9),
            "total_donors": len(global_donor_emails),
            "total_transactions": total_txns_sum,
            "is_custom_filtered": bool(start_date or end_date),
            "filter_start_date": start_date or "",
            "filter_end_date": end_date or ""
        },
        "fundraisers": fundraisers_result
    }


@router.get("/{fundraiser_id}")
def get_fundraiser_detail(
    fundraiser_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Returns deep drilldown for a single fundraiser:
    individual campaign breakdown, monthly timeline, and recent transaction log,
    with support for filtering by date range (start_date to end_date).
    """
    init_fundraiser_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM fundraisers WHERE id = ?", (fundraiser_id,))
        f_row = cur.fetchone()
        if not f_row:
            raise HTTPException(status_code=404, detail="Fundraiser not found.")
        fundraiser = dict(f_row)

        cur.execute("SELECT campaign_name, code, platform FROM fundraiser_campaigns WHERE fundraiser_id = ?", (fundraiser_id,))
        assigned_campaigns = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    df_donations = load_data()
    amount_col = "Total Online Donations Net Amount in Settled Currency"

    campaign_breakdown = []
    recent_transactions = []
    monthly_timeline = {}
    first_donation_date = None
    latest_donation_date = None
    total_raised_all_time = 0.0
    total_raised_period = 0.0

    if assigned_campaigns and df_donations is not None and not df_donations.empty:
        cname_series = df_donations["Campaign Name"].astype(str).str.strip().str.lower()
        code_series = df_donations.get("Code", pd.Series("", index=df_donations.index)).astype(str).str.strip().str.lower()

        # Clean parsed date
        if "Created Date (UTC)" in df_donations.columns:
            df_donations["_parsed_date"] = pd.to_datetime(df_donations["Created Date (UTC)"], errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
        else:
            df_donations["_parsed_date"] = ""

        all_assigned_masks = []
        for c_item in assigned_campaigns:
            cname = str(c_item["campaign_name"]).strip()
            code = str(c_item.get("code") or "ALL").strip()
            
            if code.upper() == "ALL" or not code:
                mask = cname_series == cname.lower()
            else:
                mask = (cname_series == cname.lower()) & (code_series == code.lower())

            all_assigned_masks.append(mask)
            sub_df = df_donations[mask].copy()

            if not sub_df.empty:
                gross_all = float(pd.to_numeric(sub_df[amount_col], errors="coerce").fillna(0.0).sum()) if amount_col in sub_df.columns else 0.0
                total_raised_all_time += gross_all

                # Date filtering for period calculations
                period_sub = sub_df
                if start_date or end_date:
                    d_mask = pd.Series(True, index=sub_df.index)
                    if start_date:
                        d_mask = d_mask & (sub_df["_parsed_date"] >= start_date)
                    if end_date:
                        d_mask = d_mask & (sub_df["_parsed_date"] <= end_date)
                    period_sub = sub_df[d_mask]

                gross_period = float(pd.to_numeric(period_sub[amount_col], errors="coerce").fillna(0.0).sum()) if amount_col in period_sub.columns else 0.0
                total_raised_period += gross_period
                txns = len(period_sub)
                donor_count = len(set(period_sub["Email"].dropna().astype(str).str.strip().str.lower())) if "Email" in period_sub.columns else 0
                
                campaign_breakdown.append({
                    "campaign_name": cname,
                    "code": code,
                    "platform": str(c_item.get("platform") or "ALL"),
                    "gross_raised": round(gross_period, 2),
                    "gross_raised_all_time": round(gross_all, 2),
                    "total_donations": txns,
                    "total_donors": donor_count,
                    "heading": str(sub_df["Heading"].iloc[0]) if "Heading" in sub_df.columns and not sub_df["Heading"].empty and pd.notna(sub_df["Heading"].iloc[0]) else "Unassigned",
                    "country": str(sub_df["Country"].iloc[0]) if "Country" in sub_df.columns and not sub_df["Country"].empty and pd.notna(sub_df["Country"].iloc[0]) else "Unassigned"
                })

                # Monthly aggregation (use full dataset or period)
                if "Created Date (UTC)" in sub_df.columns:
                    dates = pd.to_datetime(sub_df["Created Date (UTC)"], errors="coerce", format="mixed")
                    months = dates.dt.strftime("%Y-%m")
                    for m_val, amt in zip(months, pd.to_numeric(sub_df[amount_col], errors="coerce").fillna(0.0)):
                        if pd.notna(m_val) and m_val != "NaT":
                            monthly_timeline[m_val] = monthly_timeline.get(m_val, 0.0) + float(amt)

                # Recent transactions (sanitize all NaN / nulls for valid JSON serialization)
                if len(recent_transactions) < 50:
                    sample_cols = [c for c in ["Created Date (UTC)", "Donor Name", "First Name", "Last Name", "Email", "Campaign Name", "Code", amount_col, "Platform"] if c in sub_df.columns]
                    tx_sample = period_sub[sample_cols].head(20).to_dict('records')
                    for t in tx_sample:
                        fn = str(t.get("First Name") or "").strip() if pd.notna(t.get("First Name")) else ""
                        ln = str(t.get("Last Name") or "").strip() if pd.notna(t.get("Last Name")) else ""
                        raw_name = t.get("Donor Name")
                        name = str(raw_name).strip() if pd.notna(raw_name) and str(raw_name).strip() else (f"{fn} {ln}".strip() or "Anonymous")
                        
                        email_val = t.get("Email")
                        email_str = str(email_val).strip() if pd.notna(email_val) and str(email_val).strip().lower() not in ["nan", "none", ""] else "N/A"
                        
                        cname_val = t.get("Campaign Name")
                        cname_str = str(cname_val).strip() if pd.notna(cname_val) and str(cname_val).strip() else cname
                        
                        code_val = t.get("Code")
                        code_str = str(code_val).strip() if pd.notna(code_val) and str(code_val).strip() else code
                        
                        plat_val = t.get("Platform")
                        plat_str = str(plat_val).strip() if pd.notna(plat_val) and str(plat_val).strip() else "N/A"
                        
                        amt_val = pd.to_numeric(t.get(amount_col), errors="coerce")
                        amt_num = float(amt_val) if pd.notna(amt_val) else 0.0

                        recent_transactions.append({
                            "date": str(t.get("Created Date (UTC)") or "N/A") if pd.notna(t.get("Created Date (UTC)")) else "N/A",
                            "donor_name": name,
                            "email": email_str,
                            "campaign_name": cname_str,
                            "code": code_str,
                            "amount": round(amt_num, 2),
                            "platform": plat_str
                        })

        # Overall first and latest donation dates
        if all_assigned_masks:
            comb_mask = all_assigned_masks[0]
            for m in all_assigned_masks[1:]:
                comb_mask = comb_mask | m
            all_assigned_df = df_donations[comb_mask]
            if not all_assigned_df.empty and "_parsed_date" in all_assigned_df.columns:
                valid_dates = all_assigned_df["_parsed_date"].dropna()
                valid_dates = valid_dates[valid_dates != ""]
                if not valid_dates.empty:
                    first_donation_date = str(valid_dates.min())
                    latest_donation_date = str(valid_dates.max())

    fundraiser["first_donation_date"] = first_donation_date or "N/A"
    fundraiser["latest_donation_date"] = latest_donation_date or "N/A"
    fundraiser["inception_date"] = first_donation_date or fundraiser.get("start_date") or "N/A"
    fundraiser["total_raised_all_time"] = round(total_raised_all_time, 2)
    fundraiser["total_raised_period"] = round(total_raised_period, 2)

    timeline_sorted = [{"month": k, "amount": round(v, 2)} for k, v in sorted(monthly_timeline.items())]

    return {
        "fundraiser": fundraiser,
        "assigned_campaigns": assigned_campaigns,
        "campaign_breakdown": sorted(campaign_breakdown, key=lambda x: x["gross_raised"], reverse=True),
        "monthly_timeline": timeline_sorted,
        "recent_transactions": recent_transactions[:50]
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_fundraiser(payload: CreateFundraiserRequest):
    """Creates a new fundraiser and assigns campaigns (Super Admin only)."""
    _check_super_admin(payload.user_role, payload.can_edit_donors or False)

    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Fundraiser name is required.")

    fundraiser_id = f"FR-{uuid.uuid4().hex[:8].upper()}"
    init_fundraiser_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cur = conn.cursor()

    try:
        # Enforce that one campaign/code can only be assigned to one fundraiser
        if payload.assigned_campaigns:
            _validate_no_campaign_assignment_conflicts(cur, payload.assigned_campaigns, current_fundraiser_id=None)

        cur.execute("""
            INSERT INTO fundraisers (id, name, email, phone, target_goal, start_date, status, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            fundraiser_id,
            payload.name.strip(),
            payload.email.strip() if payload.email else "",
            payload.phone.strip() if payload.phone else "",
            float(payload.target_goal or 0.0),
            payload.start_date.strip() if payload.start_date else "",
            payload.status.strip().upper() if payload.status else "ACTIVE",
            payload.notes.strip() if payload.notes else ""
        ))

        # Insert campaign assignments
        if payload.assigned_campaigns:
            for c in payload.assigned_campaigns:
                cname = c.campaign_name.strip()
                code = (c.code or "ALL").strip()
                plat = (c.platform or "ALL").strip()
                if cname:
                    cur.execute("""
                        INSERT INTO fundraiser_campaigns (id, fundraiser_id, campaign_name, code, platform, created_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (str(uuid.uuid4()), fundraiser_id, cname, code, plat))

        conn.commit()
    finally:
        conn.close()

    try:
        broadcast_event_sync("FUNDRAISER_UPDATED", {"action": "create", "id": fundraiser_id, "name": payload.name})
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Successfully created fundraiser '{payload.name}'.",
        "fundraiser_id": fundraiser_id
    }


@router.put("/{fundraiser_id}")
def update_fundraiser(fundraiser_id: str, payload: UpdateFundraiserRequest):
    """Updates an existing fundraiser and re-assigns campaigns (Super Admin only)."""
    _check_super_admin(payload.user_role, payload.can_edit_donors or False)

    init_fundraiser_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cur = conn.cursor()

    try:
        cur.execute("SELECT id FROM fundraisers WHERE id = ?", (fundraiser_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Fundraiser not found.")

        # Enforce that one campaign/code can only be assigned to one fundraiser
        if payload.assigned_campaigns:
            _validate_no_campaign_assignment_conflicts(cur, payload.assigned_campaigns, current_fundraiser_id=fundraiser_id)

        cur.execute("""
            UPDATE fundraisers 
            SET name = ?, email = ?, phone = ?, target_goal = ?, start_date = ?, status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            payload.name.strip(),
            payload.email.strip() if payload.email else "",
            payload.phone.strip() if payload.phone else "",
            float(payload.target_goal or 0.0),
            payload.start_date.strip() if payload.start_date else "",
            payload.status.strip().upper() if payload.status else "ACTIVE",
            payload.notes.strip() if payload.notes else "",
            fundraiser_id
        ))

        # Re-assign campaigns: delete old and insert new
        cur.execute("DELETE FROM fundraiser_campaigns WHERE fundraiser_id = ?", (fundraiser_id,))
        if payload.assigned_campaigns:
            for c in payload.assigned_campaigns:
                cname = c.campaign_name.strip()
                code = (c.code or "ALL").strip()
                plat = (c.platform or "ALL").strip()
                if cname:
                    cur.execute("""
                        INSERT INTO fundraiser_campaigns (id, fundraiser_id, campaign_name, code, platform, created_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (str(uuid.uuid4()), fundraiser_id, cname, code, plat))

        conn.commit()
    finally:
        conn.close()

    try:
        broadcast_event_sync("FUNDRAISER_UPDATED", {"action": "update", "id": fundraiser_id, "name": payload.name})
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Successfully updated fundraiser '{payload.name}' and campaign assignments."
    }


@router.delete("/{fundraiser_id}")
def delete_fundraiser(fundraiser_id: str, user_role: str = "guest", can_edit_donors: bool = False):
    """Deletes a fundraiser and all its campaign assignments (Super Admin only)."""
    _check_super_admin(user_role, can_edit_donors)

    init_fundraiser_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cur = conn.cursor()

    try:
        cur.execute("SELECT name FROM fundraisers WHERE id = ?", (fundraiser_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Fundraiser not found.")
        f_name = row[0]

        cur.execute("DELETE FROM fundraiser_campaigns WHERE fundraiser_id = ?", (fundraiser_id,))
        cur.execute("DELETE FROM fundraisers WHERE id = ?", (fundraiser_id,))
        conn.commit()
    finally:
        conn.close()

    try:
        broadcast_event_sync("FUNDRAISER_UPDATED", {"action": "delete", "id": fundraiser_id, "name": f_name})
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Successfully deleted fundraiser '{f_name}'."
    }
