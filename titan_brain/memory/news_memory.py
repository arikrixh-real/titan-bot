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
            print("⚠️ Missing title")
            return False

        supabase = get_supabase()

        data = {
            "symbol": symbol,
            "title": title,
            "url": url,
            "source": source,
            "summary": summary,
            "sentiment": sentiment,
            "impact_score": impact_score,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        supabase.table("news_memory").upsert(
            data,
            on_conflict="url"
        ).execute()

        print(f"✅ News saved: {title[:50]}")
        return True

    except Exception as e:
        print(f"❌ News save failed: {e}")
        return False