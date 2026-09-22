"""Cliente REST da Gmail API + refresh de token OAuth (camada mais baixa).

Responsabilidade única: traduzir chamadas Python em HTTP e devolver dados
crus (dicts) ou levantar exceções tipadas. NÃO conhece banco, usuário ou
regra de negócio — quem decide quando renovar token e o que persistir é
`services/email_fetcher.py`.

Erros tipados importam porque cada um pede uma reação diferente do chamador:
- GmailUnauthorizedError (401)  → renovar access token e tentar 1x
- GmailForbiddenError    (403)  → escopo/API desabilitada: erro de configuração
- InvalidGrantError             → refresh token morto: só reconectando a conta
"""
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import get_settings

GMAIL_API_BASE = "https://www.googleapis.com/gmail/v1"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# O mínimo para identificar um e-mail sem baixar o corpo (requisito de
# segurança: não trafegar conteúdo além do necessário).
METADATA_HEADERS = ["From", "Subject", "Date"]

_DEFAULT_TIMEOUT = 15.0


class GmailApiError(Exception):
    """Qualquer falha HTTP da Gmail API (status >= 400)."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Gmail API {status_code}: {detail}")


class GmailUnauthorizedError(GmailApiError):
    """401: access token inválido/expirado."""


class GmailForbiddenError(GmailApiError):
    """403: escopo insuficiente OU Gmail API não habilitada no projeto Google."""


class InvalidGrantError(GmailApiError):
    """Refresh token revogado/expirado (ex.: app OAuth em modo Testing expira
    o refresh token em 7 dias). Recuperação = reconectar a conta."""


def _error_detail(response: httpx.Response) -> str:
    """Extrai a mensagem de erro do Google. Nunca inclui o token: as
    respostas de erro do Google não ecoam credenciais, e limitamos o tamanho
    para não estourar logs."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    err = body.get("error", {})
    if isinstance(err, dict):
        return str(err.get("message", err))[:200]
    return str(err)[:200]


async def refresh_access_token(refresh_token: str) -> tuple[str, datetime]:
    """Troca o refresh_token por um access_token novo.

    Retorna `(access_token, expires_at_utc)` — a expiração é calculada aqui
    (now + expires_in) porque o Google devolve duração, não timestamp.
    Levanta InvalidGrantError se o refresh token estiver morto.
    """
    settings = get_settings()
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
        })
    if response.status_code == 400 and "invalid_grant" in response.text:
        raise InvalidGrantError(400, "refresh_token revogado ou expirado — reconectar Gmail")
    response.raise_for_status()
    data = response.json()
    expires_in = int(data.get("expires_in", 3600))
    return data["access_token"], datetime.now(timezone.utc) + timedelta(seconds=expires_in)


class GmailClient:
    """Chamadas autenticadas à Gmail API com um access_token JÁ VÁLIDO.

    Stateless por chamada (um httpx.AsyncClient por request): para o volume
    de um app pessoal (dezenas de e-mails por sync) o overhead de handshake
    é irrelevante, e evita gerenciar ciclo de vida de conexão/client.
    """

    def __init__(self, access_token: str):
        self._headers = {"Authorization": f"Bearer {access_token}"}

    async def list_messages(
        self,
        query: str,
        max_results: int = 10,
        page_token: str | None = None,
    ) -> dict:
        """GET messages.list — retorna dict cru: {messages: [{id, threadId}],
        nextPageToken?, resultSizeEstimate}. `query` usa sintaxe de busca do
        Gmail (ex.: 'from:nubank.com.br newer_than:7d')."""
        params: dict[str, str | int] = {"q": query, "maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages",
                headers=self._headers,
                params=params,
            )
        self._raise_for_status(response)
        return response.json()

    async def get_message_metadata(self, message_id: str) -> dict:
        """GET messages.get com format=metadata — o corpo do e-mail NUNCA é
        baixado (só headers From/Subject/Date + internalDate/labelIds)."""
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages/{message_id}",
                headers=self._headers,
                # httpx serializa lista como parâmetros repetidos, que é o
                # formato que a Gmail API espera para metadataHeaders
                params={"format": "metadata", "metadataHeaders": METADATA_HEADERS},
            )
        self._raise_for_status(response)
        return response.json()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise GmailUnauthorizedError(401, _error_detail(response))
        if response.status_code == 403:
            raise GmailForbiddenError(
                403,
                _error_detail(response)
                + " (verifique o escopo gmail.readonly"
                " e se a Gmail API esta habilitada no projeto)",
            )
        if response.status_code >= 400:
            raise GmailApiError(response.status_code, _error_detail(response))
