import os
import sqlite3
import uuid
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Optional
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from config.settings import (
    LOCAL_DB_PATH, PARQUET_PATH, APP_BASE_URL, APPROVAL_EMAIL,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_NAME, SMTP_FROM_EMAIL
)
from core.data_processor import load_data, get_classification_matrix
from core.security import encrypt_string, decrypt_string
from backend.api.events import broadcast_event_sync

router = APIRouter(prefix="/api/expenses", tags=["Expense & Payment Tracking"])


def init_expense_db():
    """Initializes expense_requests and system_settings SQLite tables."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expense_requests (
                id TEXT PRIMARY KEY,
                code TEXT,
                heading TEXT,
                sub_heading TEXT,
                country TEXT,
                title TEXT,
                vendor TEXT,
                amount REAL,
                payment_date TEXT,
                notes TEXT,
                status TEXT DEFAULT 'PENDING_APPROVAL',
                requested_by TEXT,
                reviewed_by TEXT,
                review_notes TEXT,
                approval_token TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Seed SMTP settings from .env as defaults (INSERT OR IGNORE = only on first run)
        smtp_defaults = [
            ('approval_email', APPROVAL_EMAIL),
            ('smtp_host', SMTP_HOST),
            ('smtp_port', str(SMTP_PORT)),
            ('smtp_user', SMTP_USER),
            ('smtp_password', SMTP_PASSWORD),
            ('smtp_from_name', SMTP_FROM_NAME),
            ('smtp_from_email', SMTP_FROM_EMAIL),
        ]
        cursor.executemany("""
            INSERT OR IGNORE INTO system_settings (setting_key, setting_value)
            VALUES (?, ?);
        """, smtp_defaults)

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Expense DB init notice: {e}")


init_expense_db()


class SubmitExpenseRequest(BaseModel):
    code: str
    title: str
    vendor: str
    amount: float
    payment_date: str
    notes: Optional[str] = ""
    requested_by: Optional[str] = "Admin User"


class ReviewExpenseRequest(BaseModel):
    expense_id: str
    user_role: str
    action: str  # "APPROVED" or "REJECTED"
    review_notes: Optional[str] = ""
    can_edit_donors: Optional[bool] = False


class UpdateApprovalEmailRequest(BaseModel):
    user_role: str
    approval_email: str


class UpdateSmtpSettingsRequest(BaseModel):
    user_role: str
    approval_email: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str  # send empty string to keep existing password unchanged
    smtp_from_name: str
    smtp_from_email: str


class TestEmailRequest(BaseModel):
    user_role: str
    can_edit_donors: Optional[bool] = False


class DeleteExpenseRequest(BaseModel):
    expense_id: str
    user_role: str
    can_edit_donors: Optional[bool] = False


def _get_smtp_config():
    """Fetches all SMTP + approval settings from DB. Falls back to .env values."""
    defaults = {
        'approval_email': APPROVAL_EMAIL,
        'smtp_host': SMTP_HOST,
        'smtp_port': str(SMTP_PORT),
        'smtp_user': SMTP_USER,
        'smtp_password': SMTP_PASSWORD,
        'smtp_from_name': SMTP_FROM_NAME,
        'smtp_from_email': SMTP_FROM_EMAIL,
    }
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("SELECT setting_key, setting_value FROM system_settings")
        rows = cursor.fetchall()
        conn.close()
        for key, val in rows:
            if key in defaults and val is not None:
                if key == 'smtp_password':
                    defaults[key] = decrypt_string(val)
                else:
                    defaults[key] = val
    except Exception:
        pass
    return defaults


def _get_approval_email():
    """Fetches the current approval email from system settings."""
    return _get_smtp_config().get('approval_email', APPROVAL_EMAIL)


def _send_smtp_email(smtp_cfg: dict, to_email: str, subject: str, html_body: str, plain_body: str):
    """Sends an email using the provided SMTP config dict. Returns (success, error_msg)."""
    smtp_user = smtp_cfg.get('smtp_user', '')
    smtp_password = smtp_cfg.get('smtp_password', '')
    smtp_host = smtp_cfg.get('smtp_host', 'smtp.gmail.com')
    smtp_port = int(smtp_cfg.get('smtp_port', 587))
    smtp_from_name = smtp_cfg.get('smtp_from_name', 'Rethink Charity CRM')
    smtp_from_email = smtp_cfg.get('smtp_from_email', '') or smtp_user

    if not smtp_user or not smtp_password:
        return False, "SMTP credentials not configured. Set SMTP User and Password in Email Settings."

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{smtp_from_name} <{smtp_from_email}>"
        msg["To"] = to_email
        msg["Reply-To"] = smtp_from_email
        msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from_email, [to_email], msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)


def dispatch_approval_email(expense_id: str, title: str, amount: float, code: str, requested_by: str, token: str):
    """Generates direct approval links and dispatches approval notification via real SMTP email."""
    smtp_cfg = _get_smtp_config()
    dest_email = smtp_cfg.get('approval_email', APPROVAL_EMAIL)

    approve_url = f"{APP_BASE_URL}/api/expenses/action-email?id={expense_id}&token={token}&action=APPROVED"
    reject_url = f"{APP_BASE_URL}/api/expenses/action-email?id={expense_id}&token={token}&action=REJECTED"

    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0F172A; color: #F8FAFC; border-radius: 16px; overflow: hidden; border: 1px solid rgba(255,255,255,0.1);">
      <div style="background: linear-gradient(135deg, #06B6D4, #0284C7); padding: 24px 32px;">
        <h1 style="margin: 0; font-size: 18px; font-weight: 800; color: #FFFFFF;">⚡ Expense Approval Required</h1>
        <p style="margin: 4px 0 0; font-size: 12px; color: rgba(255,255,255,0.8);">Rethink Charity — CRM Expense Tracker</p>
      </div>
      <div style="padding: 28px 32px;">
        <p style="font-size: 14px; color: #94A3B8; margin: 0 0 20px;">A new project expense request requires your Super Admin approval:</p>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px;">
          <tr><td style="padding: 8px 0; font-size: 12px; color: #64748B; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; width: 40%;">Claim ID</td><td style="padding: 8px 0; font-size: 14px; color: #38BDF8; font-weight: 700; font-family: monospace;">{expense_id}</td></tr>
          <tr><td style="padding: 8px 0; font-size: 12px; color: #64748B; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">Project Code</td><td style="padding: 8px 0; font-size: 14px; color: #8B5CF6; font-weight: 700; font-family: monospace;">{code}</td></tr>
          <tr><td style="padding: 8px 0; font-size: 12px; color: #64748B; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">Expense Title</td><td style="padding: 8px 0; font-size: 14px; color: #F8FAFC; font-weight: 600;">{title}</td></tr>
          <tr><td style="padding: 8px 0; font-size: 12px; color: #64748B; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">Amount</td><td style="padding: 8px 0; font-size: 20px; color: #10B981; font-weight: 800;">£{amount:,.2f}</td></tr>
          <tr><td style="padding: 8px 0; font-size: 12px; color: #64748B; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">Submitted By</td><td style="padding: 8px 0; font-size: 14px; color: #F8FAFC;">{requested_by}</td></tr>
        </table>
        <div style="display: flex; gap: 12px; margin-top: 8px;">
          <a href="{approve_url}" style="display: inline-block; padding: 12px 28px; background: linear-gradient(135deg, #10B981, #059669); color: #FFFFFF; text-decoration: none; border-radius: 10px; font-weight: 800; font-size: 14px; text-align: center;">✓ APPROVE</a>
          <a href="{reject_url}" style="display: inline-block; padding: 12px 28px; background: linear-gradient(135deg, #F43F5E, #E11D48); color: #FFFFFF; text-decoration: none; border-radius: 10px; font-weight: 800; font-size: 14px; text-align: center;">✗ REJECT</a>
        </div>
      </div>
      <div style="background: rgba(15,23,42,0.5); padding: 16px 32px; border-top: 1px solid rgba(255,255,255,0.05);">
        <p style="margin: 0; font-size: 11px; color: #475569;">This email was generated by the Rethink Charity CRM. If you did not expect this, please contact your system administrator.</p>
      </div>
    </div>
    """
    plain_body = f"""EXPENSE APPROVAL NOTIFICATION\n==============================\nClaim ID: {expense_id}\nProject Code: {code}\nExpense Title: {title}\nAmount: GBP {amount:,.2f}\nSubmitted By: {requested_by}\n\nAPPROVE: {approve_url}\nREJECT: {reject_url}"""

    subject = f"[Action Required] Expense Claim Approval: {expense_id} (GBP {amount:,.2f})"
    email_sent, send_error = _send_smtp_email(smtp_cfg, dest_email, subject, html_body, plain_body)

    print(f"--- Approval Email Log ---")
    print(f"  To: {dest_email} | Sent: {email_sent}")
    print(f"  APPROVE URL: {approve_url}")
    print(f"  REJECT URL:  {reject_url}")
    if send_error:
        print(f"  Error: {send_error}")
    print(f"--------------------------")

    return dest_email, approve_url, reject_url, email_sent, send_error


