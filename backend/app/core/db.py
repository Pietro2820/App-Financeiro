"""Cliente Supabase compartilhado pelo backend.

Usa a service_role key (bypassa RLS) porque o backend roda em contexto de
automação/servidor confiável — nunca expor essa key ao frontend. Chamadas
feitas em nome de um usuário específico devem filtrar por user_id
explicitamente já que RLS não se aplica aqui.
"""
from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_secret_key)
