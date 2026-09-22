"""Garante que BaseInstitutionParser é de fato abstrata e não instanciável
diretamente — protege contra alguém "implementar" um parser sem
sobrescrever can_parse/parse."""
import pytest

from app.parsers.base import BaseInstitutionParser


def test_base_parser_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseInstitutionParser()
