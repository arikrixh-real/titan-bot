import requests
from config.api_keys import UPSTOX_ACCESS_TOKEN

url = "https://api.upstox.com/v2/market-quote/ltp"

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}"
}

# ✅ Correct instrument key for ADANIENT
params = {
    "instrument_key": "NSE_EQ|INE423A01024"
}

response = requests.get(url, headers=headers, params=params)

print(response.status_code)
print(response.json())