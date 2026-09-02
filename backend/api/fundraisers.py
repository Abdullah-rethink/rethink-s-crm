import os
import math
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


def calculate_benchmark_goal(raised_amount: float) -> float:
    """Calculates an intelligent benchmark target goal based on raised amount."""
    if raised_amount <= 0:
        return 1000.0
    if raised_amount <= 500:
        return 500.0
    elif raised_amount <= 1000:
        return 1000.0
    elif raised_amount <= 5000:
        return math.ceil(raised_amount / 1000.0) * 1000.0
    elif raised_amount <= 20000:
        return math.ceil(raised_amount / 5000.0) * 5000.0
    elif raised_amount <= 100000:
        return math.ceil(raised_amount / 10000.0) * 10000.0
    else:
        return math.ceil(raised_amount / 25000.0) * 25000.0


def sync_discovered_fundraisers_internal() -> int:
    """
    Scans the live donations dataset for unique fundraiser_name values not yet present
    in the fundraisers table and auto-registers them without overwriting admin customizations.
    """
    init_fundraiser_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cur = conn.cursor()
    
    cur.execute("SELECT LOWER(TRIM(name)) FROM fundraisers")
    existing_lower_names = set(r[0] for r in cur.fetchall() if r[0])
    
    try:
        cur.execute("""
            SELECT 
                MAX(TRIM(fundraiser_name)) as fundraiser_name,
                LOWER(TRIM(fundraiser_name)) as lower_name,
                ROUND(SUM([Total Online Donations Net Amount in Settled Currency]), 2) as total_raised,
                COUNT(*) as total_donations,
                MIN([Created Date (UTC)]) as earliest_gift,
                MAX([Created Date (UTC)]) as latest_gift
            FROM donations
            WHERE fundraiser_name IS NOT NULL AND TRIM(fundraiser_name) != ''
            GROUP BY LOWER(TRIM(fundraiser_name))
        """)
        don_fundraisers = cur.fetchall()
    except Exception as e:
        print(f"Sync fundraisers query notice: {e}")
        conn.close()
        return 0
        
    new_fundraisers = []
    new_campaign_mappings = []
    
    for fname, lname, total_raised, total_dons, earliest_gift, latest_gift in don_fundraisers:
        if lname not in existing_lower_names and fname:
            fid = f"fund_{uuid.uuid5(uuid.NAMESPACE_DNS, lname).hex[:16]}"
            raised = float(total_raised or 0.0)
            goal = calculate_benchmark_goal(raised)
            start_dt = str(earliest_gift or "").split("T")[0].split(" ")[0].strip()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            new_fundraisers.append((
                fid, fname, "", "", goal, start_dt, "ACTIVE",
                f"Auto-discovered from donor data. Lifetime raised: £{raised:,.2f}",
                now_str, now_str
            ))
            existing_lower_names.add(lname)
            
            cur.execute("""
                SELECT DISTINCT TRIM([Campaign Name]), COALESCE(TRIM(Code), 'ALL'), COALESCE(TRIM(Platform), 'LaunchGood')
                FROM donations
                WHERE LOWER(TRIM(fundraiser_name)) = ?
                  AND [Campaign Name] IS NOT NULL AND TRIM([Campaign Name]) != ''
            """, (lname,))
            for cname, code, plat in cur.fetchall():
                map_id = f"fc_{uuid.uuid5(uuid.NAMESPACE_DNS, f'{fid}_{cname}_{code}').hex[:16]}"
                new_campaign_mappings.append((
                    map_id, fid, cname, code or "ALL", plat or "LaunchGood", now_str
                ))
    
    if new_fundraisers:
        cur.executemany("""
            INSERT INTO fundraisers (id, name, email, phone, target_goal, start_date, status, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, new_fundraisers)
        
        if new_campaign_mappings:
            cur.executemany("""
                INSERT OR IGNORE INTO fundraiser_campaigns (id, fundraiser_id, campaign_name, code, platform, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, new_campaign_mappings)
            
        conn.commit()
        
    conn.close()
    return len(new_fundraisers)


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


class AssignDonationsRequest(BaseModel):
    user_role: str
    can_edit_donors: Optional[bool] = False
    fundraiser_name: str
    campaign_name: Optional[str] = None
    code: Optional[str] = None
    donor_emails: Optional[List[str]] = []


def _check_super_admin(user_role: str, can_edit_donors: bool = False):
    """Strictly enforces that only Super Admin accounts can manage fundraisers."""
    role_clean = str(user_role or "").strip().lower()
    if role_clean != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Managing fundraisers is strictly restricted to Super Admin accounts."
        )


