"""
TITAN Smart News Engine - Supabase + Sector Sync
------------------------------------------------
What this does:
1. Collects stock-related news.
2. Detects affected NSE stock symbols.
3. Detects affected sectors.
4. Stores latest batch locally in titan_brain/memory/news_batch_state.json.
5. Stores news into Supabase news_memory table.
6. Avoids duplicate news using news_hash when Supabase supports it.
7. Does not crash if Supabase table has fewer columns.
8. Keeps setup_engine.py safe.

Recommended Supabase news_memory columns:
- id uuid default gen_random_uuid()
- created_at timestamptz default now()
- news_hash text
- title text
- summary text
- link text
- source text
- detected_symbols jsonb
- sectors jsonb
- fetched_at timestamptz
"""

import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import feedparser

try:
    from supabase import create_client
except Exception:
    create_client = None


IST = ZoneInfo("Asia/Kolkata")


# =========================================================
# STOCK KEYWORDS
# =========================================================

STOCK_KEYWORDS = {
    "RELIANCE": ["reliance", "ril", "jio"],
    "TCS": ["tcs", "tata consultancy"],
    "INFY": ["infosys", "infy"],
    "HDFCBANK": ["hdfc bank", "hdfcbank"],
    "ICICIBANK": ["icici bank", "icicibank"],
    "SBIN": ["sbi", "state bank of india"],
    "ITC": ["itc"],
    "LT": ["larsen", "larsen & toubro", "l&t", " lt "],
    "AXISBANK": ["axis bank", "axisbank"],
    "KOTAKBANK": ["kotak", "kotak bank"],
    "BHARTIARTL": ["airtel", "bharti airtel"],
    "ADANIENT": ["adani enterprises", "adanient"],
    "ADANIPORTS": ["adani ports", "adaniports"],
    "TATAMOTORS": ["tata motors", "tatamotors"],
    "MARUTI": ["maruti", "maruti suzuki"],
    "BAJFINANCE": ["bajaj finance", "bajfinance"],
    "HINDUNILVR": ["hindustan unilever", "hul", "hindunilvr"],
    "SUNPHARMA": ["sun pharma", "sunpharma"],
    "TATASTEEL": ["tata steel", "tatasteel"],
    "WIPRO": ["wipro"],
    "TATACONSUM": ["tata consumer", "tataconsum"],
    "LTIM": ["ltimindtree", "lti mindtree", "ltim"],
    "ONGC": ["ongc", "oil and natural gas corporation"],
    "POWERGRID": ["power grid", "powergrid"],
    "NTPC": ["ntpc"],
    "COALINDIA": ["coal india", "coalindia"],
    "HCLTECH": ["hcl tech", "hcltech", "hcl technologies"],
    "TECHM": ["tech mahindra", "techm"],
    "ULTRACEMCO": ["ultratech cement", "ultracemco"],
    "GRASIM": ["grasim"],
    "JSWSTEEL": ["jsw steel", "jswsteel"],
    "HINDALCO": ["hindalco"],
    "M&M": ["mahindra", "mahindra and mahindra", "m&m"],
    "BAJAJ-AUTO": ["bajaj auto"],
    "EICHERMOT": ["eicher", "eicher motors"],
    "HEROMOTOCO": ["hero motocorp", "hero moto"],
    "DRREDDY": ["dr reddy", "dr reddy's"],
    "CIPLA": ["cipla"],
    "DIVISLAB": ["divis lab", "divi's laboratories"],
    "NESTLEIND": ["nestle india", "nestleind"],
    "BRITANNIA": ["britannia"],
    "ASIANPAINT": ["asian paints", "asianpaint"],
    "TITAN": ["titan company", "titan"],
    "BAJAJFINSV": ["bajaj finserv", "bajajfinsv"],
    "HDFCLIFE": ["hdfc life", "hdfclife"],
    "SBILIFE": ["sbi life", "sbilife"],
}


# =========================================================
# SECTOR MAPPING
# =========================================================

