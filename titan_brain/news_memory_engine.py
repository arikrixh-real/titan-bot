from datetime import datetime, timezone
from titan_brain.memory.supabase_client import get_supabase


def save_news_memory(
    symbol=None,
    title=None,
    url=None,
    source=None,
    summary=None,
    sentiment="neutral",
    impact_score=0,
):
    try:
        if not title and summary:
            title = summary[:120]

        if not title:
            print("⚠️ News skipped: missing title")
            return False

        supabase = get_supabase()

        data = {
            "symbol": symbol,
            "title": title,
            "url": url,
            "source": source,
            "summary": summary,
            "sentiment": sentiment,
            "impact_score": impact_score or 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        supabase.table("news_memory").upsert(
            data,
            on_conflict="url"
        ).execute()

        print(f"✅ News memory saved: {symbol} | {title[:50]}")
        return True

    except Exception as e:
        print(f"❌ News memory save failed: {e}")
        return False


def run_news_memory_engine():
    """
    Backward-compatible entrypoint for main.py.

    The full news collector lives in intelligence.news_engine. This wrapper
    keeps the legacy import stable without forcing a network call.
    """
    print("[NewsMemory] Legacy entrypoint available. No direct news item supplied.")
    return {"status": "NO_DIRECT_NEWS_ITEM", "saved": False}
