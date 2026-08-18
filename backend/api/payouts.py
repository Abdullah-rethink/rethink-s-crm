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
            df["settlement_currency"] = df.get("Settlement Currency", pd.Series("GBP", index=df.index)).fillna("GBP").astype(str).str.strip().str.upper()
            df["Settlement Currency"] = df["settlement_currency"]
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
                df["settlement_currency"] = df.get("Settlement Currency", pd.Series("GBP", index=df.index)).fillna("GBP").astype(str).str.strip().str.upper()
                df["Settlement Currency"] = df["settlement_currency"]
                return df

        return pd.DataFrame()
    except Exception as e:
        print(f"[Error] Reading cached payout data: {e}")
        return pd.DataFrame()


def _generate_disbursement_summary(df_curr: pd.DataFrame, currency_name: str) -> Dict[str, Any]:
    """Generates exact Disbursement Summary matching the Finance Team ledger format."""
    donations = df_curr[df_curr["row_type"] == "donation"]
    refunds = df_curr[df_curr["row_type"] == "refund"]
    adjustments = df_curr[df_curr["row_type"] == "adjustment"]
    reserves = df_curr[df_curr["row_type"] == "reserve"]
    fx = df_curr[df_curr["row_type"] == "fx"]
    payouts = df_curr[df_curr["row_type"] == "payout"]

    gross_donations = float(donations["gross_amt"].sum())
    gross_donations_count = int(len(donations))

    refunds_amt = float(refunds["gross_amt"].sum())
    refunds_count = int(len(refunds))

    net_sales = float(gross_donations + refunds_amt)
    net_sales_count = int(gross_donations_count - refunds_count)

    processing_fees = float(df_curr["fee_amt"].sum())
    non_processing_fees = 0.0

    manual_adjustments = float(adjustments["gross_amt"].sum())
    manual_adjustments_count = int(len(adjustments))

    reserve_adjustment = float(reserves["gross_amt"].sum())
    reserve_adjustment_count = int(len(reserves))

    fx_amt = float(fx["gross_amt"].sum())
    fx_count = int(len(fx))

    if not payouts.empty:
        total_disbursement = float(abs(payouts["net_amt"].sum()))
        total_disbursement_count = int(len(payouts))
    else:
        total_disbursement = float(net_sales - processing_fees + manual_adjustments + reserve_adjustment + fx_amt)
        total_disbursement_count = int(len(payouts))

    return {
        "currency": currency_name,
        "gross_donations": round(gross_donations, 2),
        "gross_donations_count": gross_donations_count,
        "refunds": round(refunds_amt, 2),
        "refunds_count": refunds_count,
        "refunds_failed": 0.0,
        "refunds_failed_count": 0,
        "chargebacks": 0.0,
        "chargebacks_count": 0,
        "chargebacks_reversed": 0.0,
        "chargebacks_reversed_count": 0,
        "net_sales": round(net_sales, 2),
        "net_sales_count": net_sales_count,
        "processing_fees": round(-abs(processing_fees) if processing_fees != 0 else 0.0, 2),
        "non_processing_fees": 0.0,
        "manual_adjustments": round(manual_adjustments, 2),
        "manual_adjustments_count": manual_adjustments_count,
        "reserve_adjustment": round(reserve_adjustment, 2),
        "reserve_adjustment_count": reserve_adjustment_count,
        "foreign_exchange": round(fx_amt, 2),
        "foreign_exchange_count": fx_count,
        "total_disbursement": round(total_disbursement, 2),
        "total_disbursement_count": total_disbursement_count
    }


