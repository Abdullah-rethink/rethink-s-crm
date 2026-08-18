from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
import sqlite3
import pandas as pd
import math
import os

from core.data_processor import LOCAL_DB_PATH, load_data, load_payouts_data

router = APIRouter(prefix="/api/payouts", tags=["Payouts Reconciliation"])


def _get_payout_data_from_db():
    try:
        df_p = load_payouts_data()
        if df_p is not None and not df_p.empty:
            df = df_p.copy() if not df_p.empty else df_p
            # Normalize column aliases
            c_name = df.get("Campaign Name", pd.Series("Unassigned Campaign", index=df.index)).fillna("Unassigned Campaign")
            df["campaign_name"] = c_name
            df["Campaign Name"] = c_name
            df["row_type"] = df.get("Type", df.get("Transaction Type", pd.Series("donation", index=df.index))).fillna("donation").astype(str).str.lower()
            df["gross_amt"] = pd.to_numeric(df.get("Total Online Donation Gross Amount in Settled Currency", 0.0), errors="coerce").fillna(0.0)
            df["fee_amt"] = pd.to_numeric(df.get("Total Processing Fees Paid by CC In Settled Currency", 0.0), errors="coerce").fillna(0.0)
            df["net_amt"] = pd.to_numeric(df.get("Total Online Donations Net Amount in Settled Currency", 0.0), errors="coerce").fillna(0.0)
            df["transfer_id"] = df.get("Transfer ID", pd.Series("N/A", index=df.index)).fillna("N/A").astype(str)
            df["heading"] = df.get("Heading", pd.Series("Unassigned", index=df.index)).fillna("Unassigned").astype(str)
            df["sub_heading"] = df.get("Sub-Heading", pd.Series("Unassigned", index=df.index)).fillna("Unassigned").astype(str)
            df["country"] = df.get("Country", pd.Series("Unassigned", index=df.index)).fillna("Unassigned").astype(str)
            df["code"] = df.get("Code", pd.Series("Unassigned", index=df.index)).fillna("Unassigned").astype(str)
            df["zakat"] = df.get("Zakat Eligibility", pd.Series("Unassigned", index=df.index)).fillna("Unassigned").astype(str)
            return df

        # Fallback to donations cache if payout_settlements table is empty
        df_don = load_data()
        if not df_don.empty:
            p_mask = df_don.get("Platform", pd.Series("", index=df_don.index)).astype(str).str.lower().str.contains("payout") | df_don.get("Transfer ID", pd.Series(None, index=df_don.index)).notna()
            df_sub = df_don[p_mask]
            if not df_sub.empty:
                df = df_sub.copy()
                c_name = df.get("Campaign Name", pd.Series("Unassigned Campaign", index=df.index)).fillna("Unassigned Campaign")
                df["campaign_name"] = c_name
                df["Campaign Name"] = c_name
                df["row_type"] = df.get("Type", df.get("Transaction Type", pd.Series("donation", index=df.index))).fillna("donation").astype(str).str.lower()
                df["gross_amt"] = pd.to_numeric(df.get("Total Online Donation Gross Amount in Settled Currency", 0.0), errors="coerce").fillna(0.0)
                df["fee_amt"] = pd.to_numeric(df.get("Total Processing Fees Paid by CC In Settled Currency", 0.0), errors="coerce").fillna(0.0)
                df["net_amt"] = pd.to_numeric(df.get("Total Online Donations Net Amount in Settled Currency", 0.0), errors="coerce").fillna(0.0)
                df["transfer_id"] = df.get("Transfer ID", pd.Series("N/A", index=df.index)).fillna("N/A").astype(str)
                df["heading"] = df.get("Heading", pd.Series("Unassigned", index=df.index)).fillna("Unassigned").astype(str)
                df["sub_heading"] = df.get("Sub-Heading", pd.Series("Unassigned", index=df.index)).fillna("Unassigned").astype(str)
                df["country"] = df.get("Country", pd.Series("Unassigned", index=df.index)).fillna("Unassigned").astype(str)
                df["code"] = df.get("Code", pd.Series("Unassigned", index=df.index)).fillna("Unassigned").astype(str)
                df["zakat"] = df.get("Zakat Eligibility", pd.Series("Unassigned", index=df.index)).fillna("Unassigned").astype(str)
                return df

        return pd.DataFrame()
    except Exception as e:
        print(f"[Error] Reading cached payout data: {e}")
        return pd.DataFrame()


@router.get("/summary")
def get_payouts_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    campaign_search: Optional[str] = None,
    transfer_id: Optional[str] = None
):
    """Returns top KPI metrics for LaunchGood Payout Settlement Reconciliation."""
    try:
        df = _get_payout_data_from_db()
        if df.empty:
            return {
                "total_gross": 0.0,
                "total_fees": 0.0,
                "total_reserves": 0.0,
                "net_payout": 0.0,
                "total_transactions": 0,
                "settled_donations_count": 0
            }

        # Filters
        if start_date and str(start_date).strip():
            df = df[pd.to_datetime(df["Created Date (UTC)"], errors="coerce") >= pd.to_datetime(start_date)]
        if end_date and str(end_date).strip():
            df = df[pd.to_datetime(df["Created Date (UTC)"], errors="coerce") <= pd.to_datetime(end_date)]
        if transfer_id and str(transfer_id).strip():
            df = df[df["transfer_id"].astype(str).str.strip().str.lower() == str(transfer_id).strip().lower()]

        donations_df = df[df["row_type"] == "donation"]
        payouts_df = df[df["row_type"] == "payout"]
        reserves_df = df[df["row_type"] == "reserve"]

        total_gross = float(donations_df["gross_amt"].sum())
        total_fees = float(df["fee_amt"].sum())
        total_reserves = float(abs(reserves_df["net_amt"].sum()))
        
        net_payout = float(abs(payouts_df["net_amt"].sum())) if not payouts_df.empty else float(donations_df["net_amt"].sum() - total_fees)

        return {
            "total_gross": round(total_gross, 2),
            "total_fees": round(total_fees, 2),
            "total_reserves": round(total_reserves, 2),
            "net_payout": round(net_payout, 2),
            "total_transactions": len(df),
            "settled_donations_count": len(donations_df)
        }

    except Exception as e:
        print(f"[Error] Payout summary error: {e}")
        return {
            "total_gross": 0.0,
            "total_fees": 0.0,
            "total_reserves": 0.0,
            "net_payout": 0.0,
            "total_transactions": 0,
            "settled_donations_count": 0
        }


