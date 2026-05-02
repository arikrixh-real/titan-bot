import requests
from config.api_keys import ALPHA_VANTAGE_API_KEY

symbol = "ADANIENT.BSE"

url = "https://www.alphavantage.co/query"

params = {
    "function": "GLOBAL_QUOTE",
    "symbol": symbol,
    "apikey": ALPHA_VANTAGE_API_KEY
}

response = requests.get(url, params=params, timeout=10)
data = response.json()

print(data)