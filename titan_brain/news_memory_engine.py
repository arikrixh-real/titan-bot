import requests
import xml.etree.ElementTree as ET
from datetime import datetime

from data.loader import load_cached_stock_data
from titan_brain.supabase_client import supabase


MAX_NEWS_PER_CATEGORY = 5
MAX_TOP_STOCKS = 5


NEWS_CATEGORIES = {
    "INDIAN_MARKET": [
        "Nifty Sensex stock market news today",
        "Indian stock market news today",
        "Nifty 50 Bank Nifty market outlook today",
    ],

    "GLOBAL_MARKET": [
        "US stock market news today impact on India",
        "Asian markets news today impact on India",
        "Federal Reserve interest rate news today",
        "global market cues for Indian stock market today",
    ],

    "COMMODITY_CURRENCY": [
        "crude oil price news impact on Indian stocks",
        "Brent crude oil news today",
        "USD INR rupee news today",
        "gold price news today India",
    ],

    "POLICY_RBI_SEBI": [
        "RBI news today banking stocks India",
        "SEBI news today stock market India",
        "India government policy stock market impact",
    ],

    "SECTOR": [
        "banking sector stocks news India today",
        "IT sector stocks news India today",
        "auto sector stocks news India today",
        "pharma sector stocks news India today",
        "metal sector stocks news India today",
        "energy sector stocks news India today",
        "FMCG sector stocks news India today",
        "real estate sector stocks news India today",
    ],
}


def detect_sentiment(text):
    text = text.lower()

    positive_words = [
        "gain", "gains", "rally", "surge", "jumps", "profit",
        "beats", "growth", "order win", "upgrade", "bullish",
        "strong", "positive", "record high", "expansion"
    ]

    negative_words = [
        "fall", "falls", "drop", "slips", "loss", "misses",
        "weak", "downgrade", "bearish", "fraud", "probe",
        "penalty", "negative", "selloff", "decline"
    ]

    pos = sum(1 for word in positive_words if word in text)
    neg = sum(1 for word in negative_words if word in text)

    if pos > neg:
        return "BULLISH"
    if neg > pos:
        return "BEARISH"
    return "NEUTRAL"


def detect_importance(text):
    text = text.lower()

    high_impact_words = [
        "results", "earnings", "rbi", "sebi", "fed", "inflation",
        "merger", "acquisition", "order", "fraud", "probe",
        "penalty", "rate cut", "rate hike", "guidance",
        "management", "approval", "crude", "rupee", "dollar",
        "war", "tariff", "policy"
    ]

    score = sum(1 for word in high_impact_words if word in text)

    if score >= 3:
        return 90
    if score == 2:
        return 70
    if score == 1:
        return 50
    return 30


def google_news_rss(query, max_items=5):
    url = "https://news.google.com/rss/search"

    params = {
        "q": query,
        "hl": "en-IN",
        "gl": "IN",
        "ceid": "IN:en"
    }

    try:
        response = requests.get(url, params=params, timeout=8)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        items = root.findall(".//item")

        news_items = []

        for item in items[:max_items]:
            title = item.findtext("title", default="")
            link = item.findtext("link", default="")
            source = item.findtext("source", default="Google News")
            published = item.findtext("pubDate", default="")

            if not title:
                continue

            news_items.append({
                "title": title,
                "link": link,
                "source": source,
                "published": published,
                "query": query
            })

        return news_items

    except Exception as e:
        print(f"[NEWS FETCH ERROR] {query}: {e}")
        return []


def news_exists(headline):
    try:
        result = (
            supabase
            .table("news_memory")
            .select("id")
            .eq("headline", headline)
            .limit(1)
            .execute()
        )

        return len(result.data) > 0

    except Exception as e:
        print(f"[NEWS DUPLICATE CHECK ERROR] {e}")
        return False


def store_news(symbol, headline, source, sentiment, importance, impact_type, summary, raw_data):
    if news_exists(headline):
        return False

    try:
        supabase.table("news_memory").insert({
            "symbol": symbol,
            "headline": headline,
            "source": source,
            "sentiment": sentiment,
            "importance": importance,
            "impact_type": impact_type,
            "summary": summary,
            "raw_data": raw_data
        }).execute()

        return True

    except Exception as e:
        print(f"[NEWS STORE ERROR] {e}")
        return False


def collect_category_news(category, queries, max_total=MAX_NEWS_PER_CATEGORY):
    stored_count = 0
    collected = 0

    for query in queries:
        if collected >= max_total:
            break

        news_items = google_news_rss(query, max_items=3)

        for news in news_items:
            if collected >= max_total:
                break

            headline = news["title"]
            sentiment = detect_sentiment(headline)
            importance = detect_importance(headline)

            stored = store_news(
                symbol=category,
                headline=headline,
                source=news["source"],
                sentiment=sentiment,
                importance=importance,
                impact_type=category,
                summary=headline,
                raw_data=news
            )

            collected += 1

            if stored:
                stored_count += 1

    return stored_count


def get_top_scanned_symbols(limit=MAX_TOP_STOCKS):
    """
    Gets latest high-score stocks from Supabase scan_symbols.
    If unavailable, falls back to cached stock list.
    """

    try:
        result = (
            supabase
            .table("scan_symbols")
            .select("symbol, final_score, created_at")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )

        rows = result.data or []

        if not rows:
            raise Exception("No scan_symbols found")

        unique = {}

        for row in rows:
            symbol = row.get("symbol")
            score = row.get("final_score") or 0

            if symbol not in unique:
                unique[symbol] = score

        sorted_symbols = sorted(
            unique.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [s[0] for s in sorted_symbols[:limit]]

    except Exception as e:
        print(f"[TOP STOCK FALLBACK] {e}")

        cached_data = load_cached_stock_data()
        return list(cached_data.keys())[:limit]


def collect_top_stock_news():
    stored_count = 0
    top_symbols = get_top_scanned_symbols()

    print(f"📌 Top stock news symbols: {top_symbols}")

    for symbol in top_symbols:
        query = f"{symbol} stock news India today"
        news_items = google_news_rss(query, max_items=2)

        for news in news_items:
            headline = news["title"]
            sentiment = detect_sentiment(headline)
            importance = detect_importance(headline)

            stored = store_news(
                symbol=symbol,
                headline=headline,
                source=news["source"],
                sentiment=sentiment,
                importance=importance,
                impact_type="STOCK",
                summary=headline,
                raw_data=news
            )

            if stored:
                stored_count += 1
                break

    return stored_count, top_symbols


def run_news_memory_engine():
    print("🧠 TITAN Smart News Engine Started")

    category_counts = {}

    for category, queries in NEWS_CATEGORIES.items():
        count = collect_category_news(
            category=category,
            queries=queries,
            max_total=MAX_NEWS_PER_CATEGORY
        )
        category_counts[category] = count
        print(f"📰 {category} news stored: {count}")

    stock_count, top_symbols = collect_top_stock_news()

    total = sum(category_counts.values()) + stock_count

    print(f"📈 Top stock news stored: {stock_count}")
    print(f"🔁 Top stocks checked: {top_symbols}")
    print(f"✅ Total news stored: {total}")

    return {
        "timestamp": datetime.now().isoformat(),
        "category_counts": category_counts,
        "top_stock_news_stored": stock_count,
        "top_symbols": top_symbols,
        "total_news_stored": total
    }