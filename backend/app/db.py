"""
Sessão do banco e criação do esquema.

SQLite com `check_same_thread=False` e WAL: o processamento roda numa thread
de trabalho separada da que atende o HTTP, e sem WAL o SQLite serializa
leitura e escrita a ponto de a tela de progresso travar enquanto um cômodo é
gravado.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import BANCO_URL, preparar_diretorios
from app.models import Base

preparar_diretorios()

_e_sqlite = BANCO_URL.startswith("sqlite")

engine = create_engine(
    BANCO_URL,
    connect_args={"check_same_thread": False} if _e_sqlite else {},
    pool_pre_ping=True,
    future=True,
)

if _e_sqlite:

    @event.listens_for(engine, "connect")
    def _ajustar_sqlite(conexao, _):
        cursor = conexao.cursor()
        # WAL: leitor não bloqueia escritor. Sem isso, a tela de progresso
        # trava enquanto um cômodo é gravado.
        cursor.execute("PRAGMA journal_mode=WAL")
        # ON DELETE CASCADE só funciona no SQLite com isto ligado, e todo o
        # grafo Vistoria -> Cômodo -> Foto -> Evidência depende disso.
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


SessaoBanco = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False,
                           class_=Session)


def criar_esquema() -> None:
    """Cria as tabelas que faltarem.

    O Alembic existe para EVOLUIR o esquema (ver backend/alembic); esta função
    cobre a primeira subida, para que instalar não exija rodar migração à mão."""
    Base.metadata.create_all(engine)


def obter_sessao() -> Iterator[Session]:
    """Dependência do FastAPI."""
    sessao = SessaoBanco()
    try:
        yield sessao
    finally:
        sessao.close()
