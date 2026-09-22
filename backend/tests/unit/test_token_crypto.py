"""Testes da criptografia de tokens (Fernet) usando a chave fake do conftest.

Garantem o requisito de segurança 'tokens nunca em texto puro no banco':
roundtrip funciona, ciphertext não vaza o plaintext, e dados cifrados com
outra chave são rejeitados (uma troca acidental de TOKEN_ENCRYPTION_KEY
precisa falhar de forma detectável, não corromper silenciosamente).
"""
import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.core.token_crypto import decrypt_token, encrypt_token


def test_roundtrip_preserves_token():
    token = "ya29.fake-access-token-value"
    encrypted = encrypt_token(token)
    assert encrypted != token  # nunca armazenar em texto puro
    assert decrypt_token(encrypted) == token


def test_same_plaintext_yields_different_ciphertext():
    """Fernet embute timestamp + IV: dois encrypts do mesmo valor diferem.
    Isso impede deduzir 'duas conexões usam o mesmo token' olhando o banco."""
    token = "ya29.fake"
    assert encrypt_token(token) != encrypt_token(token)


def test_ciphertext_from_another_key_is_rejected():
    other_key_ciphertext = Fernet(Fernet.generate_key()).encrypt(b"segredo").decode()
    with pytest.raises(InvalidToken):
        decrypt_token(other_key_ciphertext)
