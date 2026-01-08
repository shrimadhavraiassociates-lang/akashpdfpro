import json
import base64
import hashlib
import time
from datetime import datetime, timedelta
import os

# You can change this secret; keep it same for all apps sharing licenses
SECRET_KEY = b"SuperSecretKey1234"
ADMIN_PASS_FILE = os.path.expanduser("~/.sma_admin_password.json")
LICENSE_FILE = os.path.expanduser("~/.sma_bank_license.json")

def sign_data(data_str: str) -> str:
    h = hashlib.sha256()
    h.update(SECRET_KEY)
    h.update(data_str.encode())
    return base64.urlsafe_b64encode(h.digest()).decode()

def verify_signature(data_str: str, signature: str) -> bool:
    return sign_data(data_str) == signature

def generate_license(name: str, email: str, mobile: str, machine_id: str, days_valid: float, trial: bool = False) -> str:
    issued_at = int(time.time())
    license_data = {
        "name": name,
        "email": email,
        "mobile": mobile,
        "machine_id": machine_id,
        "days_valid": days_valid,
        "issued_at": issued_at,
        "trial": trial
    }
    json_str = json.dumps(license_data, sort_keys=True)
    signature = sign_data(json_str)
    packaged = {"data": license_data, "sig": signature}
    encoded_license = base64.urlsafe_b64encode(json.dumps(packaged).encode()).decode()
    return encoded_license

def verify_license_key(license_key: str, machine_id: str):
    try:
        # Fix missing padding if user copied incorrectly
        missing_padding = len(license_key) % 4
        if missing_padding:
            license_key += '=' * (4 - missing_padding)
            
        decoded = base64.urlsafe_b64decode(license_key)
        package = json.loads(decoded)
        data = package["data"]
        sig = package["sig"]
        json_str = json.dumps(data, sort_keys=True)

        if not verify_signature(json_str, sig):
            return False, "Invalid signature"
        if data["machine_id"] != machine_id:
            return False, "License for different machine"
        issued_at = datetime.fromtimestamp(data["issued_at"])
        if data.get("trial", False):
            expiry = issued_at + timedelta(hours=1)
        else:
            expiry = issued_at + timedelta(days=data.get("days_valid", 0))
        if datetime.now() > expiry:
            return False, "License expired"
        return True, data
    except Exception as e:
        return False, f"Invalid license format ({e})"

def save_license_to_file(license_key: str, trial_used: bool = False) -> None:
    data = {"license": license_key}
    if trial_used:
        data["trial_used"] = True
    with open(LICENSE_FILE, "w") as f:
        json.dump(data, f)

def load_license_from_file():
    try:
        with open(LICENSE_FILE, "r") as f:
            data = json.load(f)
            return data.get("license"), data.get("trial_used", False)
    except FileNotFoundError:
        return None, False

def has_trial_been_used():
    _, used = load_license_from_file()
    return used

def save_admin_password(password: str) -> None:
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    with open(ADMIN_PASS_FILE, "w") as f:
        json.dump({"password_hash": pwd_hash}, f)

def load_admin_password_hash():
    try:
        with open(ADMIN_PASS_FILE, "r") as f:
            data = json.load(f)
            return data.get("password_hash")
    except FileNotFoundError:
        return None

def verify_admin_password(password: str) -> bool:
    stored_hash = load_admin_password_hash()
    if stored_hash is None:
        # For first use, set default password
        save_admin_password("Madhav#1996")
        stored_hash = load_admin_password_hash()
    return hashlib.sha256(password.encode()).hexdigest() == stored_hash

def format_license_remaining(data: dict) -> str:
    issued = datetime.fromtimestamp(data.get("issued_at"))
    if data.get("trial"):
        expiry = issued + timedelta(hours=1)
    else:
        expiry = issued + timedelta(days=data.get("days_valid", 0))
    remaining = expiry - datetime.now()
    if remaining.total_seconds() < 0:
        return "Expired"
    days, seconds = remaining.days, remaining.seconds
    if days > 365:
        return f"{days // 365} year(s)"
    elif days > 30:
        return f"{days // 30} month(s)"
    elif days > 7:
        return f"{days // 7} week(s)"
    elif days > 0:
        return f"{days} day(s)"
    elif seconds > 3600:
        return f"{seconds // 3600} hour(s)"
    elif seconds > 60:
        return f"{seconds // 60} minute(s)"
    else:
        return f"{seconds} second(s)"
