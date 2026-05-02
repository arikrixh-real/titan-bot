import requests
from pathlib import Path

API_KEY = "6428e9f5-47bc-4b4d-9559-9bf1259a2ee6"
API_SECRET = "gxojuxs0ss"
AUTH_CODE = "x2i9-1"

REDIRECT_URI = "http://localhost"
API_KEYS_FILE = Path("config/api_keys.py")


def save_token_to_api_keys(token):
    content = API_KEYS_FILE.read_text()

    lines = content.splitlines()
    new_lines = []
    token_line_written = False

    for line in lines:
        if line.startswith("UPSTOX_ACCESS_TOKEN"):
            new_lines.append(f'UPSTOX_ACCESS_TOKEN = "{token}"')
            token_line_written = True
        else:
            new_lines.append(line)

    if not token_line_written:
        new_lines.append(f'UPSTOX_ACCESS_TOKEN = "{token}"')

    API_KEYS_FILE.write_text("\n".join(new_lines) + "\n")


url = "https://api.upstox.com/v2/login/authorization/token"

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

response = requests.post(url, headers=headers, data=data)

print("Status:", response.status_code)
result = response.json()
print("Response:", result)

if response.status_code == 200 and "access_token" in result:
    save_token_to_api_keys(result["access_token"])
    print("✅ Upstox access token saved automatically to config/api_keys.py")
else:
    print("❌ Token not saved. Check API key, secret, auth code, or plan confirmation.")