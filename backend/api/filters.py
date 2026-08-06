from typing import Optional
from fastapi import APIRouter, Query
from core.data_processor import load_data

router = APIRouter(prefix="/api/filters", tags=["Filter Controls"])


@router.get("/options")
def get_filter_options(
    source: Optional[str] = None,
    heading: Optional[str] = None,
    country: Optional[str] = None
):
    df = load_data()
    if df.empty:
        return {
            "sources": [],
            "headings": [],
            "subheadings": [],
            "countries": [],
            "codes": [],
            "zakat_statuses": ["Zakat", "Zakat Eligible", "Non-Zakat", "Unassigned"],
            "donor_countries": []
        }

    filtered_df = df.copy()

    if source and source != "All Sources (Combined)" and "Source" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Source"] == source]

    if country and country != "All Project Countries" and "Country" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Country"].astype(str).str.contains(country, case=False, regex=False, na=False)]

    sources = []
    if "Source" in df.columns:
        sources = sorted([str(s).strip() for s in df["Source"].dropna().unique() if str(s).strip() != ""])

    headings = []
    if "Heading" in filtered_df.columns:
        headings = sorted([str(h).strip() for h in filtered_df["Heading"].dropna().unique() if str(h).strip() != ""])

    sub_df = filtered_df.copy()
    if heading and heading != "All Headings" and "Heading" in sub_df.columns:
        sub_df = sub_df[sub_df["Heading"].astype(str).str.strip() == heading]

    subheadings = []
    if "Sub-Heading" in sub_df.columns:
        subheadings = sorted([str(sh).strip() for sh in sub_df["Sub-Heading"].dropna().unique() if str(sh).strip() != ""])

    countries = []
    if "Country" in df.columns:
        countries = sorted([str(c).strip() for c in df["Country"].dropna().unique() if str(c).strip() != ""])

    codes = []
    if "Code" in df.columns:
        codes = sorted([str(cd).strip() for cd in df["Code"].dropna().unique() if str(cd).strip() not in ["", "N/A", "nan", "None"]])

    donor_countries = []
    for dc_col in ["Donor Country", "Billing Country", "Country Code"]:
        if dc_col in df.columns:
            donor_countries = sorted([str(dc).strip() for dc in df[dc_col].dropna().unique() if str(dc).strip() not in ["", "N/A", "nan", "None"]])
            break

    return {
        "sources": sources,
        "headings": headings,
        "subheadings": subheadings,
        "countries": countries,
        "codes": codes,
        "zakat_statuses": ["Zakat", "Zakat Eligible", "Non-Zakat", "Unassigned"],
        "donor_countries": donor_countries
    }