@router.get("/batches")
def get_payout_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=250),
    search: Optional[str] = ""
):
    """Returns paginated list of payout settlement batches grouped by Transfer ID."""
    try:
        df = _get_payout_data_from_db()
        if df.empty:
            return {"total_batches": 0, "page": page, "page_size": page_size, "batches": []}

        if search and search.strip():
            term = search.strip().lower()
            mask = df["transfer_id"].astype(str).str.lower().str.contains(term, na=False) | df["campaign_name"].astype(str).str.lower().str.contains(term, na=False)
            df = df[mask]

        grouped = df.groupby("transfer_id").apply(lambda g: pd.Series({
            "created_date": str(g["Created Date (UTC)"].dropna().min() or "N/A"),
            "gross_amount": round(float(g[g["row_type"] == "donation"]["gross_amt"].sum()), 2),
            "processing_fees": round(float(g["fee_amt"].sum()), 2),
            "transfer_amount": round(float(abs(g[g["row_type"] == "payout"]["net_amt"].sum()) or g[g["row_type"] == "donation"]["net_amt"].sum()), 2),
            "campaigns_count": int(g["campaign_name"].nunique()),
            "donations_count": int((g["row_type"] == "donation").sum())
        })).reset_index()

        total_batches = len(grouped)
        total_pages = max(1, math.ceil(total_batches / page_size))
        page = min(page, total_pages)
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_batches)

        page_batches = grouped.iloc[start_idx:end_idx].to_dict(orient="records")

        return {
            "total_batches": total_batches,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "batches": page_batches
        }

    except Exception as e:
        print(f"[Error] Payout batches error: {e}")
        return {"total_batches": 0, "page": page, "page_size": page_size, "batches": []}


@router.get("/campaign-breakdown")
def get_campaign_payout_breakdown(
    search: Optional[str] = ""
):
    """Returns campaign-level financial payout breakdown (Gross Raised, CC Fees, Net Payout, Fee %) using Single Source of Truth matrix classifications."""
    try:
        df = _get_payout_data_from_db()
        if df.empty:
            return {"campaigns": []}

        if search and search.strip():
            term = search.strip().lower()
            df = df[df["campaign_name"].astype(str).str.lower().str.contains(term, na=False)]

        # Join/Overlay Single Source of Truth Classifications from campaign_classifications table
        try:
            conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
            matrix_df = pd.read_sql_query("SELECT campaign_name, heading, sub_heading, country, code, zakat_eligibility FROM campaign_classifications", conn)
            conn.close()
            if not matrix_df.empty:
                rule_dict = {str(c).strip().lower(): r for c, r in zip(matrix_df["campaign_name"], matrix_df.to_dict('records'))}
                c_keys = df["campaign_name"].astype(str).str.strip().str.lower()
                for f, db_f in [("heading", "heading"), ("sub_heading", "sub_heading"), ("country", "country"), ("code", "code"), ("zakat", "zakat_eligibility")]:
                    col_map = {k: str(v[db_f]) for k, v in rule_dict.items() if db_f in v and str(v[db_f]).lower() not in ["", "nan", "none", "unassigned"]}
                    mapped = c_keys.map(col_map)
                    valid_m = mapped.notna()
                    if valid_m.any():
                        df.loc[valid_m, f] = mapped[valid_m]
        except Exception as e:
            print(f"[Matrix Overlay Notice]: {e}")

        records = []
        for cname, g in df.groupby("campaign_name"):
            donations_g = g[g["row_type"] == "donation"]
            g_amt = round(float(donations_g["gross_amt"].sum()), 2)
            f_amt = round(float(g["fee_amt"].sum()), 2)
            t_amt = round(float(donations_g["net_amt"].sum()), 2)
            fee_pct = round((f_amt / g_amt * 100.0), 2) if g_amt > 0 else 0.0

            records.append({
                "campaign_name": str(cname),
                "gross_amount": g_amt,
                "processing_fees": f_amt,
                "transfer_amount": t_amt,
                "fee_percentage": fee_pct,
                "heading": str(g["heading"].iloc[0]),
                "sub_heading": str(g["sub_heading"].iloc[0]),
                "country": str(g["country"].iloc[0]),
                "code": str(g["code"].iloc[0]),
                "zakat": str(g["zakat"].iloc[0]),
                "donations_count": int(len(donations_g))
            })

        records.sort(key=lambda x: x["gross_amount"], reverse=True)
        return {"campaigns": records}

    except Exception as e:
        print(f"[Error] Campaign payout breakdown error: {e}")
        return {"campaigns": []}
