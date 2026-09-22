"""Funções de baixo nível do fluxo OAuth do Gmail (sem tocar no banco)."""
import httpx
from urllib.parse import urlencode
from app.core.config import get_settings

AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def build_authorization_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_BASE_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        response = await client.post(TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
    response.raise_for_status()
    return response.json()


async def get_user_email(access_token: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    response.raise_for_status()
    return response.json()["email"]


async def revoke_token(token: str) -> None:
    async with httpx.AsyncClient() as client:
        await client.post(REVOKE_URL, data={"token": token})