import os
import sqlite3
import pandas as pd
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, status
from pydantic import BaseModel

from core.data_processor import load_data, LOCAL_DB_PATH

router = APIRouter(prefix="/api/tracker", tags=["Sponsorship Target Tracker"])

_TRACKER_CACHE = None

def clear_tracker_cache():
    global _TRACKER_CACHE
    _TRACKER_CACHE = None

class UpdateTargetsRequest(BaseModel):
    user_role: str
    targets: Dict[str, float]

@router.get("/targets")
def get_targets():
    """Returns the current target values for each of the 4 sponsorships."""
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        cur = conn.cursor()
        cur.execute("SELECT sponsorship_type, target_value FROM sponsorship_targets")
        rows = cur.fetchall()
        return {r[0]: r[1] for r in rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/targets")
def update_targets(payload: UpdateTargetsRequest):
    """Updates target values (restricted to super_admin)."""
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Updating target values is restricted to Super Admin accounts."
        )
    
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        cur = conn.cursor()
        for s_type, val in payload.targets.items():
            cur.execute("""
                INSERT OR REPLACE INTO sponsorship_targets (sponsorship_type, target_value)
                VALUES (?, ?)
            """, (s_type, float(val)))
        conn.commit()
        clear_tracker_cache()
        return {"status": "success", "message": "Successfully updated targets!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/stats")
def get_tracker_stats(
    payment_type: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    heading: Optional[str] = Query(None),
    subheading: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    code: Optional[str] = Query(None),
    zakat: Optional[str] = Query(None),
    donor_country: Optional[str] = Query(None),
    campaign_search: Optional[str] = Query(None),
    gift_aid: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    """Computes real-time donor target progress stats filtered by sidebar criteria."""
    has_filters = any([
        payment_type and payment_type != "All Payment Types",
        tier and tier != "All Classifications",
        source and source != "All Sources (Combined)",
        heading and heading != "All Headings",
        subheading and subheading != "All Sub-Headings",
        country and country != "All Project Countries",
        code and code != "All Codes",
        zakat and zakat != "All Zakat Status",
        donor_country and donor_country != "All Donor Countries",
        campaign_search and campaign_search.strip(),
        gift_aid and gift_aid != "All Gift Aid Status",
        start_date and start_date.strip(),
        end_date and end_date.strip()
    ])

    global _TRACKER_CACHE
    if not has_filters and _TRACKER_CACHE is not None:
        return _TRACKER_CACHE

    targets = {"Hafiz": 240.0, "Orphan": 480.0, "Widow": 1080.0, "Ex-Prisoner": 1080.0}
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        cur = conn.cursor()
        cur.execute("SELECT sponsorship_type, target_value FROM sponsorship_targets")
        for r in cur.fetchall():
            targets[r[0]] = float(r[1])
    except Exception:
        pass
    finally:
        conn.close()

    df = load_data()
    if df.empty:
        res = {s: {"target": t, "total_raised": 0.0, "above_count": 0, "near_count": 0, "above": [], "near": []} for s, t in targets.items()}
        if not has_filters:
            _TRACKER_CACHE = res
        return res

    # Apply Sidebar Filters
    from backend.api.donors import _apply_filters
    df = _apply_filters(
        df,
        payment_type=payment_type,
        tier=tier,
        source=source,
        heading=heading,
        subheading=subheading,
        country=country,
        code=code,
        zakat=zakat,
        donor_country=donor_country,
        campaign_search=campaign_search,
        gift_aid=gift_aid,
        start_date=start_date,
        end_date=end_date
    )

    col_amount = "Total Online Donations Net Amount in Settled Currency"
    if col_amount not in df.columns:
        col_amount = "Donation Amount in Project Currency (May be approx.)"
    if col_amount not in df.columns:
        col_amount = "Donation Amount (in Donation Currency)"

    if col_amount not in df.columns or "Donor ID" not in df.columns or df.empty:
        res = {s: {"target": t, "total_raised": 0.0, "above_count": 0, "near_count": 0, "above": [], "near": []} for s, t in targets.items()}
        if not has_filters:
            _TRACKER_CACHE = res
        return res

    # Ensure amount column is numeric
    df[col_amount] = pd.to_numeric(df[col_amount], errors="coerce").fillna(0.0)
    df["_d_id_str"] = df["Donor ID"].astype(str)

    # Index by Donor ID string for O(1) instant lookup
    indexed_df = df.set_index("_d_id_str", drop=False)

    # Vectorized Code Masking
    code_series = df["Code"].astype(str).str.strip().str.upper() if "Code" in df.columns else pd.Series("", index=df.index)

    masks = {
        "Hafiz": code_series.str.contains("HUF", na=False),
        "Orphan": code_series.str.contains("ORP", na=False),
        "Widow": code_series.str.contains("WID", na=False),
        "Ex-Prisoner": code_series.str.contains("SUR", na=False) | code_series.str.contains("EX-PRISONER", na=False)
    }

    results = {}
    for s_type, target in targets.items():
        mask = masks[s_type]
        s_df = df[mask]
        total_raised = float(s_df[col_amount].sum()) if not s_df.empty else 0.0

        above_list = []
        near_list = []

        if not s_df.empty:
            sums = s_df.groupby("_d_id_str")[col_amount].sum()
            relevant = sums[sums >= (0.8 * target)]

            for str_id, total in relevant.items():
                total_val = float(total)
                progress = round((total_val / target) * 100.0, 1)
                
                if str_id not in indexed_df.index:
                    continue
                d_rows = indexed_df.loc[[str_id]]
                first_row = d_rows.iloc[0]
                
                best_name = "Anonymous Donor"
                for _, r in d_rows.iterrows():
                    disp = str(r.get("Display Name", "")).strip()
                    disp_lower = disp.lower()
                    if disp and disp_lower not in ["nan", "none", "null", "anonymous", "anonymous kind soul", "kind soul"]:
                        best_name = disp
                        break
                else:
                    for _, r in d_rows.iterrows():
                        fn = str(r.get("First Name", "")).strip()
                        ln = str(r.get("Last Name", "")).strip()
                        if fn or ln:
                            comb = f"{fn} {ln}".strip()
                            if comb.lower() not in ["nan", "none", "null", "anonymous", "anonymous kind soul", "kind soul", ""]:
                                best_name = comb
                                break
                    else:
                        best_name = str(first_row.get("Display Name", "Anonymous Donor"))

                email = str(first_row.get("Email", "N/A"))

                rec = {
                    "donor_id": str_id,
                    "name": best_name,
                    "email": email,
                    "total_donated": round(total_val, 2),
                    "target": target,
                    "progress": progress
                }

                if total_val >= target:
                    above_list.append(rec)
                else:
                    near_list.append(rec)

        above_list.sort(key=lambda x: x["total_donated"], reverse=True)
        near_list.sort(key=lambda x: x["total_donated"], reverse=True)

        results[s_type] = {
            "target": target,
            "total_raised": round(total_raised, 2),
            "above_count": len(above_list),
            "near_count": len(near_list),
            "above": above_list,
            "near": near_list
        }

    if not has_filters:
        _TRACKER_CACHE = results
    return results
