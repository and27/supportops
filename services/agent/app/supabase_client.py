import os

from supabase import Client, create_client

_supabase: Client | None = None


def get_supabase_client() -> Client:
    global _supabase
    if _supabase is not None:
        return _supabase

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set")

    _supabase = create_client(supabase_url, supabase_key)
    return _supabase