STOCK_SECTORS = {
    "RELIANCE": "Energy / Telecom / Retail",
    "ONGC": "Oil & Gas",
    "COALINDIA": "Energy / Coal",
    "NTPC": "Power",
    "POWERGRID": "Power",
    "TCS": "IT",
    "INFY": "IT",
    "WIPRO": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "LTIM": "IT",
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "SBIN": "Banking",
    "AXISBANK": "Banking",
    "KOTAKBANK": "Banking",
    "BAJFINANCE": "NBFC",
    "BAJAJFINSV": "Financial Services",
    "HDFCLIFE": "Insurance",
    "SBILIFE": "Insurance",
    "BHARTIARTL": "Telecom",
    "ADANIENT": "Conglomerate / Infrastructure",
    "ADANIPORTS": "Ports / Logistics",
    "LT": "Capital Goods / Infrastructure",
    "TATAMOTORS": "Auto",
    "MARUTI": "Auto",
    "M&M": "Auto",
    "BAJAJ-AUTO": "Auto",
    "EICHERMOT": "Auto",
    "HEROMOTOCO": "Auto",
    "HINDUNILVR": "FMCG",
    "ITC": "FMCG",
    "TATACONSUM": "FMCG",
    "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG",
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
    "HINDALCO": "Metals",
    "ULTRACEMCO": "Cement",
    "GRASIM": "Cement / Chemicals",
    "ASIANPAINT": "Paints / Consumer",
    "TITAN": "Consumer / Jewellery",
}


SECTOR_KEYWORDS = {
    "Banking": ["bank", "banks", "rbi", "repo rate", "credit growth", "loan", "deposit", "npa"],
    "IT": ["it sector", "software", "ai deal", "technology", "nasdaq", "dollar revenue", "digital transformation"],
    "Auto": ["auto", "vehicle", "ev", "car sales", "two wheeler", "passenger vehicle"],
    "Pharma": ["pharma", "drug", "usfda", "medicine", "healthcare", "clinical"],
    "FMCG": ["fmcg", "consumer goods", "rural demand", "staples", "inflation"],
    "Oil & Gas": ["oil", "crude", "gas", "opec", "brent"],
    "Power": ["power demand", "electricity", "renewable", "grid"],
    "Metals": ["steel", "metal", "aluminium", "iron ore", "copper"],
    "Cement": ["cement", "infra demand", "construction"],
    "Telecom": ["telecom", "5g", "spectrum", "subscriber", "tariff"],
    "Infrastructure": ["infrastructure", "capex", "road", "railway", "ports", "logistics"],
    "Global Macro": ["fed", "us fed", "inflation", "bond yield", "dollar index", "geopolitical", "war"],
    "Market Index": ["nifty", "sensex", "nse", "bse", "market opens", "market closes"],
}


# =========================================================
# NEWS FEEDS
# =========================================================

NEWS_FEEDS = [
    "https://www.moneycontrol.com/rss/business.xml",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
    "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms",
]

NEWS_MEMORY_FILE = Path("titan_brain/memory/news_batch_state.json")


# =========================================================
# TEXT HELPERS
# =========================================================

def clean_text(text):
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9& ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return f" {text.strip()} "


def make_news_hash(title, link):
    raw = f"{str(title).strip().lower()}|{str(link).strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# =========================================================
# DETECTION
# =========================================================

def detect_stock_from_news(title, summary=""):
    text = clean_text(f"{title} {summary}")
    detected_symbols = []

    for symbol, keywords in STOCK_KEYWORDS.items():
        for keyword in keywords:
            keyword_clean = clean_text(keyword)
            if keyword_clean in text:
                detected_symbols.append(symbol)
                break

    return detected_symbols


def detect_sector_from_news(title, summary="", detected_symbols=None):
    text = clean_text(f"{title} {summary}")
    sectors = set()

    detected_symbols = detected_symbols or []

    for symbol in detected_symbols:
        sector = STOCK_SECTORS.get(symbol)
        if sector:
            sectors.add(sector)

    for sector, keywords in SECTOR_KEYWORDS.items():
        for keyword in keywords:
            keyword_clean = clean_text(keyword)
            if keyword_clean in text:
                sectors.add(sector)
                break

    return sorted(sectors)


# =========================================================
# SUPABASE HELPERS
# =========================================================

def get_supabase():
    try:
        if create_client is None:
            return None

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if not url or not key:
            return None

        return create_client(url, key)

    except Exception:
        return None


def supabase_news_exists(client, news_hash, link):
    """
    Duplicate check.
    Uses news_hash first. If schema does not support it, uses link.
    If neither works, returns False and insert retry still protects from crashes.
    """
    if client is None:
        return False

    try:
        result = (
            client.table("news_memory")
            .select("id")
            .eq("news_hash", news_hash)
            .limit(1)
            .execute()
        )
        if result.data:
            return True
    except Exception:
        pass

    try:
        result = (
            client.table("news_memory")
            .select("id")
            .eq("link", link)
            .limit(1)
            .execute()
        )
        if result.data:
            return True
    except Exception:
        pass

    return False


