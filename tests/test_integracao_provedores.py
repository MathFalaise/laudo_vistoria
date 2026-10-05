"""
Testes com API REAL — desligados por padrão.

Rodam só com INTEGRATION_TESTS=1 e a chave do provedor no ambiente:

    INTEGRATION_TESTS=1 GLM_API_KEY=... python -m pytest tests/test_integracao_provedores.py

Provam o que a documentação não garante: que o provedor RECEBE a imagem e
devolve JSON no schema pedido. A imagem é SINTÉTICA (um quadrado de cor
lisa gerado aqui) — nunca uma foto de cliente. Cada teste custa uma chamada.
"""

import io
import json
import os

import pytest
from PIL import Image

from core.providers import Imagem, criar_provedor
from core.providers.esquema import esquema

pytestmark = pytest.mark.skipif(
    os.environ.get("INTEGRATION_TESTS") != "1",
    reason="testes com API real: defina INTEGRATION_TESTS=1 e a chave do provedor",
)

ESQUEMA_COR = esquema(
    type="OBJECT",
    properties={"cor": esquema(type="STRING", enum=["vermelho", "verde", "azul", "outra"])},
    required=["cor"],
)


def _quadrado_vermelho() -> Imagem:
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), (220, 20, 20)).save(buffer, format="JPEG", quality=90)
    return Imagem(dados=buffer.getvalue(), mime="image/jpeg")


@pytest.mark.parametrize("nome, chave", [
    ("gemini", "GEMINI_API_KEY"),
    ("glm", "GLM_API_KEY"),
    ("claude", "CLAUDE_API_KEY"),
])
def test_provedor_real_ve_a_imagem_e_respeita_o_schema(nome, chave):
    if not os.environ.get(chave):
        pytest.skip(f"{chave} não definida")
    provedor = criar_provedor(nome)
    texto = provedor.gerar_json(
        [_quadrado_vermelho(), "Qual é a cor predominante desta imagem?"],
        ESQUEMA_COR, 1024, "teste de integração", "integracao",
    )
    from core.gemini_client import _extrair_json
    assert _extrair_json(texto)["cor"] == "vermelho", json.dumps(texto)
