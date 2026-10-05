"""Ambiente do Alembic.

A URL do banco vem do MESMO lugar que a aplicação usa (app.config), para não
existir a chance de a migração rodar num banco e o servidor em outro.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import BANCO_URL
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", BANCO_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=BANCO_URL, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # O SQLite não sabe ALTER COLUMN: sem isto, qualquer alteração de
        # coluna falha em vez de virar a recriação de tabela.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conexao = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with conexao.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata,
                          render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