@router.get("/codes")
def get_project_codes():
    """Returns unique list of project codes with real-time Gross Raised, Approved Expenses, and Net Balance."""
    df_raw = load_data()
    matrix_df = get_classification_matrix(df_raw).fillna("Unassigned")

    init_expense_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("SELECT code, SUM(amount) FROM expense_requests WHERE status = 'APPROVED' GROUP BY code")
    approved_expense_map = {row[0]: row[1] for row in cursor.fetchall() if row[0]}
    conn.close()

    col_amount = "Total Online Donations Net Amount in Settled Currency"
    if col_amount not in df_raw.columns:
        col_amount = "Donation Amount in Project Currency (May be approx.)"

    code_map = {}

    if not df_raw.empty and "Code" in df_raw.columns:
        for code_val, group in df_raw.groupby("Code", dropna=True):
            code_str = str(code_val).strip()
            if code_str and code_str not in ["N/A", "Unassigned", "nan", "None"]:
                first_row = group.iloc[0]
                gross_raised = float(group[col_amount].sum()) if col_amount in group.columns else 0.0
                app_expense = approved_expense_map.get(code_str, 0.0)
                
                code_map[code_str] = {
                    "code": code_str,
                    "heading": str(first_row.get("Heading", "Unassigned")),
                    "sub_heading": str(first_row.get("Sub-Heading", "Unassigned")),
                    "country": str(first_row.get("Country", "Unassigned")),
                    "campaign_name": str(first_row.get("Campaign Name", "N/A")),
                    "gross_raised": round(gross_raised, 2),
                    "approved_expenses": round(app_expense, 2),
                    "net_balance": round(gross_raised - app_expense, 2)
                }

    if not matrix_df.empty and "Code" in matrix_df.columns:
        for _, r in matrix_df.iterrows():
            code_str = str(r.get("Code", "")).strip()
            if code_str and code_str in code_map:
                if code_map[code_str]["heading"] == "Unassigned" and r.get("Heading") != "Unassigned":
                    code_map[code_str]["heading"] = str(r.get("Heading"))
                if code_map[code_str]["sub_heading"] == "Unassigned" and r.get("Sub-Heading") != "Unassigned":
                    code_map[code_str]["sub_heading"] = str(r.get("Sub-Heading"))
                if code_map[code_str]["country"] == "Unassigned" and r.get("Country") != "Unassigned":
                    code_map[code_str]["country"] = str(r.get("Country"))

    sorted_codes = sorted(list(code_map.values()), key=lambda x: x["code"])
    return sorted_codes