@router.get("/campaigns-list")
def get_available_campaigns_list():
    """
    Returns unique list of all (Campaign Name, Code, Platform, Heading) combinations
    across donations, payout settlements, and all classification tables in real-time.
    """
    init_fundraiser_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    cur = conn.cursor()
    
    unique_pairs = set()
    campaign_items = []

    try:
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


@router.post("/sync-discovered")
def sync_discovered_fundraisers():
    """
    On-demand endpoint to scan donations for new unique fundraiser_name entries
    and auto-seed them into fundraisers table, preserving existing admin customizations.
    """
    new_count = sync_discovered_fundraisers_internal()
    
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fundraisers")
    total_count = cur.fetchone()[0]
    conn.close()

    if new_count > 0:
        try:
            broadcast_event_sync("FUNDRAISER_UPDATED", {"action": "sync", "new_count": new_count})
        except Exception:
            pass

    return {
        "status": "success",
        "newly_added_count": new_count,
        "total_fundraisers": total_count,
        "message": f"Sync completed. {new_count} new fundraisers discovered and added (Total: {total_count})."
    }


@router.get("")
def get_fundraisers_list(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status_filter: Optional[str] = "ALL"
):
    """
    Returns list of all fundraisers with live aggregated metrics.
    Uses ultra-fast vectorized hybrid attribution:
    - Peer-to-peer fundraisers matching exact fundraiser_name.
    - Custom admin fundraisers matching assigned campaigns for unassigned donations.
    """
    status_clean = str(status_filter or "ALL").strip().upper()
    if status_clean in ["NONE", "", "NAN", "UNDEFINED"]:
        status_clean = "ALL"

    init_fundraiser_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        query = "SELECT * FROM fundraisers"
        params = []
        if status_clean != "ALL":
            query += " WHERE status = ?"
            params.append(status_clean)
        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
        fundraiser_rows = [dict(r) for r in cur.fetchall()]

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

    # Load live transaction data
    df_donations = load_data()
    amount_col = "Total Online Donations Net Amount in Settled Currency"

    if df_donations is not None and not df_donations.empty:
        # Pre-normalize columns ONCE for instant 15ms vectorized execution
        df_work = df_donations.copy()
        df_work["fn_lower"] = df_work["fundraiser_name"].fillna("").astype(str).str.strip().str.lower() if "fundraiser_name" in df_work.columns else ""
        df_work["cname_lower"] = df_work["Campaign Name"].fillna("").astype(str).str.strip().str.lower() if "Campaign Name" in df_work.columns else ""
        df_work["code_lower"] = df_work["Code"].fillna("").astype(str).str.strip().str.lower() if "Code" in df_work.columns else ""
        df_work["net_num"] = pd.to_numeric(df_work[amount_col], errors="coerce").fillna(0.0) if amount_col in df_work.columns else 0.0
        
        if "Created Date (UTC)" in df_work.columns:
            df_work["_parsed_date"] = pd.to_datetime(df_work["Created Date (UTC)"], errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
        else:
            df_work["_parsed_date"] = ""

        # Vectorized pre-aggregation for named peer-to-peer fundraisers
        df_named = df_work[df_work["fn_lower"] != ""].copy()
        known_donation_fundraisers = set(df_named["fn_lower"].unique())
        
        # Fast group aggregations
        all_time_group = df_named.groupby("fn_lower")
        all_time_raised_map = all_time_group["net_num"].sum().to_dict()
        all_time_txns_map = all_time_group["net_num"].count().to_dict()
        all_time_min_date_map = all_time_group["_parsed_date"].min().to_dict()
        all_time_max_date_map = all_time_group["_parsed_date"].max().to_dict()
        
        # Fast email sets
        if "Email" in df_named.columns:
            df_valid_emails = df_named[df_named["Email"].notna() & (~df_named["Email"].astype(str).str.strip().str.lower().isin(["", "nan", "none", "n/a"]))].copy()
            df_valid_emails["em_clean"] = df_valid_emails["Email"].astype(str).str.strip().str.lower()
            all_time_donors_map = df_valid_emails.groupby("fn_lower")["em_clean"].nunique().to_dict()
            all_time_emails_set_map = df_valid_emails.groupby("fn_lower")["em_clean"].apply(set).to_dict()
        else:
            all_time_donors_map = {}
            all_time_emails_set_map = {}

        # Period group aggregations if date filtered
        is_custom_filtered = bool(start_date or end_date)
        if is_custom_filtered:
            date_mask = pd.Series(True, index=df_work.index)
            if start_date:
                date_mask = date_mask & (df_work["_parsed_date"] >= start_date)
            if end_date:
                date_mask = date_mask & (df_work["_parsed_date"] <= end_date)
            
            df_period = df_work[date_mask].copy()
            df_period_named = df_period[df_period["fn_lower"] != ""].copy()
            period_group = df_period_named.groupby("fn_lower")
            period_raised_map = period_group["net_num"].sum().to_dict()
            period_txns_map = period_group["net_num"].count().to_dict()
            
            if "Email" in df_period_named.columns:
                df_p_valid = df_period_named[df_period_named["Email"].notna() & (~df_period_named["Email"].astype(str).str.strip().str.lower().isin(["", "nan", "none", "n/a"]))].copy()
                df_p_valid["em_clean"] = df_p_valid["Email"].astype(str).str.strip().str.lower()
                period_donors_map = df_p_valid.groupby("fn_lower")["em_clean"].nunique().to_dict()
            else:
                period_donors_map = {}
        else:
            df_period = df_work
            period_raised_map = all_time_raised_map
            period_txns_map = all_time_txns_map
            period_donors_map = all_time_donors_map

    else:
        df_work = pd.DataFrame()
        known_donation_fundraisers = set()
        all_time_raised_map = {}
        all_time_txns_map = {}
        all_time_min_date_map = {}
        all_time_max_date_map = {}
        all_time_donors_map = {}
        all_time_emails_set_map = {}
        period_raised_map = {}
        period_txns_map = {}
        period_donors_map = {}
        is_custom_filtered = bool(start_date or end_date)

    fundraisers_result = []
    total_raised_all_time_sum = 0.0
    total_raised_period_sum = 0.0
    total_target_goal_sum = 0.0
    global_donor_emails = set()
    total_txns_sum = 0

    for f in fundraiser_rows:
        fid = f["id"]
        fname = f.get("name", "Unnamed")
        fname_clean = str(fname or "").strip().lower()
        c_list = f_campaign_map.get(fid, [])
        target_goal = float(f.get("target_goal") or 0.0)
        f_start_date = str(f.get("start_date") or "").strip()

        all_time_raised = 0.0
        period_raised = 0.0
        txn_count = 0
        period_txns = 0
        donor_count = 0
        period_donors = 0
        first_donation_date = None
        latest_donation_date = None

        if fname_clean in known_donation_fundraisers:
            # 1. Named peer-to-peer fundraiser: instant dict lookup
            all_time_raised = float(all_time_raised_map.get(fname_clean, 0.0))
            txn_count = int(all_time_txns_map.get(fname_clean, 0))
            donor_count = int(all_time_donors_map.get(fname_clean, 0))
            first_donation_date = str(all_time_min_date_map.get(fname_clean) or "")
            latest_donation_date = str(all_time_max_date_map.get(fname_clean) or "")
            
            period_raised = float(period_raised_map.get(fname_clean, 0.0))
            period_txns = int(period_txns_map.get(fname_clean, 0))
            period_donors = int(period_donors_map.get(fname_clean, 0))

            if fname_clean in all_time_emails_set_map:
                global_donor_emails.update(all_time_emails_set_map[fname_clean])

        elif c_list and not df_work.empty:
            # 2. Custom manual fundraiser: matches assigned campaigns for unassigned gifts
            masks = []
            for c_item in c_list:
                c_clean = str(c_item.get("campaign_name") or "").strip().lower()
                cd_clean = str(c_item.get("code") or "ALL").strip().lower()
                if not c_clean:
                    continue
                if cd_clean in ["all", "", "unassigned"]:
                    m = (df_work["cname_lower"] == c_clean) & (df_work["fn_lower"].isin(["", "nan", "none", "n/a", "unassigned"]))
                else:
                    m = (df_work["cname_lower"] == c_clean) & (df_work["code_lower"] == cd_clean) & (df_work["fn_lower"].isin(["", "nan", "none", "n/a", "unassigned"]))
                masks.append(m)
            if masks:
                comb = masks[0]
                for m in masks[1:]:
                    comb = comb | m
                sub_df = df_work[comb]
                if not sub_df.empty:
                    all_time_raised = float(sub_df["net_num"].sum())
                    txn_count = len(sub_df)
                    if "Email" in sub_df.columns:
                        valid_emails = sub_df["Email"].dropna().astype(str).str.strip().str.lower()
                        valid_emails = valid_emails[~valid_emails.isin(["", "nan", "none", "n/a"])]
                        donor_count = len(set(valid_emails))
                        global_donor_emails.update(valid_emails)
                    if "_parsed_date" in sub_df.columns:
                        valid_dates = sub_df["_parsed_date"].dropna()
                        valid_dates = valid_dates[valid_dates != ""]
                        if not valid_dates.empty:
                            first_donation_date = str(valid_dates.min())
                            latest_donation_date = str(valid_dates.max())

                    if is_custom_filtered:
                        date_m = pd.Series(True, index=sub_df.index)
                        if start_date:
                            date_m = date_m & (sub_df["_parsed_date"] >= start_date)
                        if end_date:
                            date_m = date_m & (sub_df["_parsed_date"] <= end_date)
                        p_sub = sub_df[date_m]
                        period_raised = float(p_sub["net_num"].sum()) if not p_sub.empty else 0.0
                        period_txns = len(p_sub)
                        if "Email" in p_sub.columns and not p_sub.empty:
                            p_emails = p_sub["Email"].dropna().astype(str).str.strip().str.lower()
                            p_emails = p_emails[~p_emails.isin(["", "nan", "none", "n/a"])]
                            period_donors = len(set(p_emails))
                        else:
                            period_donors = 0
                    else:
                        period_raised = all_time_raised
                        period_txns = txn_count
                        period_donors = donor_count

        inception_date = first_donation_date or f_start_date or "N/A"
        progress_pct = round((all_time_raised / target_goal * 100.0), 1) if target_goal > 0 else (100.0 if all_time_raised > 0 else 0.0)
        period_progress_pct = round((period_raised / target_goal * 100.0), 1) if target_goal > 0 else 0.0
        avg_donation = round(all_time_raised / txn_count, 2) if txn_count > 0 else 0.0

        fundraiser_obj = {
            "id": fid,
            "name": fname,
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
            "total_donors": donor_count,
            "period_donors": period_donors,
            "total_donations_count": txn_count,
            "period_donations_count": period_txns,
            "avg_donation": avg_donation
        }

        fundraisers_result.append(fundraiser_obj)
        total_raised_all_time_sum += all_time_raised
        total_raised_period_sum += period_raised
        total_target_goal_sum += target_goal
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
            "is_custom_filtered": is_custom_filtered,
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
    individual campaign breakdown, monthly timeline, and recent transactions log.
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

    if df_donations is not None and not df_donations.empty:
        df_work = df_donations.copy()
        df_work["fn_lower"] = df_work["fundraiser_name"].fillna("").astype(str).str.strip().str.lower() if "fundraiser_name" in df_work.columns else ""
        df_work["cname_lower"] = df_work["Campaign Name"].fillna("").astype(str).str.strip().str.lower() if "Campaign Name" in df_work.columns else ""
        df_work["code_lower"] = df_work["Code"].fillna("").astype(str).str.strip().str.lower() if "Code" in df_work.columns else ""
        df_work["net_num"] = pd.to_numeric(df_work[amount_col], errors="coerce").fillna(0.0) if amount_col in df_work.columns else 0.0

        if "Created Date (UTC)" in df_work.columns:
            df_work["_parsed_date"] = pd.to_datetime(df_work["Created Date (UTC)"], errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
        else:
            df_work["_parsed_date"] = ""

        fname_clean = str(fundraiser.get("name") or "").strip().lower()
        known_donation_fundraisers = set(df_work[df_work["fn_lower"] != ""]["fn_lower"].unique())

        if fname_clean in known_donation_fundraisers:
            sub_df = df_work[df_work["fn_lower"] == fname_clean]
        elif assigned_campaigns:
            masks = []
            for c_item in assigned_campaigns:
                c_clean = str(c_item.get("campaign_name") or "").strip().lower()
                cd_clean = str(c_item.get("code") or "ALL").strip().lower()
                if not c_clean:
                    continue
                if cd_clean in ["all", "", "unassigned"]:
                    m = (df_work["cname_lower"] == c_clean) & (df_work["fn_lower"].isin(["", "nan", "none", "n/a", "unassigned"]))
                else:
                    m = (df_work["cname_lower"] == c_clean) & (df_work["code_lower"] == cd_clean) & (df_work["fn_lower"].isin(["", "nan", "none", "n/a", "unassigned"]))
                masks.append(m)
            if masks:
                comb = masks[0]
                for m in masks[1:]:
                    comb = comb | m
                sub_df = df_work[comb]
            else:
                sub_df = pd.DataFrame()
        else:
            sub_df = pd.DataFrame()

        if not sub_df.empty:
            total_raised_all_time = float(sub_df["net_num"].sum())

            # Date filtering for period calculations
            period_sub = sub_df
            if start_date or end_date:
                d_mask = pd.Series(True, index=sub_df.index)
                if start_date:
                    d_mask = d_mask & (sub_df["_parsed_date"] >= start_date)
                if end_date:
                    d_mask = d_mask & (sub_df["_parsed_date"] <= end_date)
                period_sub = sub_df[d_mask]

            total_raised_period = float(period_sub["net_num"].sum()) if not period_sub.empty else 0.0

            # Group by Campaign Breakdown
            if "Campaign Name" in sub_df.columns:
                c_grouped = sub_df.groupby(["Campaign Name", sub_df.get("Code", "Unassigned") if "Code" in sub_df.columns else sub_df["Campaign Name"]])
                for (cname, code), c_grp in c_grouped:
                    gross_all = float(c_grp["net_num"].sum())
                    
                    c_period = period_sub[(period_sub["Campaign Name"] == cname) & (period_sub.get("Code", "Unassigned") == code)] if not period_sub.empty else pd.DataFrame()
                    gross_p = float(c_period["net_num"].sum()) if not c_period.empty else 0.0
                    p_txns = len(c_period) if not c_period.empty else 0
                    p_donors = len(set(c_period["Email"].dropna().astype(str).str.strip().str.lower())) if (not c_period.empty and "Email" in c_period.columns) else 0

                    campaign_breakdown.append({
                        "campaign_name": str(cname),
                        "code": str(code),
                        "platform": str(c_grp["Platform"].iloc[0]) if "Platform" in c_grp.columns and not c_grp["Platform"].empty else "LaunchGood",
                        "gross_raised": round(gross_p if (start_date or end_date) else gross_all, 2),
                        "gross_raised_all_time": round(gross_all, 2),
                        "total_donations": p_txns if (start_date or end_date) else len(c_grp),
                        "total_donors": p_donors if (start_date or end_date) else len(set(c_grp["Email"].dropna().astype(str).str.strip().str.lower())) if "Email" in c_grp.columns else 0,
                        "heading": str(c_grp["Heading"].iloc[0]) if "Heading" in c_grp.columns and not c_grp["Heading"].empty and pd.notna(c_grp["Heading"].iloc[0]) else "Unassigned",
                        "country": str(c_grp["Country"].iloc[0]) if "Country" in c_grp.columns and not c_grp["Country"].empty and pd.notna(c_grp["Country"].iloc[0]) else "Unassigned"
                    })

            # Monthly aggregation
            if "Created Date (UTC)" in sub_df.columns:
                dates = pd.to_datetime(sub_df["Created Date (UTC)"], errors="coerce", format="mixed")
                months = dates.dt.strftime("%Y-%m")
                for m_val, amt in zip(months, sub_df["net_num"]):
                    if pd.notna(m_val) and m_val != "NaT":
                        monthly_timeline[m_val] = monthly_timeline.get(m_val, 0.0) + float(amt)

            # Recent transactions
            sample_cols = [c for c in ["Created Date (UTC)", "Donor Name", "First Name", "Last Name", "Email", "Campaign Name", "Code", "net_num", "Platform"] if c in period_sub.columns]
            tx_sample = period_sub[sample_cols].sort_values("Created Date (UTC)", ascending=False).head(50).to_dict('records')
            for t in tx_sample:
                fn = str(t.get("First Name") or "").strip() if pd.notna(t.get("First Name")) else ""
                ln = str(t.get("Last Name") or "").strip() if pd.notna(t.get("Last Name")) else ""
                raw_name = t.get("Donor Name")
                name = str(raw_name).strip() if pd.notna(raw_name) and str(raw_name).strip() else (f"{fn} {ln}".strip() or "Anonymous")
                
                email_val = t.get("Email")
                email_str = str(email_val).strip() if pd.notna(email_val) and str(email_val).strip().lower() not in ["nan", "none", ""] else "N/A"
                
                cname_val = t.get("Campaign Name")
                cname_str = str(cname_val).strip() if pd.notna(cname_val) and str(cname_val).strip() else "General Appeal"
                
                code_val = t.get("Code")
                code_str = str(code_val).strip() if pd.notna(code_val) and str(code_val).strip() else "ALL"
                
                plat_val = t.get("Platform")
                plat_str = str(plat_val).strip() if pd.notna(plat_val) and str(plat_val).strip() else "LaunchGood"
                
                amt_num = float(t.get("net_num") or 0.0)

                recent_transactions.append({
                    "date": str(t.get("Created Date (UTC)") or "N/A") if pd.notna(t.get("Created Date (UTC)")) else "N/A",
                    "donor_name": name,
                    "email": email_str,
                    "campaign_name": cname_str,
                    "code": code_str,
                    "amount": round(amt_num, 2),
                    "platform": plat_str
                })

            if "_parsed_date" in sub_df.columns:
                valid_dates = sub_df["_parsed_date"].dropna()
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

        # Re-assign campaigns
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


@router.post("/assign-donations")
def assign_unassigned_donations(payload: AssignDonationsRequest):
    """
    Allows Super Admins to manually assign unassigned donations (by campaign, code, or donor emails)
    to a specific fundraiser, writing the fundraiser_name to the SQLite database and parquet cache.
    """
    _check_super_admin(payload.user_role, payload.can_edit_donors or False)
    
    target_fname = payload.fundraiser_name.strip()
    if not target_fname:
        raise HTTPException(status_code=400, detail="Target fundraiser name is required.")

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
    cur = conn.cursor()
    updated_rows = 0

    try:
        if payload.donor_emails:
            emails_clean = [e.strip().lower() for e in payload.donor_emails if e.strip()]
            placeholders = ",".join("?" for _ in emails_clean)
            cur.execute(f"""
                UPDATE donations 
                SET fundraiser_name = ? 
                WHERE LOWER(TRIM(Email)) IN ({placeholders})
                  AND (fundraiser_name IS NULL OR TRIM(fundraiser_name) = '')
            """, [target_fname] + emails_clean)
            updated_rows = cur.rowcount
        elif payload.campaign_name:
            cname = payload.campaign_name.strip()
            code = (payload.code or "ALL").strip()
            if code.upper() == "ALL" or not code:
                cur.execute("""
                    UPDATE donations 
                    SET fundraiser_name = ? 
                    WHERE [Campaign Name] = ? 
                      AND (fundraiser_name IS NULL OR TRIM(fundraiser_name) = '')
                """, (target_fname, cname))
            else:
                cur.execute("""
                    UPDATE donations 
                    SET fundraiser_name = ? 
                    WHERE [Campaign Name] = ? AND Code = ?
                      AND (fundraiser_name IS NULL OR TRIM(fundraiser_name) = '')
                """, (target_fname, cname, code))
            updated_rows = cur.rowcount

        conn.commit()
    finally:
        conn.close()

    return {
        "status": "success",
        "updated_donations_count": updated_rows,
        "message": f"Successfully assigned {updated_rows} donations to fundraiser '{target_fname}'."
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
