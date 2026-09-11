"""
Utilitários para localizar, redimensionar e codificar as fotos de cada
cômodo antes de enviar para a API da Claude.
"""

import base64
import io
import os

from PIL import Image

from config import EXTENSOES_IMAGEM, TAMANHO_MAX_IMAGEM


def listar_fotos(pasta_comodo: str) -> list:
    """Retorna a lista de caminhos de imagem dentro da pasta do cômodo,
    em ordem alfabética (geralmente = ordem cronológica pelo nome do arquivo)."""
    arquivos = [
        os.path.join(pasta_comodo, nome)
        for nome in sorted(os.listdir(pasta_comodo))
        if nome.lower().endswith(EXTENSOES_IMAGEM)
    ]
    return arquivos


def codificar_imagem(caminho: str) -> dict:
    """Abre, redimensiona (se necessário) e codifica uma imagem em base64,
    pronta para entrar no bloco 'content' de uma mensagem da API da Claude."""
    with Image.open(caminho) as img:
        img = img.convert("RGB")

        lado_maior = max(img.size)
        if lado_maior > TAMANHO_MAX_IMAGEM:
            fator = TAMANHO_MAX_IMAGEM / lado_maior
            novo_tamanho = (int(img.width * fator), int(img.height * fator))
            img = img.resize(novo_tamanho, Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        dados_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": dados_base64,
        },
    }


def codificar_fotos_comodo(pasta_comodo: str) -> list:
    """Codifica todas as fotos de um cômodo em blocos prontos para a API."""
    caminhos = listar_fotos(pasta_comodo)
    return [codificar_imagem(caminho) for caminho in caminhos]
