"""
Utilitários para localizar, redimensionar e codificar as fotos de cada
cômodo antes de enviar para a API do Gemini.
"""

import io
import os

from google.genai import types
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


def codificar_imagem(caminho: str) -> types.Part:
    """Abre, redimensiona (se necessário) e converte uma imagem em um
    Part pronto para entrar no 'contents' de uma mensagem da API do Gemini."""
    with Image.open(caminho) as img:
        img = img.convert("RGB")

        lado_maior = max(img.size)
        if lado_maior > TAMANHO_MAX_IMAGEM:
            fator = TAMANHO_MAX_IMAGEM / lado_maior
            novo_tamanho = (int(img.width * fator), int(img.height * fator))
            img = img.resize(novo_tamanho, Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        dados_bytes = buffer.getvalue()

    return types.Part.from_bytes(data=dados_bytes, mime_type="image/jpeg")


def codificar_fotos_comodo(pasta_comodo: str) -> list:
    """Codifica todas as fotos de um cômodo em blocos prontos para a API."""
    caminhos = listar_fotos(pasta_comodo)
    return [codificar_imagem(caminho) for caminho in caminhos]


def montar_mosaicos(caminhos: list, fotos_por_mosaico: int) -> list:
    """Junta as fotos em mosaicos (folhas de contato): cada mosaico é UMA
    imagem para a API, com várias fotos lado a lado.

    Por que existe: o Gemini cobra por IMAGEM, não por pixel. Medido em
    22/09/2026 com `usage_metadata`: 1.101 tokens por foto, o mesmo número
    com a foto em 1568px ou em 256px. Então diminuir a resolução não
    economiza nada — o que economiza é mandar menos imagens. Quatro fotos
    num mosaico custam 1/4 do preço das mesmas quatro soltas.

    Usado só na conferência (conferir.py), onde o objetivo é achar item que
    ficou de fora do laudo — coisa grande, que aparece mesmo em miniatura.
    A análise que ESCREVE o laudo continua mandando foto por foto, porque
    lá o detalhe fino importa (nº de gavetas, tipo de puxador)."""
    lado_grade = max(1, round(fotos_por_mosaico ** 0.5))
    por_mosaico = lado_grade * lado_grade

    mosaicos = []
    for inicio in range(0, len(caminhos), por_mosaico):
        lote = caminhos[inicio:inicio + por_mosaico]
        # A última folha pode ter menos fotos; a grade encolhe junto para as
        # miniaturas não ficarem menores do que precisam ser.
        grade = max(1, min(lado_grade, round(len(lote) ** 0.5 + 0.49)))
        celula = TAMANHO_MAX_IMAGEM // grade
        linhas = (len(lote) + grade - 1) // grade
        folha = Image.new("RGB", (grade * celula, linhas * celula), "white")
        for posicao, caminho in enumerate(lote):
            with Image.open(caminho) as img:
                img = img.convert("RGB")
                img.thumbnail((celula, celula), Image.LANCZOS)
                folha.paste(
                    img,
                    ((posicao % grade) * celula,
                     (posicao // grade) * celula + (celula - img.height) // 2),
                )
        buffer = io.BytesIO()
        folha.save(buffer, format="JPEG", quality=85)
        mosaicos.append(types.Part.from_bytes(data=buffer.getvalue(), mime_type="image/jpeg"))
    return mosaicos


def mosaicos_comodo(pasta_comodo: str, fotos_por_mosaico: int) -> tuple:
    """(mosaicos, quantidade de fotos) de um cômodo."""
    caminhos = listar_fotos(pasta_comodo)
    return montar_mosaicos(caminhos, fotos_por_mosaico), len(caminhos)