@router.get("/requests")
def get_expense_requests(status_filter: Optional[str] = "ALL"):
    """Returns list of expense requests and summary metrics."""
    init_expense_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM expense_requests"
    params = []
    if status_filter and status_filter != "ALL":
        query += " WHERE status = ?"
        params.append(status_filter)
    
    query += " ORDER BY created_at DESC"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT status, SUM(amount), COUNT(*) FROM expense_requests GROUP BY status")
    kpi_rows = cursor.fetchall()
    
    total_requested = 0.0
    total_approved = 0.0
    total_pending = 0.0
    total_rejected = 0.0

    count_approved = 0
    count_pending = 0
    count_rejected = 0

    for r in kpi_rows:
        st, amt, cnt = r[0], r[1] or 0.0, r[2] or 0
        total_requested += amt
        if st == "APPROVED":
            total_approved += amt
            count_approved += cnt
        elif st == "PENDING_APPROVAL":
            total_pending += amt
            count_pending += cnt
        elif st == "REJECTED":
            total_rejected += amt
            count_rejected += cnt

    conn.close()

    return {
        "summary": {
            "total_requested": round(total_requested, 2),
            "total_approved": round(total_approved, 2),
            "total_pending": round(total_pending, 2),
            "total_rejected": round(total_rejected, 2),
            "count_approved": count_approved,
            "count_pending": count_pending,
            "count_rejected": count_rejected,
            "total_count": len(rows)
        },
        "expenses": rows
    }


