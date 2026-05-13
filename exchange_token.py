import requests
import os
from pathlib import Path

API_KEY = os.getenv("UPSTOX_API_KEY", "")
API_SECRET = os.getenv("UPSTOX_API_SECRET", "")
AUTH_CODE = os.getenv("UPSTOX_AUTH_CODE", "")

REDIRECT_URI = "http://localhost"
API_KEYS_FILE = Path("config/api_keys.py")


def mask_secret(value):
    text = str(value or "")
    if len(text) <= 8:
        return "***" if text else "missing"
    return f"{text[:4]}...{text[-4:]}"


def save_token_to_api_keys(token):
    print(f"Upstox token received: {mask_secret(token)}")
    print("Token not written to source files. Store the full token in UPSTOX_ACCESS_TOKEN.")


url = "https://api.upstox.com/v2/login/authorization/token"

if not API_KEY or not API_SECRET or not AUTH_CODE:
    print("Upstox API key/secret/auth code missing. Set UPSTOX_API_KEY, UPSTOX_API_SECRET, and UPSTOX_AUTH_CODE.")
    raise SystemExit

headers = {
    "accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
}

data = {
    "code": AUTH_CODE,
    "client_id": API_KEY,
    "client_secret": API_SECRET,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
}

response = requests.post(url, headers=headers, data=data, timeout=15)

print("Status:", response.status_code)
result = response.json()
safe_result = {k: (mask_secret(v) if "token" in k.lower() else v) for k, v in result.items()}
print("Response:", safe_result)

if response.status_code == 200 and "access_token" in result:
    save_token_to_api_keys(result["access_token"])
    print("✅ Upstox access token received and masked.")
else:
    print("❌ Token not saved. Check API key, secret, auth code, or plan confirmation.")
