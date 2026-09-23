"""Testes das rotas /gmail com TestClient do FastAPI.

A fronteira mockada aqui é o serviço (email_fetcher): testamos o
comportamento HTTP — autenticação, códigos de status, validação de query
params e o filtro do response_model — sem tocar Supabase nem rede.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user_id
from app.main import app
from app.models.gmail import EmailMetadata, MessagePage
from app.services import email_fetcher

USER_ID = "user-123"
CONNECTION_ID = "3ff0d5d7-5df3-4c7a-ad4d-d9757a93aa71"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """TestClient com autenticação fake (mesma dependency da produção)."""
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    yield client
    app.dependency_overrides.clear()


def _fake_page():
    return MessagePage(
        messages=[
            EmailMetadata(
                message_id="m1",
                thread_id="t1",
                sender="Nubank <noreply@nubank.com.br>",
                subject="Fatura fechada",
                received_at=datetime(2026, 9, 22, 8, 15, tzinfo=timezone.utc),
                label_ids=["IMPORTANT"],
            )
        ],
        next_page_token="proxima-pagina",
    )


# ---------------------------------------------------------------------------
# GET /gmail/connections
# ---------------------------------------------------------------------------
def test_connections_requires_auth(client):
    assert client.get("/gmail/connections").status_code == 401


def test_connections_never_leaks_token_fields(auth_client, monkeypatch):
    """Mesmo que o service devolva um campo cifrado por engano, o
    response_model (GmailConnectionOut) filtra — defesa em profundidade."""
    row_with_leak = {
        "id": CONNECTION_ID,
        "email_address": "usuario@gmail.com",
        "scope": "gmail.readonly",
        "status": "active",
        "connected_at": "2026-09-22T12:00:00+00:00",
        "token_expires_at": None,
        "access_token_encrypted": "NAO-DEVERIA-VAZAR",
    }
    monkeypatch.setattr(email_fetcher, "list_connections", lambda user_id: [row_with_leak])

    response = auth_client.get("/gmail/connections")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == CONNECTION_ID
    assert body[0]["email_address"] == "usuario@gmail.com"
    assert "access_token_encrypted" not in body[0]
    assert "NAO-DEVERIA-VAZAR" not in response.text


def test_connections_passes_authenticated_user(auth_client, monkeypatch):
    seen_users = []
    monkeypatch.setattr(
        email_fetcher,
        "list_connections",
        lambda user_id: seen_users.append(user_id) or [],
    )

    auth_client.get("/gmail/connections")

    assert seen_users == [USER_ID]


# ---------------------------------------------------------------------------
# GET /gmail/connections/{id}/messages
# ---------------------------------------------------------------------------
def test_messages_requires_auth(client):
    response = client.get(f"/gmail/connections/{CONNECTION_ID}/messages", params={"q": "x"})
    assert response.status_code == 401


def test_messages_returns_metadata_page(auth_client, monkeypatch):
    async def fake_fetch(user_id, connection_id, query, max_results):
        assert user_id == USER_ID
        assert connection_id == CONNECTION_ID
        assert query == "from:nubank.com.br"
        assert max_results == 10  # default
        return _fake_page()

    monkeypatch.setattr(email_fetcher, "fetch_connection_emails", fake_fetch)

    response = auth_client.get(
        f"/gmail/connections/{CONNECTION_ID}/messages",
        params={"q": "from:nubank.com.br"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["next_page_token"] == "proxima-pagina"
    message = body["messages"][0]
    assert message["sender"] == "Nubank <noreply@nubank.com.br>"
    assert message["subject"] == "Fatura fechada"
    assert message["received_at"] == "2026-09-22T08:15:00Z"


def test_messages_404_when_connection_missing(auth_client, monkeypatch):
    async def fake_fetch(*args):
        raise email_fetcher.ConnectionNotFoundError(CONNECTION_ID)

    monkeypatch.setattr(email_fetcher, "fetch_connection_emails", fake_fetch)

    response = auth_client.get(f"/gmail/connections/{CONNECTION_ID}/messages", params={"q": "x"})
    assert response.status_code == 404


def test_messages_409_when_connection_revoked(auth_client, monkeypatch):
    async def fake_fetch(*args):
        raise email_fetcher.ConnectionNotUsableError("revoked")

    monkeypatch.setattr(email_fetcher, "fetch_connection_emails", fake_fetch)

    response = auth_client.get(f"/gmail/connections/{CONNECTION_ID}/messages", params={"q": "x"})
    assert response.status_code == 409
    assert "revoked" in response.json()["detail"]


def test_messages_409_when_reconnect_required(auth_client, monkeypatch):
    async def fake_fetch(*args):
        raise email_fetcher.GmailReconnectRequiredError(CONNECTION_ID)

    monkeypatch.setattr(email_fetcher, "fetch_connection_emails", fake_fetch)

    response = auth_client.get(f"/gmail/connections/{CONNECTION_ID}/messages", params={"q": "x"})
    assert response.status_code == 409
    assert "Reconecte" in response.json()["detail"]


@pytest.mark.parametrize(
    "params",
    [
        {},                                # q é obrigatório
        {"q": ""},                         # q vazio (min_length=1)
        {"q": "x", "max_results": 0},      # abaixo do mínimo
        {"q": "x", "max_results": 51},     # acima do teto (proteção de quota)
    ],
)
def test_messages_validates_query_params(auth_client, params):
    response = auth_client.get(f"/gmail/connections/{CONNECTION_ID}/messages", params=params)
    assert response.status_code == 422


def test_messages_malformed_connection_id_returns_422(auth_client):
    """Regressão do bug real: '<id>' literal na URL chegava ao PostgREST
    (coluna uuid) e virava 500. Com o path param tipado UUID, o FastAPI
    rejeita antes de tocar o banco."""
    response = auth_client.get("/gmail/connections/<id>/messages", params={"q": "x"})
    assert response.status_code == 422


def test_revoke_malformed_connection_id_returns_422(auth_client):
    """Mesma proteção na rota de revoke."""
    response = auth_client.post("/gmail/revoke/nao-sou-uuid")
    assert response.status_code == 422
