from dotenv import load_dotenv
load_dotenv()

from data.live_price import get_live_price

symbols = [
    "RELIANCE",
    "TATAMOTORS",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ADANIENT",
    "TATASTEEL",
    "GRASIM",
    "NTPC"
]

print("🔍 TESTING UPSTOX LIVE PRICE - NO CACHE")
print("=" * 50)

success = 0
failed = 0

for symbol in symbols:
    price = get_live_price(symbol, use_cache=False, debug=True)

    if price is None:
        print(f"❌ {symbol}: NO LIVE PRICE")
        failed += 1
    else:
        print(f"✅ {symbol}: {price}")
        success += 1

print("=" * 50)
print(f"✅ Success: {success}")
print(f"❌ Failed: {failed}")