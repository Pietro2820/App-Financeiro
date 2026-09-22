"""Contrato comum que todo parser de instituição deve implementar.

Cada parser concreto (nubank.py, inter.py, bradesco.py) recebe um e-mail
bruto e devolve transações no modelo normalizado — sem saber nada sobre
Gmail, banco de dados ou dedupe. Implementações concretas chegam na
Etapa 5 em diante.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class NormalizedTransaction:
    """Modelo único de transação, independente do banco de origem."""

    transaction_date: date
    description_original: str
    description_normalized: str
    amount: Decimal
    transaction_type: Literal["credit", "debit", "transfer"]
    index_in_email: int  # posição dentro do e-mail (0-based) — ver ADR 0001


class BaseInstitutionParser(ABC):
    """Um parser por instituição. NÃO deve conter if/else para outros bancos."""

    institution_slug: str  # deve bater com financial_institutions.slug

    @abstractmethod
    def can_parse(self, raw_email_subject: str, raw_email_body: str) -> bool:
        """Heurística rápida: este e-mail pertence a esta instituição?"""
        raise NotImplementedError

    @abstractmethod
    def parse(self, raw_email_body: str) -> list[NormalizedTransaction]:
        """Extrai 0..N transações do corpo do e-mail. Levanta ParserError
        (a ser definida) se não conseguir extrair os campos esperados —
        nunca deve falhar silenciosamente."""
        raise NotImplementedError
