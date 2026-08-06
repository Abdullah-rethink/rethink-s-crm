from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from core.data_processor import (
    get_classification_matrix,
    load_data,
    save_classification_matrix,
)
from views.classification_view import (
    get_givebright_classification_matrix,
    save_givebright_classification_matrix,
)

router = APIRouter(prefix="/api/classifications", tags=["Campaign Classifications"])


class RuleRow(BaseModel):
    campaign_name: str
    community_name: Optional[str] = "Unassigned"
    heading: Optional[str] = "Unassigned"
    sub_heading: Optional[str] = "Unassigned"
    country: Optional[str] = "Unassigned"
    code: Optional[str] = "Unassigned"
    zakat_eligibility: Optional[str] = "Unassigned"


class SaveRulesRequest(BaseModel):
    user_role: str
    platform: str  # "launchgood" or "givebright"
    rules: List[dict]
    can_edit_matrix: Optional[bool] = False


@router.get("/launchgood")
def get_launchgood_matrix():
    df_raw = load_data()
    matrix_df = get_classification_matrix(df_raw).fillna("Unassigned")
    unassigned_count = (matrix_df["Heading"] == "Unassigned").sum() if "Heading" in matrix_df.columns else 0
    return {
        "platform": "LaunchGood",
        "total_campaigns": len(matrix_df),
        "classified_campaigns": int(len(matrix_df) - unassigned_count),
        "unassigned_campaigns": int(unassigned_count),
        "rules": matrix_df.to_dict(orient="records")
    }


@router.get("/givebright")
def get_givebright_matrix():
    df_raw = load_data()
    matrix_df = get_givebright_classification_matrix(df_raw).fillna("Unassigned")
    unassigned_count = (matrix_df["Heading"] == "Unassigned").sum() if "Heading" in matrix_df.columns else 0
    return {
        "platform": "GiveBright",
        "total_campaigns": len(matrix_df),
        "classified_campaigns": int(len(matrix_df) - unassigned_count),
        "unassigned_campaigns": int(unassigned_count),
        "rules": matrix_df.to_dict(orient="records")
    }


@router.post("/save")
def save_matrix_rules(payload: SaveRulesRequest):
    if payload.user_role != "super_admin" and not payload.can_edit_matrix:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Modifying campaign classification matrix rules is restricted to authorized accounts."
        )

    rules_dict = []
    for r in payload.rules:
        rules_dict.append({
            "Campaign Name": r.get("Campaign Name") or r.get("campaign_name", "N/A"),
            "Community Name": r.get("Community Name") or r.get("community_name", "N/A"),
            "Heading": r.get("Heading") or r.get("heading", "Unassigned"),
            "Sub-Heading": r.get("Sub-Heading") or r.get("sub_heading", "Unassigned"),
            "Country": r.get("Country") or r.get("country", "Unassigned"),
            "Code": r.get("Code") or r.get("code", "N/A"),
            "Zakat Eligibility": r.get("Zakat Eligibility") or r.get("zakat_eligibility", "Unassigned")
        })
    import pandas as pd
    matrix_df = pd.DataFrame(rules_dict)

    if payload.platform.lower() == "givebright":
        n_saved = save_givebright_classification_matrix(matrix_df)
    else:
        n_saved = save_classification_matrix(matrix_df)

    # Automatically sync classification rules to update all donor data!
    from core.data_processor import sync_matrix_classifications_to_donors
    donors_updated = sync_matrix_classifications_to_donors(matrix_df)

    return {
        "status": "success",
        "message": f"Successfully saved {n_saved:,} {payload.platform} classification rules and updated {donors_updated:,} matching donor records!"
    }