def _generate_ledger_breakdown(df: pd.DataFrame) -> List[Dict[str, Any]]:
    DESCRIPTIONS = {
        "donation": "Gross donor contributions received",
        "payout": "Bank transfer batches paid out to charity account",
        "reserve": "Rolling reserve hold funds",
        "fx": "Foreign exchange conversion adjustments",
        "adjustment": "Settlement / manual account adjustment",
        "refund": "Donor transaction refund deductions"
    }
    TYPE_ORDER = ["donation", "payout", "reserve", "fx", "adjustment", "refund"]

    if df is None or df.empty or "row_type" not in df.columns:
        return []

    breakdown = []
    found_types = set(df["row_type"].unique())
    ordered_types = [t for t in TYPE_ORDER if t in found_types] + [t for t in found_types if t not in TYPE_ORDER]

    for r_type in ordered_types:
        g = df[df["row_type"] == r_type]
        count = int(len(g))
        gross = float(g["gross_amt"].sum())
        fees = float(g["fee_amt"].sum())
        net = float(g["net_amt"].sum())

        if r_type == "payout" and net > 0:
            net = -abs(net)
            gross = -abs(gross)

        breakdown.append({
            "row_type": str(r_type),
            "row_count": count,
            "gross_amount": round(gross, 2),
            "processing_fees": round(fees, 2),
            "net_amount": round(net, 2),
            "description": DESCRIPTIONS.get(r_type, "Platform transaction entry")
        })

    return breakdown


