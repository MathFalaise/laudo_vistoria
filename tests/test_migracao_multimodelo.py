"""
Migração Alembic da camada multimodelo (backend/alembic/versions/7c41e2b9a0d5).

Roda o Alembic de verdade num SQLite temporário: upgrade, `check` (as
migrações batem com os modelos), downgrade (só as duas tabelas novas saem) e
upgrade de novo. E o caminho de quem NÃO roda a migração: um banco no esquema
antigo ganha as tabelas novas no create_all da subida, sem perder dado.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

RAIZ = Path(__file__).resolve().parents[1]
NOVAS = {"validacao_evidencia", "chamada_modelo"}


def _alembic(banco: Path, *argumentos) -> subprocess.CompletedProcess:
    ambiente = {**os.environ, "LAUDO_BANCO_URL": f"sqlite:///{banco.as_posix()}",
                "PYTHONPATH": os.pathsep.join([str(RAIZ), str(RAIZ / "backend")])}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(RAIZ / "backend" / "alembic.ini"), *argumentos],
        cwd=RAIZ, env=ambiente, capture_output=True, text=True, timeout=120,
    )


def _tabelas(banco: Path) -> set:
    with sqlite3.connect(banco) as conexao:
        return {nome for (nome,) in conexao.execute("select name from sqlite_master where type='table'")}


def test_upgrade_check_downgrade_upgrade(tmp_path):
    banco = tmp_path / "laudo.db"
    assert _alembic(banco, "upgrade", "head").returncode == 0
    assert NOVAS <= _tabelas(banco)

    verificacao = _alembic(banco, "check")
    assert verificacao.returncode == 0, verificacao.stdout + verificacao.stderr

    assert _alembic(banco, "downgrade", "-1").returncode == 0
    restantes = _tabelas(banco)
    assert not (NOVAS & restantes) and {"evidencia", "vistoria", "pendencia"} <= restantes

    assert _alembic(banco, "upgrade", "head").returncode == 0
    assert NOVAS <= _tabelas(banco)


def test_banco_antigo_ganha_as_tabelas_na_subida_sem_perder_dado(tmp_path):
    banco = tmp_path / "antigo.db"
    assert _alembic(banco, "upgrade", "d3a8fff07aa6").returncode == 0      # esquema anterior
    with sqlite3.connect(banco) as conexao:
        conexao.execute(
            "insert into regra (id, criado_em, texto, ativa, origem) "
            "values ('r1', '2026-09-01 00:00:00', 'regra antiga', 1, 'manual')")
    assert not (NOVAS & _tabelas(banco))

    from app.models import Base
    Base.metadata.create_all(create_engine(f"sqlite:///{banco.as_posix()}"))   # = db.criar_esquema

    assert NOVAS <= _tabelas(banco)
    with sqlite3.connect(banco) as conexao:
        assert conexao.execute("select texto from regra").fetchall() == [("regra antiga",)]


@pytest.mark.parametrize("tabela", sorted(NOVAS))
def test_tabelas_novas_nao_guardam_conteudo_de_modelo(tabela):
    """Nenhuma coluna de prompt, resposta ou imagem — só identificadores e números."""
    from app.models import Base
    colunas = set(Base.metadata.tables[tabela].columns.keys())
    assert not colunas & {"prompt", "resposta", "imagem", "conteudo", "chave"}
