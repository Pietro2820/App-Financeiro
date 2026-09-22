"""Configuração do ambiente de testes.

Define variáveis de ambiente FAKES (porém válidas no formato) ANTES de
qualquer teste importar módulos de `app`. Isso é necessário porque
`get_settings()` usa `lru_cache` — se o primeiro teste disparar a leitura
sem env definida, o cache guarda o erro (ValidationError) para o resto da
sessão.

Nenhum valor aqui é segredo real: são fixtures de teste. O conftest vive
em tests/ e nunca é usado em produção.
"""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("SUPABASE_URL", "https://fake-project.supabase.co")
os.environ.setdefault("SUPABASE_SECRET_KEY", "fake-service-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "fake-client-id.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "fake-client-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/gmail/callback")
# Chave Fernet válida no formato (gerada uma vez, fixa, só para testes)
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "hW83TOuRjsgZois7XFixIi3ChjfVHGlZ0zjbvpL8Yi8=")
os.environ.setdefault("OAUTH_STATE_SECRET", "fake-state-secret-only-for-tests")

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def anyio_backend():
    """Testes async rodam sobre asyncio (plugin anyio já vem com o FastAPI)."""
    return "asyncio"


@pytest.fixture
def gmail_api_fixture():
    """Carrega fixtures JSON com formatos REAIS de resposta da Gmail API
    (anonimizadas): tests/fixtures/gmail_api/<nome>.json"""

    def _load(name: str) -> dict:
        path = _FIXTURES_DIR / "gmail_api" / name
        return json.loads(path.read_text(encoding="utf-8"))

    return _load
