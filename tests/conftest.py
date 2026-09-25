"""
Preparação da suíte.

O diretório de dados e o banco são definidos ANTES de qualquer import de
`app.*`, porque app.config lê o ambiente no momento do import. Cada execução
usa uma pasta temporária própria: nenhum teste toca o banco de trabalho.
"""

import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
for caminho in (RAIZ, RAIZ / "backend"):
    if str(caminho) not in sys.path:
        sys.path.insert(0, str(caminho))

_DIRETORIO_TESTE = Path(tempfile.mkdtemp(prefix="laudo-testes-"))
os.environ.setdefault("LAUDO_DIRETORIO_DADOS", str(_DIRETORIO_TESTE))
os.environ.setdefault("LAUDO_BANCO_URL", f"sqlite:///{(_DIRETORIO_TESTE / 'teste.db').as_posix()}")
os.environ.setdefault("LAUDO_ADMIN_EMAIL", "vistoriador@teste.local")
os.environ.setdefault("LAUDO_ADMIN_SENHA", "senha-de-teste-12345")
# Sem chave real: nenhum teste pode alcançar a API do Gemini. Os que precisam
# de resposta do modelo injetam um cliente falso.
os.environ.setdefault("GEMINI_API_KEY", "chave-falsa-de-teste")
