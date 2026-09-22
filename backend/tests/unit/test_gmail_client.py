"""Testes do GmailClient + refresh_access_token com respx.

O respx intercepta o httpx no nível de transporte: o código de produção
executa de verdade (serialização de params, headers, parsing de erro) —
só a rede é fake. As respostas vêm de fixtures com o formato real da API.
"""
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.integrations import gmail_client
from app.integrations.gmail_client import (
    GmailClient,
    GmailForbiddenError,
    GmailUnauthorizedError,
    InvalidGrantError,
    refresh_access_token,
)


@pytest.mark.anyio
@respx.mock
async def test_list_messages_builds_request_and_returns_page(gmail_api_fixture):
    route = respx.get(f"{gmail_client.GMAIL_API_BASE}/users/me/messages").mock(
        return_value=httpx.Response(200, json=gmail_api_fixture("messages_list.json"))
    )

    page = await GmailClient("fake-access-token").list_messages(
        "from:nubank.com.br", max_results=10
    )

    assert len(page["messages"]) == 2
    assert page["nextPageToken"] == "00765432109876543210"
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer fake-access-token"
    assert request.url.params["q"] == "from:nubank.com.br"
    assert request.url.params["maxResults"] == "10"
    assert "pageToken" not in request.url.params


@pytest.mark.anyio
@respx.mock
async def test_list_messages_forwards_page_token(gmail_api_fixture):
    route = respx.get(f"{gmail_client.GMAIL_API_BASE}/users/me/messages").mock(
        return_value=httpx.Response(200, json=gmail_api_fixture("messages_list.json"))
    )

    await GmailClient("t").list_messages("q", page_token="abc123")

    assert route.calls.last.request.url.params["pageToken"] == "abc123"


@pytest.mark.anyio
@respx.mock
async def test_get_message_metadata_never_requests_full_body(gmail_api_fixture):
    """Requisito de segurança: format=metadata + só headers From/Subject/Date."""
    route = respx.get(
        f"{gmail_client.GMAIL_API_BASE}/users/me/messages/18f3a2b4c5d6e7f8"
    ).mock(return_value=httpx.Response(200, json=gmail_api_fixture("message_get_metadata_1.json")))

    data = await GmailClient("t").get_message_metadata("18f3a2b4c5d6e7f8")

    assert data["id"] == "18f3a2b4c5d6e7f8"
    params = route.calls.last.request.url.params
    assert params["format"] == "metadata"
    assert params.get_list("metadataHeaders") == ["From", "Subject", "Date"]


@pytest.mark.anyio
@respx.mock
async def test_list_messages_401_raises_unauthorized(gmail_api_fixture):
    respx.get(f"{gmail_client.GMAIL_API_BASE}/users/me/messages").mock(
        return_value=httpx.Response(401, json=gmail_api_fixture("gmail_error_401.json"))
    )
    with pytest.raises(GmailUnauthorizedError) as exc_info:
        await GmailClient("token-morto").list_messages("q")
    assert "invalid authentication" in exc_info.value.detail


@pytest.mark.anyio
@respx.mock
async def test_get_message_403_raises_forbidden_with_hint(gmail_api_fixture):
    respx.get(f"{gmail_client.GMAIL_API_BASE}/users/me/messages/abc").mock(
        return_value=httpx.Response(403, json=gmail_api_fixture("gmail_error_403.json"))
    )
    with pytest.raises(GmailForbiddenError) as exc_info:
        await GmailClient("t").get_message_metadata("abc")
    # a mensagem deve orientar o debug (escopo / API habilitada)
    assert "gmail.readonly" in exc_info.value.detail


@pytest.mark.anyio
@respx.mock
async def test_refresh_access_token_returns_token_and_expiry(gmail_api_fixture):
    route = respx.post(gmail_client.TOKEN_URL).mock(
        return_value=httpx.Response(200, json=gmail_api_fixture("token_refresh_ok.json"))
    )

    before = datetime.now(timezone.utc)
    access_token, expires_at = await refresh_access_token("fake-refresh-token")

    assert access_token == "ya29.a0AfH6SM-fake-refreshed-access-token"
    # expires_in=3599 → expiração ≈ now + 1h (tolerância p/ duração do teste)
    delta = (expires_at - before).total_seconds()
    assert 3590 <= delta <= 3600
    body = route.calls.last.request.read().decode()
    assert "grant_type=refresh_token" in body
    assert "refresh_token=fake-refresh-token" in body


@pytest.mark.anyio
@respx.mock
async def test_refresh_with_dead_token_raises_invalid_grant(gmail_api_fixture):
    respx.post(gmail_client.TOKEN_URL).mock(
        return_value=httpx.Response(400, json=gmail_api_fixture("token_refresh_invalid_grant.json"))
    )
    with pytest.raises(InvalidGrantError):
        await refresh_access_token("refresh-token-morto")