@router.post("/submit")
def submit_expense(payload: SubmitExpenseRequest):
    """Submits a new project expense request with deduplication guard and dispatches approval notification email."""
    init_expense_db()
    
    # ----- Deduplication Guard -----
    # Prevent duplicate submissions with same code + title + amount + payment_date within 60 seconds
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, created_at FROM expense_requests 
        WHERE code = ? AND title = ? AND amount = ? AND payment_date = ?
        AND created_at >= datetime('now', '-60 seconds')
        ORDER BY created_at DESC LIMIT 1
    """, (payload.code.strip(), payload.title.strip(), payload.amount, payload.payment_date))
    
    dup_row = cursor.fetchone()
    conn.close()
    
    if dup_row:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate expense detected! An identical claim ({dup_row[0]}) was submitted within the last 60 seconds for code '{payload.code}', title '{payload.title}', amount £{payload.amount:,.2f}. Please wait or modify the details."
        )
    
    # ----- Resolve Classification Details -----
    df_raw = load_data()
    matrix_df = get_classification_matrix(df_raw).fillna("Unassigned")
    
    heading, sub_heading, country = "Unassigned", "Unassigned", "Unassigned"
    target_code = payload.code.strip().lower()

    if not df_raw.empty and "Code" in df_raw.columns:
        match_df = df_raw[df_raw["Code"].astype(str).str.strip().str.lower() == target_code]
        if not match_df.empty:
            first_r = match_df.iloc[0]
            heading = str(first_r.get("Heading", "Unassigned"))
            sub_heading = str(first_r.get("Sub-Heading", "Unassigned"))
            country = str(first_r.get("Country", "Unassigned"))

    if heading == "Unassigned" and not matrix_df.empty and "Code" in matrix_df.columns:
        for _, r in matrix_df.iterrows():
            if str(r.get("Code", "")).strip().lower() == target_code:
                heading = str(r.get("Heading", "Unassigned"))
                sub_heading = str(r.get("Sub-Heading", "Unassigned"))
                country = str(r.get("Country", "Unassigned"))
                break

    expense_id = f"EXP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    token = uuid.uuid4().hex

    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO expense_requests 
        (id, code, heading, sub_heading, country, title, vendor, amount, payment_date, notes, status, requested_by, approval_token)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', ?, ?)
    """, (
        expense_id, payload.code.strip(), heading, sub_heading, country,
        payload.title.strip(), payload.vendor.strip(), payload.amount, payload.payment_date,
        payload.notes, payload.requested_by, token
    ))
    conn.commit()
    conn.close()

    dest_email, approve_url, reject_url, email_sent, send_error = dispatch_approval_email(
        expense_id, payload.title.strip(), payload.amount, payload.code.strip(), payload.requested_by, token
    )

    broadcast_event_sync("EXPENSE_SUBMITTED", {"id": expense_id, "code": payload.code.strip(), "amount": payload.amount})

    result = {
        "status": "success",
        "expense_id": expense_id,
        "approval_email_sent_to": dest_email,
        "email_actually_sent": email_sent,
        "approve_url": approve_url,
        "reject_url": reject_url,
        "message": f"Expense claim {expense_id} submitted! Approval notification dispatched to '{dest_email}'."
    }
    if not email_sent:
        result["email_warning"] = f"Email could not be sent: {send_error}. Configure SMTP_USER and SMTP_PASSWORD in .env to enable email delivery."
    
    return result


