"""Rotas do fluxo de conexão Gmail via OAuth2 + leitura de metadados."""
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.db import get_supabase
from app.core.oauth_state import create_state, verify_state
from app.core.security import get_current_user_id
from app.core.token_crypto import decrypt_token, encrypt_token
from app.integrations import gmail_oauth
from app.models.gmail import GmailConnectionOut, MessagePage
from app.services import email_fetcher

router = APIRouter(prefix="/gmail", tags=["gmail"])


@router.get("/connect")
async def gmail_connect(user_id: str = Depends(get_current_user_id)):
    """Retorna a URL de autorização do Google. Cole no navegador pra continuar."""
    state = create_state(user_id=user_id)
    url = gmail_oauth.build_authorization_url(state)
    return {"authorization_url": url}


@router.get("/callback")
async def gmail_callback(code: str = Query(...), state: str = Query(...)):
    """Chamada pelo Google após autorização. Sem Authorization header —
    a identidade vem do 'state' assinado."""
    try:
        user_id = verify_state(state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"State inválido: {e}")

    tokens = await gmail_oauth.exchange_code_for_tokens(code)
    # O Google só retorna refresh_token na primeira autorização (ou com
    # prompt=consent). Sem ele não há como renovar o access token depois —
    # melhor falhar com mensagem clara do que KeyError/500 (nunca falhar
    # silenciosamente).
    if "refresh_token" not in tokens:
        raise HTTPException(
            status_code=502,
            detail=(
                "Google não retornou refresh_token. Revogue o acesso do app em "
                "https://myaccount.google.com/permissions e conecte novamente."
            ),
        )
    email_address = await gmail_oauth.get_user_email(tokens["access_token"])

    # O Google devolve expires_in (segundos, tipicamente 3599) — salvamos o
    # timestamp absoluto para o email_fetcher decidir o refresh proativo.
    expires_in = int(tokens.get("expires_in", 3600))
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    supabase = get_supabase()
    supabase.table("gmail_connections").upsert({
        "user_id": user_id,
        "email_address": email_address,
        "access_token_encrypted": encrypt_token(tokens["access_token"]),
        "refresh_token_encrypted": encrypt_token(tokens["refresh_token"]),
        "scope": tokens.get("scope", ""),
        "status": "active",
        "token_expires_at": token_expires_at.isoformat(),
    }, on_conflict="user_id,email_address").execute()

    return {"message": f"Gmail {email_address} conectado com sucesso."}


@router.post("/revoke/{connection_id}")
async def gmail_revoke(
    connection_id: UUID,  # UUID tipado: malformado vira 422, não 500 do PostgREST
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    # maybe_single() em vez de single(): single() LEVANTA exceção quando não
    # encontra nenhuma linha (viraria um 500); maybe_single() retorna None e
    # cai no 404 abaixo, que é o comportamento correto.
    result = supabase.table("gmail_connections") \
        .select("*") \
        .eq("id", str(connection_id)) \
        .eq("user_id", user_id) \
        .maybe_single() \
        .execute()

    connection = result.data
    if not connection:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")

    refresh_token = decrypt_token(connection["refresh_token_encrypted"])
    await gmail_oauth.revoke_token(refresh_token)

    # Timestamp ISO gerado no app (portável) e filtro por user_id no update —
    # a service key bypassa RLS, então a garantia de escopo tem que ser
    # explícita em cada query (ver comentário em core/db.py).
    supabase.table("gmail_connections").update({
        "status": "revoked",
        "revoked_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", str(connection_id)).eq("user_id", user_id).execute()

    return {"message": "Conexão revogada com sucesso."}


@router.get("/connections", response_model=list[GmailConnectionOut])
async def gmail_list_connections(
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Lista as conexões Gmail do usuário autenticado.

    O response_model (GmailConnectionOut) não tem campos de token — mesmo
    que o service devolvesse algo sensível por engano, o FastAPI filtra.
    """
    return email_fetcher.list_connections(user_id)


@router.get("/connections/{connection_id}/messages", response_model=MessagePage)
async def gmail_list_messages(
    connection_id: UUID,  # UUID tipado: malformado vira 422, não 500 do PostgREST
    user_id: Annotated[str, Depends(get_current_user_id)],
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=300,
            description="Busca na sintaxe do Gmail. Ex.: from:nubank.com.br, newer_than:7d",
        ),
    ],
    max_results: Annotated[int, Query(ge=1, le=50)] = 10,
) -> MessagePage:
    """Metadados dos e-mails que casam com `q` (Etapa 4: nada é persistido,
    corpo nunca é baixado). Códigos de erro:
    - 404: conexão inexistente ou de outro usuário
    - 409: conexão revogada/em erro, ou refresh token morto (reconectar)
    """
    try:
        return await email_fetcher.fetch_connection_emails(
            user_id, str(connection_id), q, max_results
        )
    except email_fetcher.ConnectionNotFoundError:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")
    except email_fetcher.ConnectionNotUsableError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Conexão com status '{exc}' — reconecte o Gmail em /gmail/connect",
        )
    except email_fetcher.GmailReconnectRequiredError:
        raise HTTPException(
            status_code=409,
            detail=(
                "Google recusou o refresh token (expirado ou revogado). "
                "Reconecte o Gmail em /gmail/connect."
            ),
        )
