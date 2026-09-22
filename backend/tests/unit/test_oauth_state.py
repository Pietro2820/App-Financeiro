"""Testes do 'state' do fluxo OAuth (anti-CSRF) — funções puras, sem rede.

O state carrega o user_id assinado com HMAC; estes testes garantem que
qualquer adulteração (payload trocado, assinatura forjada, expiração) é
rejeitada — caso contrário, um atacante poderia completar o fluxo OAuth
no lugar de outro usuário.
"""
import time

import pytest

from app.core.oauth_state import create_state, verify_state


def test_valid_state_returns_user_id():
    state = create_state(user_id="user-123")
    assert verify_state(state) == "user-123"


def test_payload_from_another_state_fails():
    """Assinatura de um state não valida o payload de outro."""
    legit = create_state(user_id="user-123")
    forged = create_state(user_id="attacker")
    _, legit_signature = legit.split(".", 1)
    forged_payload, _ = forged.split(".", 1)
    with pytest.raises(ValueError):
        verify_state(f"{forged_payload}.{legit_signature}")


def test_tampered_signature_fails():
    state = create_state(user_id="user-123")
    payload_b64, _ = state.split(".", 1)
    with pytest.raises(ValueError):
        verify_state(f"{payload_b64}.{'0' * 64}")


def test_expired_state_fails(monkeypatch):
    """TTL de 10min: state criado agora deve falhar se o relógio avançar."""
    state = create_state(user_id="user-123")
    real_now = time.time()
    monkeypatch.setattr(time, "time", lambda: real_now + 601)
    with pytest.raises(ValueError):
        verify_state(state)


def test_malformed_state_fails():
    with pytest.raises(ValueError):
        verify_state("string-sem-ponto")
