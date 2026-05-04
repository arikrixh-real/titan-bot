import requests
import webbrowser

API_KEY = "4f5acbf7-73b5-4437-a692-8e5b8fde9d8a"
API_SECRET = "73unm2ly3u"

REDIRECT_URI = "http://localhost"

auth_url = (
    "https://api.upstox.com/v2/login/authorization/dialog"
    f"?response_type=code"
    f"&client_id={API_KEY}"
    f"&redirect_uri={REDIRECT_URI}"
)

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

response = requests.post(token_url, data=payload, headers=headers)

print("\nSTATUS CODE:", response.status_code)
print("RAW RESPONSE:")
print(response.text)

try:
    data = response.json()
except Exception:
    print("\n❌ Upstox did not return JSON.")
    print("Most common reasons: wrong API key/secret, wrong redirect URL, or expired/used code.")
    raise SystemExit

access_token = data.get("access_token")

if access_token:
    print("\n✅ COPY THIS INTO .env:\n")
    print(f"UPSTOX_ACCESS_TOKEN={access_token}")
else:
    print("\n❌ Access token not found.")