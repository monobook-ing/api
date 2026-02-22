from functools import lru_cache
from typing import Generator

from supabase import Client, create_client

from app.core.config import get_settings

_supabase_client: Client | None = None


@lru_cache
def get_supabase_client() -> Client:
    """Get or create a singleton Supabase client instance."""
    global _supabase_client
    
    if _supabase_client is None:
        settings = get_settings()
        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_service_key
        )
    
    return _supabase_client


def get_supabase() -> Generator[Client, None, None]:
    """Dependency that yields a Supabase client instance."""
    yield get_supabase_client()