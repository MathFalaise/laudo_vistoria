"""
Configuração do servidor, toda por variável de ambiente (ver .env.example).

Nada aqui chega ao navegador. A GEMINI_API_KEY em especial é lida só neste
processo: o frontend nunca recebe um endpoint que a devolva, e nenhuma rota a
inclui numa resposta (regra 27 do pedido).
"""

from __future__ import annotations

import os
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parents[2]


def _bool(nome: str, padrao: bool = False) -> bool:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "yes", "sim", "on")


def _int(nome: str, padrao: int) -> int:
    try:
        return int(os.environ.get(nome, padrao))
    except (TypeError, ValueError):
        return padrao


# --- armazenamento -------------------------------------------------------
# Diretório persistente. No Docker é um volume; fora dele, uma pasta ao lado
# do projeto. Tudo que precisa sobreviver a um restart mora aqui: banco,
# fotos e exportações.
DIRETORIO_DADOS = Path(
    os.environ.get("LAUDO_DIRETORIO_DADOS", RAIZ_PROJETO / "dados")
).resolve()
DIRETORIO_FOTOS = DIRETORIO_DADOS / "fotos"
DIRETORIO_EXPORTACOES = DIRETORIO_DADOS / "exportacoes"

BANCO_URL = os.environ.get(
    "LAUDO_BANCO_URL", f"sqlite:///{(DIRETORIO_DADOS / 'laudo.db').as_posix()}"
)

# --- acesso --------------------------------------------------------------
NOME_COOKIE_SESSAO = "laudo_sessao"
DURACAO_SESSAO_HORAS = _int("LAUDO_SESSAO_HORAS", 12)
# Em produção com HTTPS isto tem que ser True (ver docs/producao.md).
COOKIE_SEGURO = _bool("LAUDO_COOKIE_SEGURO", False)

# Usuário criado na primeira subida, se não houver nenhum. Sem isso não há
# como entrar na aplicação recém-instalada.
ADMIN_EMAIL = os.environ.get("LAUDO_ADMIN_EMAIL", "")
ADMIN_SENHA = os.environ.get("LAUDO_ADMIN_SENHA", "")

# --- upload --------------------------------------------------------------
# Limites: um celular moderno faz foto de 3-6 MB; 25 MB cobre HEIC de 48 MP
# com folga e ainda barra alguém subindo um vídeo com extensão trocada.
TAMANHO_MAX_FOTO_MB = _int("LAUDO_MAX_FOTO_MB", 25)
TAMANHO_MAX_FOTO = TAMANHO_MAX_FOTO_MB * 1024 * 1024
TAMANHO_MAX_ZIP_MB = _int("LAUDO_MAX_ZIP_MB", 500)
TAMANHO_MAX_ZIP = TAMANHO_MAX_ZIP_MB * 1024 * 1024
# Proteção contra zip bomb: total descompactado e número de arquivos.
MAX_ARQUIVOS_ZIP = _int("LAUDO_MAX_ARQUIVOS_ZIP", 3000)
MAX_DESCOMPACTADO_ZIP = _int("LAUDO_MAX_DESCOMPACTADO_MB", 2000) * 1024 * 1024

# --- CORS ----------------------------------------------------------------
# Em desenvolvimento o Vite serve em 5173 e a API em 8000; em produção o
# mesmo contêiner serve os dois e a lista fica vazia.
ORIGENS_PERMITIDAS = [
    origem.strip()
    for origem in os.environ.get(
        "LAUDO_ORIGENS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origem.strip()
]

# Pasta com o build do frontend, servida pela própria API em produção.
DIRETORIO_FRONTEND = Path(
    os.environ.get("LAUDO_FRONTEND_DIST", RAIZ_PROJETO / "frontend" / "dist")
)

# Quantos cômodos são processados em paralelo. Um de cada vez, de propósito:
# o gargalo é a API do Gemini, e paralelismo agressivo troca cota estourada
# (429, que não tem retry automático) por pouco ganho de tempo.
TRABALHADORES_JOB = _int("LAUDO_TRABALHADORES", 1)


def preparar_diretorios() -> None:
    for diretorio in (DIRETORIO_DADOS, DIRETORIO_FOTOS, DIRETORIO_EXPORTACOES):
        diretorio.mkdir(parents=True, exist_ok=True)
