"""Geração e validação do 'state' do fluxo OAuth (anti-CSRF + carrega user_id)."""
import time
import hmac
import hashlib
import base64
import json
from app.core.config import get_settings

_STATE_TTL_SECONDS = 600  # 10 minutos pra completar o fluxo


def create_state(user_id: str) -> str:
    payload = {"user_id": user_id, "exp": int(time.time()) + _STATE_TTL_SECONDS}
    payload_json = json.dumps(payload).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode()
    signature = _sign(payload_b64)
    return f"{payload_b64}.{signature}"


def verify_state(state: str) -> str:
    """Retorna o user_id se o state for válido; levanta ValueError caso contrário."""
    try:
        payload_b64, signature = state.split(".", 1)
    except ValueError:
        raise ValueError("state malformado")

    if not hmac.compare_digest(_sign(payload_b64), signature):
        raise ValueError("assinatura do state inválida")

    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    if payload["exp"] < time.time():
        raise ValueError("state expirado")

    return payload["user_id"]


def _sign(payload_b64: str) -> str:
    settings = get_settings()
    return hmac.new(
        settings.oauth_state_secret.encode(),
        payload_b64.encode(),
        hashlib.sha256,
    ).hexdigest()