@router.post("/review")
def review_expense(payload: ReviewExpenseRequest):
    """Approve or Reject an expense request from Super Admin UI."""
    if payload.user_role != "super_admin" and not payload.can_edit_donors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Approving/Rejecting expense requests is restricted to Super Admins."
        )

    action_status = payload.action.upper()
    if action_status not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Invalid action. Must be APPROVED or REJECTED.")

    init_expense_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE expense_requests 
        SET status = ?, reviewed_by = ?, review_notes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (action_status, payload.user_role, payload.review_notes, payload.expense_id))
    
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()

    if rows_affected == 0:
        raise HTTPException(status_code=404, detail="Expense request ID not found.")

    broadcast_event_sync("EXPENSE_REVIEWED", {"id": payload.expense_id, "action": action_status})

    return {
        "status": "success",
        "message": f"Expense request {payload.expense_id} has been {action_status}!"
    }


@router.post("/delete")
def delete_expense(payload: DeleteExpenseRequest):
    """Delete an expense request. Only Super Admins can delete."""
    if payload.user_role != "super_admin" and not payload.can_edit_donors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Deleting expense requests is restricted to Super Admins."
        )

    init_expense_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    
    # Fetch the expense first to return info
    cursor.execute("SELECT id, code, title, amount, status FROM expense_requests WHERE id = ?", (payload.expense_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Expense request '{payload.expense_id}' not found.")
    
    exp_id, exp_code, exp_title, exp_amount, exp_status = row
    
    cursor.execute("DELETE FROM expense_requests WHERE id = ?", (payload.expense_id,))
    conn.commit()
    conn.close()

    broadcast_event_sync("EXPENSE_DELETED", {"id": payload.expense_id, "code": exp_code})

    return {
        "status": "success",
        "message": f"Expense '{exp_id}' (Code: {exp_code}, £{exp_amount:,.2f}) has been permanently deleted.",
        "deleted_expense": {
            "id": exp_id,
            "code": exp_code,
            "title": exp_title,
            "amount": exp_amount,
            "previous_status": exp_status
        }
    }


@router.get("/action-email")
def handle_email_approval(id: str, token: str, action: str):
    """Handles email link approval/rejection sync."""
    action_status = action.upper()
    if action_status not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Invalid action.")

    init_expense_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE expense_requests 
        SET status = ?, reviewed_by = 'Super Admin (via Email Link)', updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND approval_token = ?
    """, (action_status, id, token))
    
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()

    if rows_affected == 0:
        return {"status": "error", "message": "Invalid link or token expired."}

    broadcast_event_sync("EXPENSE_REVIEWED", {"id": id, "action": action_status, "source": "email_link"})

    return {
        "status": "success",
        "message": f"Expense request {id} has been marked as {action_status} via email sync!"
    }


@router.get("/settings")
def get_expense_settings():
    """Returns all SMTP + approval email settings. Password is masked."""
    init_expense_db()
    cfg = _get_smtp_config()
    smtp_configured = bool(cfg.get('smtp_user') and cfg.get('smtp_password'))
    password_set = bool(cfg.get('smtp_password'))

    return {
        "approval_email": cfg.get('approval_email', ''),
        "smtp_host": cfg.get('smtp_host', 'smtp.gmail.com'),
        "smtp_port": int(cfg.get('smtp_port', 587)),
        "smtp_user": cfg.get('smtp_user', ''),
        "smtp_password_set": password_set,   # never return the actual password
        "smtp_from_name": cfg.get('smtp_from_name', 'Rethink Charity CRM'),
        "smtp_from_email": cfg.get('smtp_from_email', ''),
        "smtp_configured": smtp_configured,
    }


@router.post("/settings")
def update_expense_settings(payload: UpdateSmtpSettingsRequest):
    """Updates all SMTP + approval email settings. Super Admin only."""
    if payload.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Updating email settings is restricted to Super Admins."
        )

    init_expense_db()
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    cursor = conn.cursor()

    upsert = """
        INSERT INTO system_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(setting_key) DO UPDATE
        SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP
    """

    updates = [
        ('approval_email', payload.approval_email.strip()),
        ('smtp_host', payload.smtp_host.strip()),
        ('smtp_port', str(payload.smtp_port)),
        ('smtp_user', payload.smtp_user.strip()),
        ('smtp_from_name', payload.smtp_from_name.strip()),
        ('smtp_from_email', payload.smtp_from_email.strip()),
    ]
    cursor.executemany(upsert, updates)

    # Only update password if a new one was provided (non-empty)
    if payload.smtp_password.strip():
        encrypted_pwd = encrypt_string(payload.smtp_password.strip())
        cursor.execute(upsert, ('smtp_password', encrypted_pwd))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": "Email & SMTP settings saved successfully!"
    }


@router.post("/test-email")
def test_smtp_email(payload: TestEmailRequest):
    """Sends a test email using current SMTP settings. Super Admin only."""
    if payload.user_role != "super_admin" and not payload.can_edit_donors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sending test emails is restricted to Super Admins."
        )

    init_expense_db()
    smtp_cfg = _get_smtp_config()
    dest_email = smtp_cfg.get('approval_email', APPROVAL_EMAIL)

    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 560px; margin: 0 auto; background: #0F172A; border-radius: 16px; overflow: hidden; border: 1px solid rgba(255,255,255,0.1);">
      <div style="background: linear-gradient(135deg, #8B5CF6, #06B6D4); padding: 24px 32px;">
        <h1 style="margin: 0; font-size: 18px; font-weight: 800; color: #fff;">✅ SMTP Test Email</h1>
        <p style="margin: 4px 0 0; font-size: 12px; color: rgba(255,255,255,0.8);">Rethink Charity CRM — Email Settings</p>
      </div>
      <div style="padding: 28px 32px; color: #94A3B8; font-size: 14px; line-height: 1.6;">
        <p>Your SMTP configuration is working correctly! 🎉</p>
        <p style="margin-top: 16px; font-size: 12px; color: #475569;">
          Server: <strong style="color: #38BDF8;">{smtp_cfg.get('smtp_host')}:{smtp_cfg.get('smtp_port')}</strong><br>
          Sender: <strong style="color: #38BDF8;">{smtp_cfg.get('smtp_from_name')} &lt;{smtp_cfg.get('smtp_from_email') or smtp_cfg.get('smtp_user')}&gt;</strong>
        </p>
      </div>
    </div>
    """
    plain_body = "SMTP Test Email from Rethink Charity CRM — your configuration is working correctly!"
    subject = "[CRM Test] SMTP Configuration Verified — Rethink Charity"

    success, error = _send_smtp_email(smtp_cfg, dest_email, subject, html_body, plain_body)

    if success:
        return {"status": "success", "message": f"Test email sent successfully to '{dest_email}'! Check your inbox."}
    else:
        raise HTTPException(status_code=500, detail=f"Test email failed: {error}")
