import os

from supabase import create_client


def get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        print("[Supabase] Supabase config missing or disabled. DB actions skipped.")
        return None

    try:
        return create_client(url, key)
    except Exception:
        print("[Supabase] Supabase config missing or disabled. DB actions skipped.")
        return None


supabase = get_supabase_client()