@router.get("/summary")
def get_payouts_summary(
    currency: Optional[str] = Query("GBP", description="Filter by settlement currency: GBP, USD, or ALL"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    campaign_search: Optional[str] = None,
    transfer_id: Optional[str] = None
):
    """Returns top KPI metrics, Finance Disbursement Summary, and Accounting Ledger breakdown."""
    try:
        df_all = _get_payout_data_from_db()
        if df_all.empty:
            return {
                "currency": currency or "GBP",
                "total_gross": 0.0,
                "total_fees": 0.0,
                "total_reserves": 0.0,
                "net_payout": 0.0,
                "total_transactions": 0,
                "settled_donations_count": 0,
                "disbursement_summary": {},
                "ledger_breakdown": [],
                "available_currencies": ["GBP", "USD"]
            }

        df = df_all.copy()

        # Currency Filter
        curr_selected = (currency or "GBP").strip().upper()
        if curr_selected in ["GBP", "USD"]:
            df = df[df["settlement_currency"] == curr_selected]
        else:
            curr_selected = "ALL"

        # Date & Transfer Filters
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
        
        disbursement_summary = _generate_disbursement_summary(df, curr_selected)
        ledger_breakdown = _generate_ledger_breakdown(df)

        return {
            "currency": curr_selected,
            "total_gross": round(total_gross, 2),
            "total_fees": round(total_fees, 2),
            "total_reserves": round(total_reserves, 2),
            "net_payout": round(net_payout, 2),
            "total_transactions": len(df),
            "settled_donations_count": len(donations_df),
            "disbursement_summary": disbursement_summary,
            "ledger_breakdown": ledger_breakdown,
            "available_currencies": ["GBP", "USD", "ALL"]
        }

    except Exception as e:
        print(f"[Error] Payout summary error: {e}")
        return {
            "currency": currency or "GBP",
            "total_gross": 0.0,
            "total_fees": 0.0,
            "total_reserves": 0.0,
            "net_payout": 0.0,
            "total_transactions": 0,
            "settled_donations_count": 0,
            "disbursement_summary": {},
            "ledger_breakdown": [],
            "available_currencies": ["GBP", "USD"]
        }


@router.get("/ledger-breakdown")
def get_payout_ledger_breakdown(
    currency: Optional[str] = Query("GBP", description="Filter by settlement currency: GBP, USD, or ALL")
):
    """Returns complete row-type accounting ledger audit table."""
    try:
        df = _get_payout_data_from_db()
        curr_selected = (currency or "GBP").strip().upper()
        if curr_selected in ["GBP", "USD"]:
            df = df[df["settlement_currency"] == curr_selected]
        return {
            "currency": curr_selected,
            "ledger": _generate_ledger_breakdown(df),
            "disbursement_summary": _generate_disbursement_summary(df, curr_selected)
        }
    except Exception as e:
        print(f"[Error] Ledger breakdown error: {e}")
        return {"currency": currency or "GBP", "ledger": [], "disbursement_summary": {}}


@router.get("/batches")
def get_payout_batches(
    currency: Optional[str] = Query("GBP", description="Filter by settlement currency"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=250),
    search: Optional[str] = ""
):
    """Returns paginated list of payout settlement batches grouped by Transfer ID."""
    try:
        df = _get_payout_data_from_db()
        p_val = page if isinstance(page, int) else 1
        ps_val = page_size if isinstance(page_size, int) else 25
        curr_selected = str(currency).strip().upper() if isinstance(currency, str) else "GBP"
        search_val = str(search).strip().lower() if isinstance(search, str) else ""

        if df.empty:
            return {"total_batches": 0, "page": p_val, "page_size": ps_val, "batches": [], "currency": curr_selected}

        if curr_selected in ["GBP", "USD"]:
            df = df[df["settlement_currency"] == curr_selected]

        if search_val:
            mask = df["transfer_id"].astype(str).str.lower().str.contains(search_val, na=False) | df["campaign_name"].astype(str).str.lower().str.contains(search_val, na=False)
            df = df[mask]

        grouped = df.groupby("transfer_id").apply(lambda g: pd.Series({
            "created_date": str(g["Created Date (UTC)"].dropna().min() or "N/A"),
            "gross_amount": round(float(g[g["row_type"] == "donation"]["gross_amt"].sum()), 2),
            "processing_fees": round(float(g["fee_amt"].sum()), 2),
            "transfer_amount": round(float(abs(g[g["row_type"] == "payout"]["net_amt"].sum()) or g[g["row_type"] == "donation"]["net_amt"].sum()), 2),
            "campaigns_count": int(g["campaign_name"].nunique()),
            "donations_count": int((g["row_type"] == "donation").sum()),
            "currency": str(g["settlement_currency"].iloc[0] if "settlement_currency" in g.columns else "GBP")
        })).reset_index()

        total_batches = len(grouped)
        total_pages = max(1, math.ceil(total_batches / ps_val))
        p_val = min(p_val, total_pages)
        start_idx = (p_val - 1) * ps_val
        end_idx = min(start_idx + ps_val, total_batches)

        page_batches = grouped.iloc[start_idx:end_idx].to_dict(orient="records")

        return {
            "total_batches": total_batches,
            "page": p_val,
            "page_size": ps_val,
            "total_pages": total_pages,
            "batches": page_batches,
            "currency": curr_selected
        }

    except Exception as e:
        print(f"[Error] Payout batches error: {e}")
        return {"total_batches": 0, "page": 1, "page_size": 25, "batches": [], "currency": "GBP"}


@router.get("/campaign-breakdown")
def get_campaign_payout_breakdown(
    currency: Optional[str] = Query("GBP", description="Filter by settlement currency"),
    search: Optional[str] = ""
):
    """Returns classification code-level hierarchical breakdown with nested campaigns and individual campaign metrics."""
    try:
        df = _get_payout_data_from_db()
        if df.empty:
            return {"code_groups": [], "campaigns": [], "total_codes": 0, "total_campaigns": 0, "currency": currency or "GBP"}

        curr_selected = str(currency).strip().upper() if isinstance(currency, str) else "GBP"
        if curr_selected in ["GBP", "USD"]:
            df = df[df["settlement_currency"] == curr_selected]

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

        search_val = str(search).strip().lower() if isinstance(search, str) else ""

        # 1. Generate Individual Campaign Records
        campaign_records = []
        for cname, g in df.groupby("campaign_name"):
            donations_g = g[g["row_type"] == "donation"]
            g_amt = round(float(donations_g["gross_amt"].sum()), 2)
            f_amt = round(float(g["fee_amt"].sum()), 2)
            t_amt = round(float(donations_g["net_amt"].sum()), 2)
            fee_pct = round((f_amt / g_amt * 100.0), 2) if g_amt > 0 else 0.0

            campaign_records.append({
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

        campaign_records.sort(key=lambda x: x["gross_amount"], reverse=True)

        # 2. Generate Hierarchical Code Groups
        code_groups = []
        for code_val, c_group in df.groupby("code"):
            donations_cg = c_group[c_group["row_type"] == "donation"]
            g_amt = round(float(donations_cg["gross_amt"].sum()), 2)
            f_amt = round(float(c_group["fee_amt"].sum()), 2)
            t_amt = round(float(donations_cg["net_amt"].sum()), 2)
            fee_pct = round((f_amt / g_amt * 100.0), 2) if g_amt > 0 else 0.0

            sub_camps = []
            for sub_name, sub_g in c_group.groupby("campaign_name"):
                sub_don = sub_g[sub_g["row_type"] == "donation"]
                sub_gross = round(float(sub_don["gross_amt"].sum()), 2)
                sub_fee = round(float(sub_g["fee_amt"].sum()), 2)
                sub_net = round(float(sub_don["net_amt"].sum()), 2)
                sub_pct = round((sub_fee / sub_gross * 100.0), 2) if sub_gross > 0 else 0.0
                sub_camps.append({
                    "campaign_name": str(sub_name),
                    "gross_amount": sub_gross,
                    "processing_fees": sub_fee,
                    "transfer_amount": sub_net,
                    "fee_percentage": sub_pct,
                    "donations_count": int(len(sub_don))
                })
            sub_camps.sort(key=lambda x: x["gross_amount"], reverse=True)

            code_groups.append({
                "code": str(code_val),
                "heading": str(c_group["heading"].iloc[0]),
                "sub_heading": str(c_group["sub_heading"].iloc[0]),
                "country": str(c_group["country"].iloc[0]),
                "zakat": str(c_group["zakat"].iloc[0]),
                "gross_amount": g_amt,
                "processing_fees": f_amt,
                "transfer_amount": t_amt,
                "fee_percentage": fee_pct,
                "campaigns_count": len(sub_camps),
                "donations_count": int(len(donations_cg)),
                "campaigns": sub_camps
            })

        code_groups.sort(key=lambda x: x["gross_amount"], reverse=True)

        # Apply Search Filter
        if search_val:
            filtered_camps = [
                c for c in campaign_records 
                if search_val in c["campaign_name"].lower() 
                or search_val in c["code"].lower() 
                or search_val in c["heading"].lower() 
                or search_val in c["sub_heading"].lower()
                or search_val in c["country"].lower()
            ]
            filtered_codes = []
            for cg in code_groups:
                code_match = (
                    search_val in cg["code"].lower()
                    or search_val in cg["heading"].lower()
                    or search_val in cg["sub_heading"].lower()
                    or search_val in cg["country"].lower()
                )
                matching_subs = [sc for sc in cg["campaigns"] if search_val in sc["campaign_name"].lower()]
                if code_match or matching_subs:
                    cg_copy = dict(cg)
                    if not code_match and matching_subs:
                        cg_copy["campaigns"] = matching_subs
                    filtered_codes.append(cg_copy)
            
            return {
                "code_groups": filtered_codes,
                "campaigns": filtered_camps,
                "total_codes": len(filtered_codes),
                "total_campaigns": len(filtered_camps),
                "currency": curr_selected
            }

        return {
            "code_groups": code_groups,
            "campaigns": campaign_records,
            "total_codes": len(code_groups),
            "total_campaigns": len(campaign_records),
            "currency": curr_selected
        }

    except Exception as e:
        print(f"[Error] Campaign payout breakdown error: {e}")
        return {"code_groups": [], "campaigns": [], "total_codes": 0, "total_campaigns": 0, "currency": currency or "GBP"}

