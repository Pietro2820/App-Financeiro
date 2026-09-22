"""Entrypoint da API. Nesta etapa só existe para validar que a estrutura do
projeto e a conexão com Supabase funcionam — endpoints de negócio real
entram na Etapa 11.
"""
from typing import Annotated

from fastapi import Depends, FastAPI

from app.api import gmail
from app.core.config import get_settings
from app.core.db import get_supabase
from app.core.security import get_current_user_id

app = FastAPI(title="App Financeiro API", version="0.1.0")

app.include_router(gmail.router)


@app.get("/health")
def health() -> dict:
    """Confirma que a API sobe e que as settings carregam corretamente."""
    settings = get_settings()
    return {"status": "ok", "environment": settings.environment}


@app.get("/health/db")
def health_db() -> dict:
    """Confirma que a conexão com o Supabase funciona, consultando o
    catálogo de instituições financeiras (deve ter as do seed.sql)."""
    supabase = get_supabase()
    result = supabase.table("financial_institutions").select("id, name, slug").execute()
    return {"status": "ok", "institutions_count": len(result.data), "institutions": result.data}


@app.get("/me")
def me(user_id: Annotated[str, Depends(get_current_user_id)]) -> dict:
    """Endpoint protegido: só responde com um token válido no header
    Authorization. Usado pra validar o fluxo de autenticação ponta a
    ponta antes de existir qualquer tela de login."""
    return {"user_id": user_id}
