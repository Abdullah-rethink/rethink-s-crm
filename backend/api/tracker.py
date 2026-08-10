import os
import sqlite3
import pandas as pd
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, status
from pydantic import BaseModel

from core.data_processor import load_data, LOCAL_DB_PATH

router = APIRouter(prefix="/api/tracker", tags=["Sponsorship Target Tracker"])

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
        return {"status": "success", "message": "Successfully updated targets!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/stats")
def get_tracker_stats():
    """Computes real-time donor target progress stats."""
    # 1. Fetch current targets from SQLite
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

    # 2. Load active dataset
    df = load_data()
    if df.empty:
        return {s: {"target": t, "total_raised": 0.0, "above": [], "near": []} for s, t in targets.items()}

    col_amount = "Total Online Donations Net Amount in Settled Currency"
    if col_amount not in df.columns:
        col_amount = "Donation Amount in Project Currency (May be approx.)"
    if col_amount not in df.columns:
        col_amount = "Donation Amount (in Donation Currency)"

    if col_amount not in df.columns or "Donor ID" not in df.columns:
        return {s: {"target": t, "total_raised": 0.0, "above": [], "near": []} for s, t in targets.items()}

    # Ensure amount column is numeric
    df[col_amount] = pd.to_numeric(df[col_amount], errors="coerce").fillna(0.0)

    # 3. Categorize transactions based on Code
    df["sponsorship_type"] = None
    if "Code" in df.columns:
        code_series = df["Code"].astype(str).str.strip().str.upper()
        df.loc[code_series.str.contains("HUF", na=False), "sponsorship_type"] = "Hafiz"
        df.loc[code_series.str.contains("ORP", na=False), "sponsorship_type"] = "Orphan"
        df.loc[code_series.str.contains("WID", na=False), "sponsorship_type"] = "Widow"
        df.loc[code_series.str.contains("SUR", na=False) | code_series.str.contains("EX-PRISONER", na=False), "sponsorship_type"] = "Ex-Prisoner"

    # Pre-build donor profiles to retrieve display name and email quickly
    donor_info = {}
    
    for donor_id, sub_df in df.groupby("Donor ID"):
        first_row = sub_df.iloc[0]
        best_name = "Anonymous Donor"
        for _, row in sub_df.iterrows():
            disp = str(row.get("Display Name", "")).strip()
            disp_lower = disp.lower()
            if disp and disp_lower not in ["nan", "none", "null", "anonymous", "anonymous kind soul", "kind soul"]:
                best_name = disp
                break
        else:
            for _, row in sub_df.iterrows():
                fn = str(row.get("First Name", "")).strip()
                ln = str(row.get("Last Name", "")).strip()
                if fn or ln:
                    combined = f"{fn} {ln}".strip()
                    if combined.lower() not in ["nan", "none", "null", "anonymous", "anonymous kind soul", "kind soul", ""]:
                        best_name = combined
                        break
            else:
                best_name = str(first_row.get("Display Name", "Anonymous Donor"))

        donor_info[donor_id] = {
            "name": best_name,
            "email": str(first_row.get("Email", "N/A"))
        }

    # 4. Compute statistics for each sponsorship type
    results = {}
    for s_type, target in targets.items():
        s_df = df[df["sponsorship_type"] == s_type]
        total_raised = float(s_df[col_amount].sum())

        above_list = []
        near_list = []

        if not s_df.empty:
            donor_sums = s_df.groupby("Donor ID")[col_amount].sum()
            
            for d_id, total in donor_sums.items():
                total = float(total)
                progress = round((total / target) * 100.0, 1)
                
                info = donor_info.get(d_id, {"name": "Anonymous Donor", "email": "N/A"})
                donor_record = {
                    "donor_id": str(d_id),
                    "name": info["name"],
                    "email": info["email"],
                    "total_donated": round(total, 2),
                    "target": target,
                    "progress": progress
                }

                if total >= target:
                    above_list.append(donor_record)
                elif total >= (0.8 * target):
                    near_list.append(donor_record)

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

    return results
