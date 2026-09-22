"""Schemas Pydantic da integração Gmail (entrada) e da API (saída).

`EmailMetadata.from_api_response` é o ÚNICO lugar que conhece o formato da
resposta do `messages.get?format=metadata` — se o Google mudar o wire format,
o ajuste fica isolado aqui (mesmo princípio dos parsers por instituição).
"""
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class GmailConnectionOut(BaseModel):
    """Conexão Gmail para exibição na API.

    Deliberadamente SEM campos de token (nem cifrados): o response_model do
    FastAPI filtra qualquer campo extra que o service devolva por engano —
    defesa em profundidade contra vazamento.
    """

    id: str
    email_address: str
    scope: str
    status: str
    connected_at: datetime
    token_expires_at: datetime | None = None


class EmailMetadata(BaseModel):
    """Metadados de um e-mail — sem corpo e sem snippet, de propósito.

    Conteúdo financeiro só deve circular quando estritamente necessário
    (requisito de segurança). A Etapa 4 não persiste nada; a partir da
    Etapa 6 o que vai ao banco é o payload normalizado + hash (ADR 0001).
    """

    message_id: str
    thread_id: str
    sender: str
    subject: str
    received_at: datetime
    label_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "EmailMetadata":
        """Converte a resposta crua do messages.get (format=metadata)."""
        headers = {
            h["name"].lower(): h["value"]
            for h in data.get("payload", {}).get("headers", [])
        }
        # internalDate (epoch ms, string) é a hora de chegada no servidor do
        # Google — mais confiável que o header Date, que o remetente monta.
        internal_date_ms = int(data.get("internalDate") or 0)
        return cls(
            message_id=data["id"],
            thread_id=data.get("threadId") or data["id"],
            sender=headers.get("from", ""),
            subject=headers.get("subject", "(sem assunto)"),
            received_at=datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc),
            label_ids=data.get("labelIds", []),
        )


class MessagePage(BaseModel):
    """Uma página de resultados: metadados + cursor para a próxima."""

    messages: list[EmailMetadata]
    next_page_token: str | None = None