def remove_missing_column_from_payload(error_text, payload):
    """
    Supabase/PostgREST error format:
    Could not find the 'column_name' column of 'news_memory'
    This removes the missing column and retries safely.
    """
    match = re.search(r"Could not find the '([^']+)' column", str(error_text))
    if not match:
        return False

    missing_col = match.group(1)

    if missing_col in payload:
        payload.pop(missing_col, None)
        return True

    return False


def insert_news_to_supabase(news_items):
    client = get_supabase()

    if client is None:
        print("⚠️ News Supabase not connected")
        return 0

    inserted_count = 0
    duplicate_count = 0
    failed_count = 0

    for item in news_items:
        title = item.get("title", "")
        link = item.get("link", "")
        news_hash = item.get("news_hash") or make_news_hash(title, link)

        if supabase_news_exists(client, news_hash, link):
            duplicate_count += 1
            continue

        payload = {
            "created_at": datetime.now(IST).isoformat(),
            "news_hash": news_hash,
            "title": title,
            "summary": item.get("summary", ""),
            "link": link,
            "source": item.get("source", ""),
            "detected_symbols": item.get("detected_symbols", []),
            "sectors": item.get("sectors", []),
            "fetched_at": item.get("fetched_at_iso", datetime.now(IST).isoformat()),
        }

        # Retry by automatically removing columns your table does not have.
        success = False
        payload_to_try = dict(payload)

        for _ in range(12):
            try:
                client.table("news_memory").insert(payload_to_try).execute()
                inserted_count += 1
                success = True
                break

            except Exception as e:
                removed = remove_missing_column_from_payload(str(e), payload_to_try)

                if not removed:
                    # Final fallback: created_at only.
                    try:
                        client.table("news_memory").insert({
                            "created_at": datetime.now(IST).isoformat()
                        }).execute()
                        inserted_count += 1
                        success = True
                        break
                    except Exception:
                        break

        if not success:
            failed_count += 1

    print(f"☁️ News Supabase inserted: {inserted_count}")
    print(f"♻️ News duplicates skipped: {duplicate_count}")

    if failed_count:
        print(f"⚠️ News Supabase failed: {failed_count}")

    return inserted_count


# =========================================================
# NEWS FETCHING
# =========================================================

def fetch_news():
    all_news = []

    for feed_url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)

            for entry in feed.entries[:15]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                link = entry.get("link", "")

                if not title and not link:
                    continue

                detected_symbols = detect_stock_from_news(title, summary)
                sectors = detect_sector_from_news(title, summary, detected_symbols)

                # Keep stock, sector, market, macro news
                if not detected_symbols and not sectors:
                    continue

                news_hash = make_news_hash(title, link)
                fetched_at_iso = datetime.now(IST).isoformat()

                news_item = {
                    "news_hash": news_hash,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "detected_symbols": detected_symbols,
                    "sectors": sectors,
                    "source": feed_url,
                    "fetched_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                    "fetched_at_iso": fetched_at_iso,
                }

                all_news.append(news_item)

        except Exception as e:
            print(f"⚠️ Error fetching news from {feed_url}: {e}")

    return all_news


def get_stock_news():
    return fetch_news()


def run_news_engine():
    """
    Main function called by setup_engine.py.
    Fetches stock/sector/market news, stores local backup and Supabase memory.
    """
    try:
        news_items = get_stock_news()

        NEWS_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        memory_data = {
            "updated_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "news_count": len(news_items),
            "news": news_items[:100],
        }

        with open(NEWS_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, indent=2, ensure_ascii=False)

        inserted_count = insert_news_to_supabase(news_items)

        print(f"📰 News Engine: collected {len(news_items)} stock/sector news items")
        print(f"🧠 News memory updated: {NEWS_MEMORY_FILE}")
        print(f"☁️ News synced to Supabase: {inserted_count}")

        return news_items

    except Exception as e:
        print(f"⚠️ News Engine Error: {e}")
        return []


if __name__ == "__main__":
    print("Testing TITAN Smart News Engine...")

    print("Test 1:", detect_stock_from_news("Reliance shares rise after strong earnings"))
    print("Test 2:", detect_stock_from_news("TCS wins major AI deal"))
    print("Test 3 sectors:", detect_sector_from_news("RBI policy boosts banking stocks"))
    print("Test 4 sectors:", detect_sector_from_news("Crude oil rises as OPEC cuts supply"))
    print("Test 5 sectors:", detect_sector_from_news("Nifty opens flat amid weak global cues"))

    print("\nFetching live stock/sector news...")
    stock_news = run_news_engine()

    for news in stock_news[:10]:
        print("\n-------------------------")
        print("Title:", news["title"])
        print("Symbols:", news["detected_symbols"])
        print("Sectors:", news["sectors"])
        print("Link:", news["link"])