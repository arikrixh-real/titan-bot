import feedparser
import re
import json
from pathlib import Path
from datetime import datetime


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
}


NEWS_FEEDS = [
    "https://www.moneycontrol.com/rss/business.xml",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
]

NEWS_MEMORY_FILE = Path("titan_brain/memory/news_batch_state.json")


def clean_text(text):
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9& ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return f" {text.strip()} "


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


def fetch_news():
    all_news = []

    for feed_url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)

            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                link = entry.get("link", "")

                detected_symbols = detect_stock_from_news(title, summary)

                news_item = {
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "detected_symbols": detected_symbols,
                    "source": feed_url,
                    "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }

                all_news.append(news_item)

        except Exception as e:
            print(f"Error fetching news from {feed_url}: {e}")

    return all_news


def get_stock_news():
    news = fetch_news()
    return [item for item in news if item["detected_symbols"]]


def run_news_engine():
    """
    Main function called by setup_engine.py.
    Fetches stock-related news and stores latest batch safely.
    """
    try:
        stock_news = get_stock_news()

        NEWS_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        memory_data = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "news_count": len(stock_news),
            "news": stock_news[:50],
        }

        with open(NEWS_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, indent=2, ensure_ascii=False)

        print(f"📰 News Engine: collected {len(stock_news)} stock-related news items")
        print(f"🧠 News memory updated: {NEWS_MEMORY_FILE}")

        return stock_news

    except Exception as e:
        print(f"⚠️ News Engine Error: {e}")
        return []


if __name__ == "__main__":
    print("Testing TITAN News Engine...")

    print("Test 1:", detect_stock_from_news("Reliance shares rise after strong earnings"))
    print("Test 2:", detect_stock_from_news("TCS wins major AI deal"))
    print("Test 3:", detect_stock_from_news("Market opens flat today"))
    print("Test 4:", detect_stock_from_news("LTIMindtree Q4 preview"))
    print("Test 5:", detect_stock_from_news("Air India enters codeshare pact with Japan airline"))

    print("\nFetching live stock-related news...")
    stock_news = run_news_engine()

    for news in stock_news[:10]:
        print("\n-------------------------")
        print("Title:", news["title"])
        print("Symbols:", news["detected_symbols"])
        print("Link:", news["link"])