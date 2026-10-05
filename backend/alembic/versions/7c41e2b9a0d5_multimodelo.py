"""multimodelo: validação visual por evidência e telemetria de chamadas

Revision ID: 7c41e2b9a0d5
Revises: d3a8fff07aa6
Create Date: 2026-10-05 19:00:00

Só cria tabelas novas — nenhuma coluna muda nas existentes e nenhum dado é
apagado. O downgrade remove apenas as duas tabelas desta revisão.
"""
from alembic import op
import sqlalchemy as sa


revision = '7c41e2b9a0d5'
down_revision = 'd3a8fff07aa6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('validacao_evidencia',
    sa.Column('evidencia_id', sa.String(length=32), nullable=False),
    sa.Column('origem', sa.String(length=160), nullable=False),
    sa.Column('revisao', sa.Integer(), nullable=False),
    sa.Column('observacao_original', sa.Text(), nullable=False),
    sa.Column('decisao', sa.String(length=30), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=False),
    sa.Column('validador', sa.String(length=160), nullable=False),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['evidencia_id'], ['evidencia.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('validacao_evidencia', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_validacao_evidencia_evidencia_id'), ['evidencia_id'], unique=True)

    op.create_table('chamada_modelo',
    sa.Column('vistoria_id', sa.String(length=32), nullable=False),
    sa.Column('comodo_id', sa.String(length=32), nullable=True),
    sa.Column('job_id', sa.String(length=32), nullable=True),
    sa.Column('foto_id', sa.String(length=32), nullable=True),
    sa.Column('provedor', sa.String(length=40), nullable=False),
    sa.Column('modelo', sa.String(length=120), nullable=False),
    sa.Column('tipo', sa.String(length=40), nullable=False),
    sa.Column('sucesso', sa.Boolean(), nullable=False),
    sa.Column('erro', sa.String(length=120), nullable=False),
    sa.Column('duracao_s', sa.Float(), nullable=False),
    sa.Column('tentativas', sa.Integer(), nullable=False),
    sa.Column('imagens', sa.Integer(), nullable=False),
    sa.Column('tokens_entrada', sa.Integer(), nullable=True),
    sa.Column('tokens_saida', sa.Integer(), nullable=True),
    sa.Column('tokens_total', sa.Integer(), nullable=True),
    sa.Column('custo_usd', sa.Float(), nullable=True),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['comodo_id'], ['comodo.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['vistoria_id'], ['vistoria.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chamada_modelo', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chamada_modelo_comodo_id'), ['comodo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chamada_modelo_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chamada_modelo_vistoria_id'), ['vistoria_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('chamada_modelo', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chamada_modelo_vistoria_id'))
        batch_op.drop_index(batch_op.f('ix_chamada_modelo_job_id'))
        batch_op.drop_index(batch_op.f('ix_chamada_modelo_comodo_id'))
    op.drop_table('chamada_modelo')

    with op.batch_alter_table('validacao_evidencia', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_validacao_evidencia_evidencia_id'))
    op.drop_table('validacao_evidencia')
