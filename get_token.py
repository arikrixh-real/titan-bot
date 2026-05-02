import webbrowser

# 🔑 PUT YOUR TITAN2 API KEY HERE
API_KEY = "6428e9f5-47bc-4b4d-9559-9bf1259a2ee6"

REDIRECT_URI = "http://localhost"

auth_url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={API_KEY}&redirect_uri={REDIRECT_URI}"

print("Opening Upstox login...")
webbrowser.open(auth_url)