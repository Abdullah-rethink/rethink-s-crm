from typing import Optional
from fastapi import APIRouter, Query
from core.data_processor import load_data
from backend.api.donors import _apply_filters

router = APIRouter(prefix="/api/filters", tags=["Filter Controls"])


@router.get("/options")
def get_filter_options(
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
    if df_raw.empty:
        return {
            "sources": [],
            "headings": [],
            "subheadings": [],
            "countries": [],
            "codes": [],
            "zakat_statuses": ["Zakat", "Zakat Eligible", "Non-Zakat", "Unassigned"],
            "donor_countries": [],
            "gift_aid_options": ["All Gift Aid Status", "Yes", "No"]
        }

    # All sources available in dataset
    sources = []
    if "Source" in df_raw.columns:
        sources = sorted([str(s).strip() for s in df_raw["Source"].dropna().unique() if str(s).strip() != ""])

    # 1. Headings: filter by all active criteria EXCEPT heading itself
    h_df = _apply_filters(df_raw, payment_type, tier, source, None, subheading, country, code, zakat, donor_country, campaign_search, gift_aid)
    headings = []
    if "Heading" in h_df.columns:
        headings = sorted([str(h).strip() for h in h_df["Heading"].dropna().unique() if str(h).strip() not in ["", "nan", "None"]])

    # 2. Sub-headings: filter by all active criteria (including heading) EXCEPT subheading
    sub_df = _apply_filters(df_raw, payment_type, tier, source, heading, None, country, code, zakat, donor_country, campaign_search, gift_aid)
    subheadings = []
    if "Sub-Heading" in sub_df.columns:
        subheadings = sorted([str(sh).strip() for sh in sub_df["Sub-Heading"].dropna().unique() if str(sh).strip() not in ["", "nan", "None"]])

    # 3. Countries: filter by all active criteria EXCEPT country
    c_df = _apply_filters(df_raw, payment_type, tier, source, heading, subheading, None, code, zakat, donor_country, campaign_search, gift_aid)
    countries = []
    if "Country" in c_df.columns:
        countries = sorted([str(c).strip() for c in c_df["Country"].dropna().unique() if str(c).strip() not in ["", "nan", "None"]])

    # 4. Codes: filter by all active criteria EXCEPT code
    cd_df = _apply_filters(df_raw, payment_type, tier, source, heading, subheading, country, None, zakat, donor_country, campaign_search, gift_aid)
    codes = []
    if "Code" in cd_df.columns:
        codes = sorted([str(cd).strip() for cd in cd_df["Code"].dropna().unique() if str(cd).strip() not in ["", "N/A", "nan", "None", "Unassigned"]])

    # 5. Donor Countries: filter by all active criteria EXCEPT donor_country
    dc_df = _apply_filters(df_raw, payment_type, tier, source, heading, subheading, country, code, zakat, None, campaign_search, gift_aid)
    donor_countries = []
    for dc_col in ["Donor Country", "Billing Country", "Country Code"]:
        if dc_col in dc_df.columns:
            donor_countries = sorted([str(dc).strip() for dc in dc_df[dc_col].dropna().unique() if str(dc).strip() not in ["", "N/A", "nan", "None"]])
            break

    return {
        "sources": sources,
        "headings": headings,
        "subheadings": subheadings,
        "countries": countries,
        "codes": codes,
        "zakat_statuses": ["Zakat", "Zakat Eligible", "Non-Zakat", "Unassigned"],
        "donor_countries": donor_countries,
        "gift_aid_options": ["All Gift Aid Status", "Yes", "No"]
    }
