from typing import Optional
from fastapi import APIRouter, Query
import pandas as pd
from core.data_processor import load_data
from backend.api.donors import _apply_filters

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


@router.get("/summary")
def get_metrics_summary(
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
    df_raw = load_data()
    df = _apply_filters(df_raw, payment_type, tier, source, heading, subheading, country, code, zakat, donor_country, campaign_search, gift_aid)

    if df.empty:
        return {
            "total_raised": 0.0,
            "total_txns": 0,
            "avg_donation": 0.0,
            "top_category": "N/A",
            "recurring_pct": 0.0,
            "top_donor_seg": "N/A"
        }

    col_amount = "Total Online Donations Net Amount in Settled Currency"
    if col_amount not in df.columns:
        col_amount = "Donation Amount in Project Currency (May be approx.)"

    col_heading = "Heading"

    total_raised = float(df[col_amount].sum()) if col_amount in df.columns else 0.0
    total_txns = int(len(df))
    avg_donation = float(total_raised / total_txns) if total_txns > 0 else 0.0

    top_cat = "N/A"
    if col_heading in df.columns and not df[col_heading].dropna().empty:
        modes = df[col_heading].mode()
        if not modes.empty:
            top_cat = str(modes[0])

    recurring_pct = 0.0
    if "Payment Frequency" in df.columns and total_txns > 0:
        rec_count = (df["Payment Frequency"] == "Recurring Payment").sum()
        recurring_pct = float((rec_count / total_txns) * 100.0)

    top_donor_seg = "N/A"
    if "Lifetime Donor Classification" in df.columns and not df["Lifetime Donor Classification"].dropna().empty:
        seg_modes = df["Lifetime Donor Classification"].mode()
        if not seg_modes.empty:
            top_donor_seg = str(seg_modes[0])

    return {
        "total_raised": round(total_raised, 2),
        "total_txns": total_txns,
        "avg_donation": round(avg_donation, 2),
        "top_category": top_cat,
        "recurring_pct": round(recurring_pct, 1),
        "top_donor_seg": top_donor_seg
    }
