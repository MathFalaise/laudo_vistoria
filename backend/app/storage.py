"""
Armazenamento de fotos em disco, com as travas de segurança do upload.

Duas ideias organizam este módulo:

1. NADA que o usuário escreve vira caminho. Nome de arquivo e nome de cômodo
   entram como dado; o caminho no disco é montado a partir de UUIDs. Isso
   elimina a classe inteira de path traversal em vez de tentar filtrá-la.
2. Extensão não é prova. O arquivo é aberto e decodificado pelo Pillow antes
   de ser aceito (regra 28) — "foto.jpg" que na verdade é um .exe não passa,
   e um HEIC sem extensão passa.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.config import (DIRETORIO_FOTOS, MAX_ARQUIVOS_ZIP, MAX_DESCOMPACTADO_ZIP,
                        TAMANHO_MAX_FOTO)

# Registra o decodificador HEIC no Pillow. Sem isto, a foto padrão do iPhone
# é rejeitada — e metade das vistorias chega de iPhone.
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIC_DISPONIVEL = True
except Exception:  # pragma: no cover - ambiente sem a roda compilada
    HEIC_DISPONIVEL = False

FORMATOS_ACEITOS = {"JPEG", "PNG", "HEIF", "MPO"}
EXTENSOES_ACEITAS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}

MIME_POR_FORMATO = {
    "JPEG": "image/jpeg", "MPO": "image/jpeg",
    "PNG": "image/png", "HEIF": "image/heic",
}


class ArquivoRejeitado(ValueError):
    """Upload que não passou na validação. A mensagem vai para o usuário, então
    diz o que houve sem vazar caminho de servidor."""


def _pasta_do_comodo(comodo_id: str) -> Path:
    """Caminho derivado só de UUID — nunca de texto que o usuário escreveu."""
    if not comodo_id.isalnum():
        raise ArquivoRejeitado("Identificador de cômodo inválido.")
    pasta = DIRETORIO_FOTOS / comodo_id[:2] / comodo_id
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def caminho_absoluto(caminho_relativo: str) -> Path:
    """Resolve um caminho do banco para o disco, recusando qualquer coisa que
    escape do diretório de fotos.

    Esta é a última linha de defesa: mesmo que um caminho malicioso chegasse a
    ser gravado no banco, ele não é servido."""
    destino = (DIRETORIO_FOTOS / caminho_relativo).resolve()
    raiz = DIRETORIO_FOTOS.resolve()
    if not destino.is_relative_to(raiz):
        raise ArquivoRejeitado("Caminho de arquivo fora do diretório permitido.")
    return destino


def validar_imagem(dados: bytes, nome_original: str = "") -> tuple:
    """Confere que os bytes são MESMO uma imagem suportada.

    Devolve (formato, largura, altura, mime). Levanta ArquivoRejeitado com uma
    mensagem legível quando não são — a extensão do arquivo não participa da
    decisão, só da mensagem de erro."""
    if not dados:
        raise ArquivoRejeitado("Arquivo vazio.")
    if len(dados) > TAMANHO_MAX_FOTO:
        limite = TAMANHO_MAX_FOTO // (1024 * 1024)
        raise ArquivoRejeitado(
            f"Arquivo maior que o limite de {limite} MB ({len(dados) // (1024 * 1024)} MB)."
        )

    try:
        with Image.open(io.BytesIO(dados)) as imagem:
            formato = (imagem.format or "").upper()
            largura, altura = imagem.size
            # `verify` pega arquivo truncado; depois dele a imagem não pode
            # mais ser lida, por isso largura/altura saem antes.
            imagem.verify()
    except UnidentifiedImageError:
        extra = ""
        if nome_original.lower().endswith((".heic", ".heif")) and not HEIC_DISPONIVEL:
            extra = (" O suporte a HEIC não está instalado neste servidor "
                     "(pacote pillow-heif).")
        raise ArquivoRejeitado(
            f"'{nome_original or 'arquivo'}' não é uma imagem que este sistema "
            f"consiga abrir.{extra}"
        ) from None
    except Exception as erro:
        raise ArquivoRejeitado(
            f"Não foi possível ler '{nome_original or 'arquivo'}': {erro.__class__.__name__}."
        ) from erro

    if formato not in FORMATOS_ACEITOS:
        raise ArquivoRejeitado(
            f"Formato {formato or 'desconhecido'} não é aceito. "
            "Envie JPG, PNG ou HEIC."
        )
    if largura < 8 or altura < 8:
        raise ArquivoRejeitado("Imagem pequena demais para servir de evidência.")

    return formato, largura, altura, MIME_POR_FORMATO.get(formato, "image/jpeg")


def salvar_foto(comodo_id: str, foto_id: str, dados: bytes, nome_original: str) -> dict:
    """Valida e grava a foto. Devolve os metadados para o banco.

    HEIC é convertido para JPEG na gravação: o navegador não exibe HEIC, e a
    tela de auditoria precisa mostrar a miniatura ao lado da pendência. O
    arquivo original também é guardado, para a foto entregue ao cliente ser a
    que saiu da câmera."""
    formato, largura, altura, mime = validar_imagem(dados, nome_original)
    pasta = _pasta_do_comodo(comodo_id)

    if formato == "HEIF":
        with Image.open(io.BytesIO(dados)) as imagem:
            buffer = io.BytesIO()
            imagem.convert("RGB").save(buffer, "JPEG", quality=90)
        (pasta / f"{foto_id}.heic").write_bytes(dados)
        dados_gravados = buffer.getvalue()
        extensao, mime = ".jpg", "image/jpeg"
    else:
        dados_gravados = dados
        extensao = {"PNG": ".png"}.get(formato, ".jpg")

    nome_arquivo = f"{foto_id}{extensao}"
    (pasta / nome_arquivo).write_bytes(dados_gravados)

    return {
        "caminho": f"{comodo_id[:2]}/{comodo_id}/{nome_arquivo}",
        "mime": mime,
        "bytes_tamanho": len(dados_gravados),
        "largura": largura,
        "altura": altura,
    }


def remover_foto(caminho_relativo: str) -> None:
    """Apaga o arquivo. Só é chamado quando o USUÁRIO remove a foto — escopo
    nunca apaga nada (regra 7)."""
    try:
        destino = caminho_absoluto(caminho_relativo)
    except ArquivoRejeitado:
        return
    for candidato in (destino, destino.with_suffix(".heic")):
        if candidato.is_file():
            candidato.unlink()


def miniatura(caminho_relativo: str, lado: int = 480) -> bytes:
    """Miniatura para a tela de auditoria. Gerada sob demanda — guardar duas
    versões de cada foto dobraria o disco de uma vistoria de 500 fotos."""
    with Image.open(caminho_absoluto(caminho_relativo)) as imagem:
        imagem = imagem.convert("RGB")
        imagem.thumbnail((lado, lado), Image.LANCZOS)
        buffer = io.BytesIO()
        imagem.save(buffer, "JPEG", quality=82)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# ZIP
# --------------------------------------------------------------------------

def _nome_seguro_do_zip(nome: str) -> tuple:
    """(pasta, arquivo) de uma entrada do ZIP, ou (None, None) se for recusada.

    Recusa: caminho absoluto, `..`, letra de unidade do Windows, e entrada de
    diretório. Um ZIP pode conter "../../etc/passwd" — o formato permite, e
    descompactar sem checar é a falha clássica (Zip Slip)."""
    nome = nome.replace("\\", "/")
    if nome.endswith("/"):
        return None, None
    if nome.startswith("/") or ".." in nome.split("/") or ":" in nome:
        return None, None

    partes = [parte for parte in nome.split("/") if parte and parte != "."]
    if not partes:
        return None, None
    arquivo = partes[-1]
    # Metadados do macOS, que vêm em todo ZIP feito no Finder.
    if arquivo.startswith("._") or "__MACOSX" in partes:
        return None, None
    if Path(arquivo).suffix.lower() not in EXTENSOES_ACEITAS:
        return None, None

    # A pasta imediatamente acima do arquivo é o nome do cômodo. Fotos na raiz
    # do ZIP ficam sem cômodo e o chamador decide o que fazer.
    pasta = partes[-2] if len(partes) >= 2 else ""
    return pasta, arquivo


def ler_zip_de_vistoria(dados: bytes) -> dict:
    """Lê um ZIP com uma pasta por cômodo e devolve {comodo: [(nome, bytes)]}.

    Travas contra zip bomb: número de entradas, tamanho declarado de cada uma
    e total descompactado. O tamanho é checado pelo cabeçalho ANTES de
    extrair, e de novo depois — o cabeçalho pode mentir."""
    try:
        arquivo_zip = zipfile.ZipFile(io.BytesIO(dados))
    except zipfile.BadZipFile:
        raise ArquivoRejeitado("Arquivo ZIP inválido ou corrompido.") from None

    entradas = arquivo_zip.infolist()
    if len(entradas) > MAX_ARQUIVOS_ZIP:
        raise ArquivoRejeitado(
            f"ZIP com {len(entradas)} entradas — o limite é {MAX_ARQUIVOS_ZIP}."
        )
    declarado = sum(entrada.file_size for entrada in entradas)
    if declarado > MAX_DESCOMPACTADO_ZIP:
        raise ArquivoRejeitado(
            f"ZIP descompactado passaria de "
            f"{MAX_DESCOMPACTADO_ZIP // (1024 * 1024)} MB."
        )

    por_comodo: dict = {}
    total = 0
    for entrada in entradas:
        pasta, arquivo = _nome_seguro_do_zip(entrada.filename)
        if arquivo is None:
            continue
        if entrada.file_size > TAMANHO_MAX_FOTO:
            continue
        with arquivo_zip.open(entrada) as fluxo:
            conteudo = fluxo.read(TAMANHO_MAX_FOTO + 1)
        if len(conteudo) > TAMANHO_MAX_FOTO:
            continue
        total += len(conteudo)
        if total > MAX_DESCOMPACTADO_ZIP:
            raise ArquivoRejeitado(
                "ZIP maior do que o declarado no cabeçalho — extração interrompida."
            )
        por_comodo.setdefault(pasta or "Sem cômodo", []).append((arquivo, conteudo))

    if not por_comodo:
        raise ArquivoRejeitado(
            "Nenhuma imagem JPG, PNG ou HEIC encontrada no ZIP. Ele precisa ter "
            "uma pasta por cômodo, com as fotos dentro."
        )
    return {comodo: sorted(fotos) for comodo, fotos in sorted(por_comodo.items())}
