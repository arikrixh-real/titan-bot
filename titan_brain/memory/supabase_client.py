import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()


def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        raise Exception("Missing Supabase credentials")

    return create_client(url, key)