import json
import os
import hashlib
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta

DB_FILE = "users_db.json"

# Plan Definitions
PLANS = {
    "None": {"pages": 0, "validity_months": 0},
    "Silver": {"pages": 100, "validity_months": 1}, # 100 pages per month
    "Gold": {"pages": float('inf'), "validity_months": 1}, # Unlimited for 1 month
    "Platinum": {"pages": float('inf'), "validity_months": 12} # Unlimited for 1 year
}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_db():
    if not os.path.exists(DB_FILE):
        return init_db()
    
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Database Error: {e}")
        return {"users": {}}

def init_db():
    """Initializes the local JSON DB with default admin."""
    admin_data = {
        "password": hash_password("9157199960"),
        "role": "admin",
        "plan": "Admin",
        "plan_start_date": str(datetime.now().date()),
        "plan_expiry_date": str((datetime.now() + relativedelta(years=100)).date()),
        "pages_used_cycle": 0,
        "total_pages_used": 0
    }
    
    db = {"users": {"admin": admin_data}}
    save_db(db)
    return db

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

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