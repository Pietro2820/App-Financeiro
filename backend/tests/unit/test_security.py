"""Testa a lógica de decode do JWT isoladamente, sem precisar de um
Supabase real. Gera um par de chaves EC de verdade (mesmo algoritmo que
o Supabase usa, ES256) e simula o cliente JWKS pra não depender de rede."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.security import AuthError, decode_supabase_jwt

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


def _make_token(
    *,
    sub: str = "user-123",
    exp_delta: timedelta = timedelta(hours=1),
    audience: str = "authenticated",
) -> str:
    payload = {
        "sub": sub,
        "aud": audience,
        "exp": datetime.now(timezone.utc) + exp_delta,
    }
    return jwt.encode(payload, _PRIVATE_KEY, algorithm="ES256")


def _patch_jwks(monkeypatch):
    from app.core import security

    fake_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=_PUBLIC_KEY)
    )
    monkeypatch.setattr(security, "get_jwks_client", lambda: fake_client)


def test_decode_valid_token(monkeypatch):
    _patch_jwks(monkeypatch)
    token = _make_token()
    payload = decode_supabase_jwt(token)
    assert payload["sub"] == "user-123"


def test_decode_expired_token_raises(monkeypatch):
    _patch_jwks(monkeypatch)
    token = _make_token(exp_delta=timedelta(hours=-1))
    with pytest.raises(AuthError):
        decode_supabase_jwt(token)


def test_decode_wrong_audience_raises(monkeypatch):
    _patch_jwks(monkeypatch)
    token = _make_token(audience="other-audience")
    with pytest.raises(AuthError):
        decode_supabase_jwt(token)
