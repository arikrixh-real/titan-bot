import requests
import webbrowser
import os

API_KEY = os.getenv("UPSTOX_API_KEY", "")
API_SECRET = os.getenv("UPSTOX_API_SECRET", "")

REDIRECT_URI = "http://localhost"


def mask_secret(value):
    text = str(value or "")
    if len(text) <= 8:
        return "***" if text else "missing"
    return f"{text[:4]}...{text[-4:]}"

auth_url = (
    "https://api.upstox.com/v2/login/authorization/dialog"
    f"?response_type=code"
    f"&client_id={API_KEY}"
    f"&redirect_uri={REDIRECT_URI}"
)

if not API_KEY or not API_SECRET:
    print("Upstox API key/secret missing. Set UPSTOX_API_KEY and UPSTOX_API_SECRET.")
    raise SystemExit

print("\nOpening Upstox login page...")
webbrowser.open(auth_url)

print("\nAfter login, URL will look like:")
print("http://localhost/?code=XXXXXX")

code = input("\nPaste ONLY the code here: ").strip()

token_url = "https://api.upstox.com/v2/login/authorization/token"

payload = {
    "code": code,
    "client_id": API_KEY,
    "client_secret": API_SECRET,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
}

headers = {
    "accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
}

response = requests.post(token_url, data=payload, headers=headers, timeout=15)

print("\nSTATUS CODE:", response.status_code)
print("RAW RESPONSE: suppressed to avoid printing tokens")

try:
    data = response.json()
except Exception:
    print("\n❌ Upstox did not return JSON.")
    print("Most common reasons: wrong API key/secret, wrong redirect URL, or expired/used code.")
    raise SystemExit

access_token = data.get("access_token")

if access_token:
    print("\n✅ COPY THIS INTO .env:\n")
    print(f"UPSTOX_ACCESS_TOKEN={mask_secret(access_token)}")
    print("Full token received. Store it securely in .env; it is intentionally not printed.")
else:
    print("\n❌ Access token not found.")
