"""Serviço de leitura de e-mails: conexão Gmail do usuário → metadados.

Orquestra o que o cliente REST não pode saber: de quem é a conexão, quando
renovar o token, o que persistir após o refresh e como falhar de forma
acionável (nunca silenciosamente).

Estratégia de refresh (decisão da Etapa 4):
- PROATIVO: se `token_expires_at` está a <5min de expirar (ou NULL), renova
  antes de chamar a API — evita um roundtrip condenado a 401.
- REATIVO: se vier 401 mesmo com token "fresco" (clock skew, revogação
  externa), força refresh + 1 único retry.
- invalid_grant no refresh → conexão marcada `status='error'` no banco +
  exceção clara → API responde 409 "reconecte o Gmail".
"""
import logging
from datetime import datetime, timedelta, timezone

from app.core.db import get_supabase
from app.core.token_crypto import decrypt_token, encrypt_token
from app.integrations.gmail_client import (
    GmailClient,
    GmailUnauthorizedError,
    InvalidGrantError,
    refresh_access_token,
)
from app.models.gmail import EmailMetadata, MessagePage

logger = logging.getLogger(__name__)

# Margem de segurança do refresh proativo: cobre clock skew e a duração da
# própria chamada.
_REFRESH_MARGIN = timedelta(minutes=5)

# Select explícito (nunca "*"): o fetcher precisa dos tokens cifrados, mas
# a listagem pública usa outra lista de colunas, sem eles.
_CONNECTION_COLUMNS = (
    "id,user_id,email_address,status,scope,"
    "access_token_encrypted,refresh_token_encrypted,token_expires_at"
)


class ConnectionNotFoundError(Exception):
    """Conexão inexistente OU pertence a outro usuário — a resposta é
    idêntica nos dois casos de propósito (não revelar que o id existe)."""


class ConnectionNotUsableError(Exception):
    """Conexão existe mas não está 'active' (revoked/error)."""


class GmailReconnectRequiredError(Exception):
    """O Google recusou o refresh token (expirado/revogado). A conexão foi
    marcada como 'error'; o usuário precisa refazer o fluxo /gmail/connect."""


def list_connections(user_id: str) -> list[dict]:
    """Conexões do usuário para exibição — o select já exclui as colunas de
    token, então nem em memória elas circulam aqui."""
    supabase = get_supabase()
    result = (
        supabase.table("gmail_connections")
        .select("id,email_address,scope,status,connected_at,token_expires_at")
        .eq("user_id", user_id)
        .order("connected_at", desc=True)
        .execute()
    )
    return result.data


def _load_connection(user_id: str, connection_id: str) -> dict:
    supabase = get_supabase()
    result = (
        supabase.table("gmail_connections")
        .select(_CONNECTION_COLUMNS)
        .eq("id", connection_id)
        # A service key bypassa RLS → o escopo por usuário tem que ser
        # explícito em TODA query (ver comentário em core/db.py).
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise ConnectionNotFoundError(connection_id)
    return result.data


def _persist_refreshed_token(
    connection_id: str, user_id: str, access_token: str, expires_at: datetime
) -> None:
    supabase = get_supabase()
    supabase.table("gmail_connections").update({
        "access_token_encrypted": encrypt_token(access_token),
        "token_expires_at": expires_at.isoformat(),
    }).eq("id", connection_id).eq("user_id", user_id).execute()


def _mark_connection_error(connection_id: str, user_id: str) -> None:
    supabase = get_supabase()
    supabase.table("gmail_connections").update(
        {"status": "error"}
    ).eq("id", connection_id).eq("user_id", user_id).execute()


async def _refresh_and_persist(connection: dict) -> GmailClient:
    """Renova o access token com o refresh token e persiste o resultado."""
    refresh_token = decrypt_token(connection["refresh_token_encrypted"])
    try:
        access_token, expires_at = await refresh_access_token(refresh_token)
    except InvalidGrantError:
        # Nunca falhar silenciosamente: o estado fica visível no banco
        # (status='error') e o usuário recebe um erro acionável.
        _mark_connection_error(connection["id"], connection["user_id"])
        raise GmailReconnectRequiredError(connection["id"]) from None
    _persist_refreshed_token(
        connection["id"], connection["user_id"], access_token, expires_at
    )
    logger.info("access token renovado para connection_id=%s", connection["id"])
    return GmailClient(access_token)


def _token_is_fresh(connection: dict) -> bool:
    expires_at = connection.get("token_expires_at")
    if not expires_at:
        return False  # NULL = conexão antiga ou expiração desconhecida → renova
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        # PostgREST devolve timestamptz com offset, mas se algum dia vier
        # naive, assumir UTC em vez de estourar TypeError na comparação.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc) + _REFRESH_MARGIN


async def fetch_connection_emails(
    user_id: str,
    connection_id: str,
    query: str,
    max_results: int = 10,
) -> MessagePage:
    """Lista metadados de e-mails de UMA conexão do usuário.

    Fluxo: carrega conexão (escopada) → exige status 'active' → garante
    token válido → messages.list → messages.get(metadata) por item.

    Nota de escala: é 1 chamada de list + N de metadata (N ≤ max_results ≤
    50). O Gmail tem `batchGet`, mas para volume pessoal o N+1 é simples e
    suficiente — revisitar se o cron (Etapa 14) processar centenas por run.
    """
    connection = _load_connection(user_id, connection_id)
    if connection["status"] != "active":
        raise ConnectionNotUsableError(connection["status"])

    if _token_is_fresh(connection):
        client = GmailClient(decrypt_token(connection["access_token_encrypted"]))
    else:
        client = await _refresh_and_persist(connection)

    try:
        page = await client.list_messages(query, max_results=max_results)
    except GmailUnauthorizedError:
        # Fallback reativo: token "fresco" segundo nosso cálculo, mas o
        # Google discordou. 1 refresh + 1 retry; se falhar de novo, propaga.
        logger.info(
            "401 apesar de token fresco (connection_id=%s) — refresh reativo",
            connection_id,
        )
        client = await _refresh_and_persist(connection)
        page = await client.list_messages(query, max_results=max_results)

    messages = [
        EmailMetadata.from_api_response(await client.get_message_metadata(item["id"]))
        for item in page.get("messages", [])
    ]
    return MessagePage(messages=messages, next_page_token=page.get("nextPageToken"))
