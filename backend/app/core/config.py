"""Configuração central da aplicação, lida de variáveis de ambiente.

Nunca colocar segredos com valor default aqui — só nomes de variáveis.
Em produção (GitHub Actions / deploy) os valores vêm de secrets; em dev,
de um arquivo `.env` local (nunca commitado — ver .gitignore).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str
    supabase_secret_key: str  # usado só no backend, NUNCA no frontend

    # Gmail OAuth (Etapa 3)
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    token_encryption_key: str   # criptografia dos tokens salvos no banco
    oauth_state_secret: str     # assinatura do 'state' do fluxo OAuth

    # App
    environment: str = "development"  # development | production
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Cacheado: lê o .env uma vez só por processo."""
    return Settings()