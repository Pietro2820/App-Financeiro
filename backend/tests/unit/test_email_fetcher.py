"""Testes do email_fetcher (serviço) com fakes explícitos.

Camada de HTTP é substituída por FakeGmailClient e o Supabase por
FakeSupabase — preferível a MagicMock aqui: a cadeia
table().select().eq()... fica legível e as asserções verificam
comportamento real (colunas selecionadas, filtros, updates persistidos),
não "mágica de mock".
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.token_crypto import decrypt_token, encrypt_token
from app.integrations.gmail_client import GmailUnauthorizedError, InvalidGrantError
from app.services import email_fetcher
from app.services.email_fetcher import (
    ConnectionNotFoundError,
    ConnectionNotUsableError,
    GmailReconnectRequiredError,
    fetch_connection_emails,
    list_connections,
)

USER_ID = "11111111-1111-1111-1111-111111111111"
CONNECTION_ID = "22222222-2222-2222-2222-222222222222"
NEW_ACCESS_TOKEN = "ya29.novo-access-token"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class _FakeQuery:
    """Cadeia encadeável select/eq/maybe_single/order/update/execute."""

    def __init__(self, fake, result):
        self._fake = fake
        self._result = result
        self.select_columns: str | None = None
        self.update_values: dict | None = None
        self.filters: list[tuple[str, str]] = []

    def select(self, columns):
        self.select_columns = columns
        return self

    def update(self, values):
        self.update_values = values
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def maybe_single(self):
        return self

    def order(self, *args, **kwargs):
        return self

    def execute(self):
        self._fake.queries.append(self)
        return SimpleNamespace(data=self._result)


class FakeSupabase:
    def __init__(self, select_result=None):
        self.select_result = select_result
        self.queries: list[_FakeQuery] = []
        self.table_name: str | None = None

    def table(self, name):
        self.table_name = name
        return self

    def select(self, columns):
        query = _FakeQuery(self, self.select_result)
        return query.select(columns)

    def update(self, values):
        query = _FakeQuery(self, None)
        return query.update(values)


class FakeGmailClient:
    """Mesma interface do GmailClient que o fetcher usa."""

    def __init__(self, access_token, *, list_result=None, list_error=None, metadata_by_id=None):
        self.access_token = access_token
        self.list_calls: list[str] = []
        self.metadata_calls: list[str] = []
        self._list_result = list_result
        self._list_error = list_error
        self._metadata_by_id = metadata_by_id or {}

    async def list_messages(self, query, max_results=10, page_token=None):
        self.list_calls.append(query)
        if self._list_error:
            raise self._list_error
        return self._list_result

    async def get_message_metadata(self, message_id):
        self.metadata_calls.append(message_id)
        return self._metadata_by_id[message_id]


# ---------------------------------------------------------------------------
# Helpers de montagem
# ---------------------------------------------------------------------------
def _connection_row(*, status="active", access_token="fake-access-token", expires_in_minutes=60):
    expires_at = None
    if expires_in_minutes is not None:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
        ).isoformat()
    return {
        "id": CONNECTION_ID,
        "user_id": USER_ID,
        "email_address": "usuario@gmail.com",
        "status": status,
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "access_token_encrypted": encrypt_token(access_token),
        "refresh_token_encrypted": encrypt_token("fake-refresh-token"),
        "token_expires_at": expires_at,
    }


def _patch_supabase(monkeypatch, select_result):
    fake = FakeSupabase(select_result)
    monkeypatch.setattr(email_fetcher, "get_supabase", lambda: fake)
    return fake


def _patch_refresh(monkeypatch, error=None):
    calls: list[str] = []

    async def fake_refresh(refresh_token):
        calls.append(refresh_token)
        if error:
            raise error
        return NEW_ACCESS_TOKEN, datetime.now(timezone.utc) + timedelta(hours=1)

    monkeypatch.setattr(email_fetcher, "refresh_access_token", fake_refresh)
    return calls


def _patch_client_factory(monkeypatch, *, list_result, metadata_by_id, list_error=None):
    created: list[FakeGmailClient] = []

    def factory(access_token):
        client = FakeGmailClient(
            access_token,
            list_result=list_result,
            list_error=list_error,
            metadata_by_id=metadata_by_id,
        )
        created.append(client)
        return client

    monkeypatch.setattr(email_fetcher, "GmailClient", factory)
    return created


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_fresh_token_skips_refresh_and_returns_metadata(monkeypatch, gmail_api_fixture):
    row = _connection_row(expires_in_minutes=60)
    _patch_supabase(monkeypatch, row)
    refresh_calls = _patch_refresh(monkeypatch)
    created = _patch_client_factory(
        monkeypatch,
        list_result=gmail_api_fixture("messages_list.json"),
        metadata_by_id={
            "18f3a2b4c5d6e7f8": gmail_api_fixture("message_get_metadata_1.json"),
            "18f3a1a0b9c8d7e6": gmail_api_fixture("message_get_metadata_2.json"),
        },
    )

    page = await fetch_connection_emails(USER_ID, CONNECTION_ID, "from:nubank.com.br")

    assert refresh_calls == []  # token fresco: nenhuma renovação
    assert created[0].access_token == "fake-access-token"  # decriptado do banco
    assert len(page.messages) == 2
    assert page.next_page_token == "00765432109876543210"
    first = page.messages[0]
    assert first.message_id == "18f3a2b4c5d6e7f8"
    assert first.sender == "Nubank <noreply@nubank.com.br>"
    assert first.received_at == datetime.fromtimestamp(1790035200, tz=timezone.utc)
    assert created[0].metadata_calls == ["18f3a2b4c5d6e7f8", "18f3a1a0b9c8d7e6"]


@pytest.mark.anyio
async def test_missing_expiry_triggers_proactive_refresh_and_persists(
    monkeypatch, gmail_api_fixture
):
    """token_expires_at NULL (conexão antiga) → renova ANTES de chamar a API
    e persiste o novo token cifrado + expiração."""
    row = _connection_row(expires_in_minutes=None)
    fake_db = _patch_supabase(monkeypatch, row)
    refresh_calls = _patch_refresh(monkeypatch)
    created = _patch_client_factory(
        monkeypatch,
        list_result={"messages": []},
        metadata_by_id={},
    )

    await fetch_connection_emails(USER_ID, CONNECTION_ID, "q")

    assert refresh_calls == ["fake-refresh-token"]  # refresh token decriptado
    assert created[0].access_token == NEW_ACCESS_TOKEN
    update = next(q for q in fake_db.queries if q.update_values)
    assert decrypt_token(update.update_values["access_token_encrypted"]) == NEW_ACCESS_TOKEN
    assert update.update_values["token_expires_at"]  # expiração persistida
    assert ("user_id", USER_ID) in update.filters  # update escopado


@pytest.mark.anyio
async def test_expiry_inside_margin_triggers_refresh(monkeypatch):
    """Expira em 2min < margem de 5min → refresh proativo."""
    row = _connection_row(expires_in_minutes=2)
    _patch_supabase(monkeypatch, row)
    refresh_calls = _patch_refresh(monkeypatch)
    _patch_client_factory(monkeypatch, list_result={"messages": []}, metadata_by_id={})

    await fetch_connection_emails(USER_ID, CONNECTION_ID, "q")

    assert refresh_calls == ["fake-refresh-token"]


@pytest.mark.anyio
async def test_invalid_grant_marks_error_and_raises_reconnect(monkeypatch):
    row = _connection_row(expires_in_minutes=None)
    fake_db = _patch_supabase(monkeypatch, row)
    _patch_refresh(monkeypatch, error=InvalidGrantError(400, "morto"))

    with pytest.raises(GmailReconnectRequiredError):
        await fetch_connection_emails(USER_ID, CONNECTION_ID, "q")

    update = next(q for q in fake_db.queries if q.update_values)
    assert update.update_values == {"status": "error"}  # falha visível no banco
    assert ("id", CONNECTION_ID) in update.filters
    assert ("user_id", USER_ID) in update.filters


@pytest.mark.anyio
async def test_connection_not_found_raises(monkeypatch):
    _patch_supabase(monkeypatch, None)  # maybe_single sem linha → data=None
    _patch_refresh(monkeypatch)

    with pytest.raises(ConnectionNotFoundError):
        await fetch_connection_emails(USER_ID, CONNECTION_ID, "q")


@pytest.mark.anyio
async def test_revoked_connection_rejected_before_any_http(monkeypatch):
    row = _connection_row(status="revoked")
    _patch_supabase(monkeypatch, row)
    refresh_calls = _patch_refresh(monkeypatch)
    created = _patch_client_factory(monkeypatch, list_result={"messages": []}, metadata_by_id={})

    with pytest.raises(ConnectionNotUsableError):
        await fetch_connection_emails(USER_ID, CONNECTION_ID, "q")

    assert refresh_calls == []
    assert created == []  # nenhuma chamada externa


@pytest.mark.anyio
async def test_reactive_refresh_on_401_retries_once(monkeypatch, gmail_api_fixture):
    """Token 'fresco' mas o Google devolveu 401 → refresh + 1 retry."""
    row = _connection_row(expires_in_minutes=60)
    _patch_supabase(monkeypatch, row)
    refresh_calls = _patch_refresh(monkeypatch)

    created: list[FakeGmailClient] = []

    def factory(access_token):
        # 1ª instância: simula 401 do Google; 2ª (pós-refresh): funciona
        client = FakeGmailClient(
            access_token,
            list_error=GmailUnauthorizedError(401, "expired") if not created else None,
            list_result=gmail_api_fixture("messages_list.json"),
            metadata_by_id={
                "18f3a2b4c5d6e7f8": gmail_api_fixture("message_get_metadata_1.json"),
                "18f3a1a0b9c8d7e6": gmail_api_fixture("message_get_metadata_2.json"),
            },
        )
        created.append(client)
        return client

    monkeypatch.setattr(email_fetcher, "GmailClient", factory)

    page = await fetch_connection_emails(USER_ID, CONNECTION_ID, "q")

    assert len(created) == 2
    assert created[0].access_token == "fake-access-token"
    assert created[1].access_token == NEW_ACCESS_TOKEN
    assert refresh_calls == ["fake-refresh-token"]
    assert len(page.messages) == 2


@pytest.mark.anyio
async def test_load_query_is_user_scoped_and_minimal(monkeypatch):
    """A service key bypassa RLS → toda query tem que filtrar user_id
    explicitamente, e o select não pode trazer mais colunas que o necessário."""
    fake_db = _patch_supabase(monkeypatch, _connection_row())
    _patch_refresh(monkeypatch)
    _patch_client_factory(monkeypatch, list_result={"messages": []}, metadata_by_id={})

    await fetch_connection_emails(USER_ID, CONNECTION_ID, "q")

    load_query = next(q for q in fake_db.queries if q.select_columns and q.filters)
    assert ("user_id", USER_ID) in load_query.filters  # escopo explícito
    assert ("id", CONNECTION_ID) in load_query.filters
    # o load interno PRECISA dos tokens cifrados (para decriptar em memória),
    # mas nunca de colunas além das declaradas
    assert "access_token_encrypted" in load_query.select_columns
    assert "refresh_token_encrypted" in load_query.select_columns


@pytest.mark.anyio
async def test_list_connections_select_excludes_token_columns(monkeypatch):
    rows = [{
        "id": CONNECTION_ID,
        "email_address": "usuario@gmail.com",
        "scope": "gmail.readonly",
        "status": "active",
        "connected_at": "2026-09-22T12:00:00+00:00",
        "token_expires_at": None,
    }]
    fake_db = _patch_supabase(monkeypatch, rows)

    result = list_connections(USER_ID)

    assert result == rows
    query = fake_db.queries[0]
    assert "encrypted" not in query.select_columns  # tokens nem circulam
    assert ("user_id", USER_ID) in query.filters
