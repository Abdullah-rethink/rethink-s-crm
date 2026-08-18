import io
import os
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from config.settings import PARQUET_PATH
from core.data_processor import (
    delete_single_dataset,
    load_data,
    process_and_upload_excel,
    purge_all_data,
    purge_payout_data,
    update_source_tag,
)
from core.database import get_cloud_sync_status

router = APIRouter(prefix="/api/admin", tags=["Admin & Database Management"])


from core.auth import get_all_users, update_user_permissions, edit_user_details


class UpdateUserPermissionRequest(BaseModel):
    user_role: str
    target_email: str
    new_role: str
    can_edit_donors: bool
    can_edit_matrix: bool
    can_manage_tags: bool
    can_purge_data: bool


class EditUserRequest(BaseModel):
    user_role: str
    user_id: int
    email: str
    username: str
    password: str = None  # Optional reset password


class AssignPresetRequest(BaseModel):
    user_role: str
    target_email: str
    preset_name: str  # "super_admin", "admin", "data_editor"


class RenameTagRequest(BaseModel):
    user_role: str
    old_tag: str
    new_tag: str


class DeleteTagRequest(BaseModel):
    user_role: str
    tag_name: str


class PurgeDataRequest(BaseModel):
    user_role: str
    confirm: bool = False


@router.get("/users")
def get_users_list():
    return get_all_users()


@router.post("/users/permissions")
def update_user_permission_endpoint(payload: UpdateUserPermissionRequest):
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Managing user roles and permissions is restricted to Super Admin accounts."
        )

    update_user_permissions(
        payload.target_email,
        payload.new_role,
        payload.can_edit_donors,
        payload.can_edit_matrix,
        payload.can_manage_tags,
        payload.can_purge_data
    )
    return {"status": "success", "message": f"Successfully updated permissions for '{payload.target_email}'."}


@router.post("/users/preset")
def assign_preset_endpoint(payload: AssignPresetRequest):
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assigning role presets is restricted to Super Admin accounts."
        )

    preset = payload.preset_name.lower()
    if preset == "super_admin":
        role, d, m, t, p = "super_admin", 1, 1, 1, 1
    elif preset == "data_editor":
        role, d, m, t, p = "data_editor", 1, 1, 0, 0
    else:  # admin (read-only)
        role, d, m, t, p = "admin", 0, 0, 0, 0

    update_user_permissions(payload.target_email, role, d, m, t, p)
    return {"status": "success", "message": f"Successfully assigned preset '{payload.preset_name}' to '{payload.target_email}'."}


@router.post("/users/edit")
def edit_user_endpoint(payload: EditUserRequest):
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editing user details is restricted to Super Admin accounts."
        )

    if not payload.email.strip() or not payload.username.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and username are required."
        )

    ok, msg = edit_user_details(
        payload.user_id,
        payload.email,
        payload.username,
        payload.password
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {"status": "success", "message": msg}


@router.get("/status")
def get_system_status():
    df_raw = load_data()
    pq_exists = os.path.exists(PARQUET_PATH)
    pq_size = f"{os.path.getsize(PARQUET_PATH) / (1024*1024):.1f} MB" if pq_exists else "N/A"
    sync_info = get_cloud_sync_status()

    return {
        "total_records": len(df_raw),
        "parquet_exists": pq_exists,
        "parquet_size": pq_size,
        "cloud_sync_status": sync_info["status"] if sync_info else "ACTIVE"
    }


@router.get("/tags")
def get_dataset_tags():
    df_raw = load_data()
    if df_raw.empty or "Source" not in df_raw.columns:
        return []

    source_counts = df_raw["Source"].value_counts().reset_index()
    source_counts.columns = ["source_tag", "record_count"]
    return source_counts.to_dict(orient="records")


@router.post("/tags/rename")
def rename_dataset_tag(payload: RenameTagRequest):
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Renaming dataset tags is restricted to Super Admin accounts."
        )

    if not payload.old_tag or not payload.new_tag.strip():
        raise HTTPException(status_code=400, detail="Old tag and new tag name are required.")

    n_updated = update_source_tag(payload.old_tag, payload.new_tag.strip())
    return {
        "status": "success",
        "message": f"Successfully renamed {n_updated:,} records from '{payload.old_tag}' to '{payload.new_tag.strip()}'."
    }


@router.post("/tags/delete")
def delete_dataset_tag(payload: DeleteTagRequest):
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Deleting dataset batches is restricted to Super Admin accounts."
        )

    if not payload.tag_name:
        raise HTTPException(status_code=400, detail="Tag name is required.")

    n_deleted = delete_single_dataset(payload.tag_name)
    return {
        "status": "success",
        "message": f"Successfully deleted dataset batch '{payload.tag_name}' ({n_deleted:,} records removed)."
    }


@router.post("/purge")
def purge_database(payload: PurgeDataRequest):
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Purging all database records is restricted to Super Admin accounts."
        )

    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation is required to purge data.")

    purge_all_data()
    return {
        "status": "success",
        "message": "Database purged cleanly!"
    }


@router.post("/purge-payouts")
def purge_payouts_endpoint(payload: PurgeDataRequest):
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Purging payout data is restricted to Super Admin accounts."
        )

    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation is required to purge payout data.")

    n_purged = purge_payout_data()
    return {
        "status": "success",
        "message": f"Successfully purged LaunchGood payout settlement data! ({n_purged:,} records removed)"
    }


@router.post("/upload-data")
def upload_raw_data_file(
    user_role: str = Form(...),
    upload_mode: str = Form("merge"),  # "merge" or "replace"
    platform: str = Form("auto"),       # "auto", "launchgood", "givebright", "paysuite", "website"
    file: UploadFile = File(...)
):
    """Bulk uploads a raw donation dataset (.csv, .xlsx, .xls) for LaunchGood, GiveBright, Paysuite, or Rethink Website."""
    if user_role not in ["super_admin", "admin", "data_editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Uploading donation datasets requires Data Editor or Admin privileges."
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".csv", ".xlsx", ".xls"]:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a .csv, .xlsx, or .xls file.")

    try:
        file_bytes = file.file.read()
        file_buffer = io.BytesIO(file_bytes)

        res = process_and_upload_excel(
            file_buffer=file_buffer,
            source_name=file.filename,
            upload_mode=upload_mode,
            platform=platform
        )

        if isinstance(res, dict) and res.get("status") == "error":
            raise HTTPException(status_code=400, detail=res.get("message", "Upload failed."))

        return {
            "status": "success",
            "message": f"Successfully processed '{file.filename}'! {res.get('added', 0):,} records imported and auto-classified.",
            "details": res
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process uploaded file: {str(e)}")
