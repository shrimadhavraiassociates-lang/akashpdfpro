import json
import os
import hashlib
import streamlit as st
import gspread
import google.auth
from google.oauth2.service_account import Credentials
from datetime import datetime
from dateutil.relativedelta import relativedelta

SHEET_NAME = "PDF_Pro_Users"

# Plan Definitions
PLANS = {
    "None": {"pages": 0, "validity_months": 0},
    "Silver": {"pages": 100, "validity_months": 1}, # 100 pages per month
    "Gold": {"pages": float('inf'), "validity_months": 1}, # Unlimited for 1 month
    "Platinum": {"pages": float('inf'), "validity_months": 12} # Unlimited for 1 year
}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_sheet():
    """Authenticates and returns the Google Sheet object."""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    
    creds = None
    
    # 1. Streamlit Cloud Secrets
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    # 2. Local File (credentials.json) - For local testing
    elif os.path.exists("credentials.json"):
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    # 3. GCP Application Default Credentials (Cloud Run / App Engine)
    else:
        # This allows the app to run on Google Cloud Run using the service's identity
        creds, _ = google.auth.default(scopes=scope)
    
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1

def load_db():
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        
        # If sheet is empty, initialize it
        if not records:
            return init_db(sheet)

        users = {}
        for r in records:
            uname = str(r['username'])
            users[uname] = {
                "password": r['password'],
                "role": r['role'],
                "plan": r['plan'],
                "plan_start_date": r['plan_start_date'],
                "plan_expiry_date": r['plan_expiry_date'],
                "pages_used_cycle": int(r['pages_used_cycle']) if r['pages_used_cycle'] != "" else 0,
                "total_pages_used": int(r['total_pages_used']) if r['total_pages_used'] != "" else 0
            }
        return {"users": users}
    except Exception as e:
        st.error(f"Database Error: {e}")
        return {"users": {}}

def init_db(sheet):
    """Initializes the sheet with headers and default admin."""
    headers = ["username", "password", "role", "plan", "plan_start_date", "plan_expiry_date", "pages_used_cycle", "total_pages_used"]
    
    admin_data = [
        "admin", 
        hash_password("9157199960"), 
        "admin", 
        "Admin", 
        str(datetime.now().date()), 
        str((datetime.now() + relativedelta(years=100)).date()), 
        0, 
        0
    ]
    
    sheet.clear()
    sheet.append_row(headers)
    sheet.append_row(admin_data)
    
    # Return the structure so the app can continue without reloading
    return load_db()

def save_db(db):
    sheet = get_sheet()
    headers = ["username", "password", "role", "plan", "plan_start_date", "plan_expiry_date", "pages_used_cycle", "total_pages_used"]
    
    # Prepare data for bulk update
    data = [headers]
    for uname, info in db["users"].items():
        row = [
            uname,
            info["password"],
            info["role"],
            info["plan"],
            info["plan_start_date"],
            info["plan_expiry_date"],
            info["pages_used_cycle"],
            info["total_pages_used"]
        ]
        data.append(row)
    
    # Clear and write all (Simple approach for small user base)
    sheet.clear()
    sheet.update(data)

def register_user(username, password):
    db = load_db()
    if username in db["users"]:
        return False, "Username already taken."
    
    db["users"][username] = {
        "password": hash_password(password),
        "role": "user",
        "plan": "None",
        "plan_start_date": str(datetime.now().date()),
        "plan_expiry_date": str(datetime.now().date()),
        "pages_used_cycle": 0,
        "total_pages_used": 0
    }
    save_db(db)
    return True, "Registration successful. Please ask Admin to assign a plan."

def authenticate(username, password):
    db = load_db()
    if username not in db["users"]:
        return False, None
    
    user = db["users"][username]
    if user["password"] == hash_password(password):
        return True, user
    return False, None

def assign_plan(username, plan_type):
    if plan_type not in PLANS:
        return False, "Invalid plan type."
    
    db = load_db()
    if username not in db["users"]:
        return False, "User not found."
    
    plan_info = PLANS[plan_type]
    now = datetime.now().date()
    
    # Calculate expiry
    if plan_info["validity_months"] > 0:
        expiry = now + relativedelta(months=plan_info["validity_months"])
    else:
        expiry = now # Expired immediately

    db["users"][username]["plan"] = plan_type
    db["users"][username]["plan_start_date"] = str(now)
    db["users"][username]["plan_expiry_date"] = str(expiry)
    db["users"][username]["pages_used_cycle"] = 0 # Reset usage on new plan
    
    save_db(db)
    return True, f"Assigned {plan_type} to {username}."

def check_quota(username, pages_to_process):
    db = load_db()
    user = db["users"].get(username)
    if not user: return False, "User not found."
    if user["role"] == "admin": return True, "Admin"

    plan = user.get("plan", "None")
    if plan == "None":
        return False, "No active plan. Contact Admin."

    # Check Expiry
    expiry = datetime.strptime(user["plan_expiry_date"], "%Y-%m-%d").date()
    if datetime.now().date() > expiry:
        return False, "Plan expired. Contact Admin."

    # Check Silver Plan Quota (Monthly Reset Logic)
    if plan == "Silver":
        start_date = datetime.strptime(user["plan_start_date"], "%Y-%m-%d").date()
        today = datetime.now().date()
        
        # Calculate months passed since start
        months_passed = (today.year - start_date.year) * 12 + (today.month - start_date.month)
        
        # If we are in a new month relative to start date, logic could be complex.
        # Simplified: Reset usage if the 'cycle' date has passed. 
        # For simplicity in this file-based DB, we just check total limit. 
        # Real implementation: Store 'last_reset_date'.
        # Here: We assume 'pages_used_cycle' is manually reset or reset on plan renewal.
        # Let's implement a basic auto-reset if needed, but for now strict 100 limit per cycle.
        
        limit = PLANS["Silver"]["pages"]
        if user["pages_used_cycle"] + pages_to_process > limit:
            return False, f"Quota exceeded. Used: {user['pages_used_cycle']}/{limit} pages."

    return True, "Allowed"

def update_usage(username, pages_processed):
    db = load_db()
    if username in db["users"]:
        db["users"][username]["pages_used_cycle"] += pages_processed
        db["users"][username]["total_pages_used"] += pages_processed
        save_db(db)

def get_user_info(username):
    db = load_db()
    return db["users"].get(username)

def get_all_users():
    db = load_db()
    # Return list of dicts with username included
    users = []
    for k, v in db["users"].items():
        u = v.copy()
        u["username"] = k
        users.append(u)
    return users