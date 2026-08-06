from typing import Optional
from fastapi import APIRouter, Query
from config.settings import DONOR_TIER_ORDER
from core.data_processor import load_data

router = APIRouter(prefix="/api/ltv", tags=["Lifetime LTV & Segmentation"])


def _apply_filters(df, payment_type, tier, source, heading, subheading, country):
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

    return filtered_df


def _get_amount_column(df):
    for col in [
        "Total Online Donations Net Amount in Settled Currency",
        "Donation Amount in Project Currency (May be approx.)",
        "Donation Amount (in Donation Currency)"
    ]:
        if col in df.columns:
            return col
    return None


@router.get("/summary")
def get_ltv_summary(
    payment_type: Optional[str] = None,
    tier: Optional[str] = None,
    source: Optional[str] = None,
    heading: Optional[str] = None,
    subheading: Optional[str] = None,
    country: Optional[str] = None
):
    df_raw = load_data()
    df = _apply_filters(df_raw, payment_type, tier, source, heading, subheading, country)
    col_amount = _get_amount_column(df)

    if df.empty or not col_amount or "Lifetime Donor Classification" not in df.columns:
        return []

    ltv_summary = df.groupby("Lifetime Donor Classification").agg(
        total_raised=(col_amount, "sum"),
        donation_count=(col_amount, "count"),
        avg_donation=(col_amount, "mean")
    ).reset_index()

    ltv_summary["tier_order"] = ltv_summary["Lifetime Donor Classification"].map(
        {t: i for i, t in enumerate(DONOR_TIER_ORDER)}
    )
    ltv_summary = ltv_summary.sort_values("tier_order").drop(columns=["tier_order"])
    ltv_summary.rename(columns={"Lifetime Donor Classification": "tier"}, inplace=True)

    ltv_summary["total_raised"] = ltv_summary["total_raised"].round(2)
    ltv_summary["avg_donation"] = ltv_summary["avg_donation"].round(2)

    return ltv_summary.to_dict(orient="records")
