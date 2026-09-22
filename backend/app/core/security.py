"""Validação do token emitido pelo Supabase Auth via JWKS (chaves
assimétricas) — o método atual recomendado pelo Supabase, sem precisar
guardar nenhum segredo compartilhado no backend.

Não importa se o usuário logou com email/senha ou (futuramente) Google —
o Supabase emite o mesmo formato de JWT pra qualquer provedor.
"""
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import get_settings

_bearer_scheme = HTTPBearer(auto_error=False)


class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


@lru_cache
def get_jwks_client() -> PyJWKClient:
    """Cliente que busca e cacheia as chaves públicas do Supabase."""
    settings = get_settings()
    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_url, cache_keys=True)


def decode_supabase_jwt(token: str) -> dict:
    """Decodifica e valida um JWT do Supabase usando a chave pública
    correspondente (buscada via JWKS). Levanta AuthError se inválido,
    expirado ou se não for possível validar. Separada da dependency pra
    ser testável sem precisar de uma request HTTP de verdade."""
    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expirado")
    except jwt.InvalidTokenError:
        raise AuthError("Token inválido")
    except AuthError:
        raise
    except Exception as exc:
        # falha ao buscar a JWKS (rede, URL errada, projeto errado, etc)
        raise AuthError(f"Não foi possível validar o token: {exc}")
    return payload


def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """Dependency para proteger endpoints. Uso:

        @app.get("/algo")
        def algo(user_id: Annotated[str, Depends(get_current_user_id)]):
            ...
    """
    if credentials is None:
        raise AuthError("Header Authorization ausente")
    payload = decode_supabase_jwt(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Token sem claim 'sub'")
    return user_id
