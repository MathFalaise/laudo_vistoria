"""
Entidades do banco.

O grafo que dá rastreabilidade completa, e que é a razão de existir desta
camada (regra 32 do pedido):

    Foto -> Evidencia -> ItemLaudo -> Pendencia

Cada seta é uma pergunta que o sistema antigo não sabia responder:

- "de qual foto saiu esta frase do laudo?" (ItemLaudo <- Evidencia <- Foto)
- "por que esta evidência não virou texto?" (Evidencia.motivo_descarte)
- "esta pendência ainda é a mesma depois que o texto mudou?" (Pendencia
  aponta para ItemLaudo.id, não para o texto — regra 17)

Os nomes são em português porque o resto do projeto é, e o vistoriador lê
este código. O paralelo com os nomes do pedido está em cada docstring.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def agora() -> datetime:
    return datetime.now(timezone.utc)


def novo_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class _ComId:
    """Id textual estável (UUID hex).

    Textual e não autoincremento de propósito: o id de um ItemLaudo viaja para
    o arquivo de pendências e para a tela de auditoria, e precisa continuar
    válido depois de exportar, reimportar e reprocessar."""

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=novo_id)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


# --------------------------------------------------------------------------
# Acesso
# --------------------------------------------------------------------------

class Usuario(Base, _ComId):
    """Regra 27: começa com um único usuário administrativo. Sem multi-tenant."""

    __tablename__ = "usuario"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(200), default="")
    # scrypt da biblioteca padrão — sem dependência externa de hashing.
    senha_hash: Mapped[str] = mapped_column(String(255))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    sessoes: Mapped[list["Sessao"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )


class Sessao(Base, _ComId):
    """Sessão guardada no banco, não assinada no cookie.

    Assim ela é REVOGÁVEL: trocar a senha, sair, ou desativar o usuário mata
    a sessão de verdade. Um cookie assinado continuaria valendo até expirar."""

    __tablename__ = "sessao"

    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    # Guardamos o HASH do token, não o token: um vazamento do banco não
    # entrega sessões ativas.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ultimo_uso: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    usuario: Mapped["Usuario"] = relationship(back_populates="sessoes")


# --------------------------------------------------------------------------
# Vistoria
# --------------------------------------------------------------------------

class Vistoria(Base, _ComId):
    """Inspection. Uma vistoria de um imóvel."""

    __tablename__ = "vistoria"

    titulo: Mapped[str] = mapped_column(String(300))
    endereco: Mapped[str] = mapped_column(String(400), default="")
    # As "notas" que hoje vão em --notas: informação confirmada do imóvel.
    notas: Mapped[str] = mapped_column(Text, default="")
    data_vistoria: Mapped[str] = mapped_column(String(20), default="")
    arquivada: Mapped[bool] = mapped_column(Boolean, default=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora
    )

    comodos: Mapped[list["Comodo"]] = relationship(
        back_populates="vistoria", cascade="all, delete-orphan",
        order_by="Comodo.ordem",
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="vistoria", cascade="all, delete-orphan"
    )


class EstadoComodo:
    PENDENTE = "pendente"
    PROCESSANDO = "processando"
    CONCLUIDO = "concluido"
    FALHOU = "falhou"


class Comodo(Base, _ComId):
    """Room. O estado aqui é o que permite retomar (regra 26): reiniciar a
    aplicação não reprocessa o que já terminou."""

    __tablename__ = "comodo"
    __table_args__ = (UniqueConstraint("vistoria_id", "nome", name="uq_comodo_nome"),)

    vistoria_id: Mapped[str] = mapped_column(ForeignKey("vistoria.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoComodo.PENDENTE)
    erro: Mapped[str] = mapped_column(Text, default="")
    processado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Espelho do que a validação de escopo concluiu, para a tela não ter que
    # recalcular: quantas fotos serviram, e se o cômodo ficou mal coberto.
    fotos_utilizaveis: Mapped[int] = mapped_column(Integer, default=0)
    cobertura_incompleta: Mapped[bool] = mapped_column(Boolean, default=False)

    vistoria: Mapped["Vistoria"] = relationship(back_populates="comodos")
    fotos: Mapped[list["Foto"]] = relationship(
        back_populates="comodo", cascade="all, delete-orphan", order_by="Foto.ordem"
    )
    itens: Mapped[list["ItemLaudo"]] = relationship(
        back_populates="comodo", cascade="all, delete-orphan", order_by="ItemLaudo.ordem"
    )
    evidencias: Mapped[list["Evidencia"]] = relationship(
        back_populates="comodo", cascade="all, delete-orphan"
    )


class Foto(Base, _ComId):
    """Photo. NUNCA é apagada por causa de escopo (regra 7) — o que muda é
    `escopo`, que controla se ela pode alimentar o laudo."""

    __tablename__ = "foto"

    comodo_id: Mapped[str] = mapped_column(ForeignKey("comodo.id", ondelete="CASCADE"), index=True)
    nome_original: Mapped[str] = mapped_column(String(300))
    # Caminho RELATIVO ao diretório de armazenamento. Nunca absoluto: o
    # diretório muda entre a máquina de desenvolvimento e o contêiner, e
    # caminho absoluto no banco é como se monta um path traversal.
    caminho: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str] = mapped_column(String(100), default="image/jpeg")
    bytes_tamanho: Mapped[int] = mapped_column(Integer, default=0)
    largura: Mapped[int] = mapped_column(Integer, default=0)
    altura: Mapped[int] = mapped_column(Integer, default=0)
    ordem: Mapped[int] = mapped_column(Integer, default=0)

    # Resultado da análise de escopo (core.evidencias.AnaliseFoto).
    escopo: Mapped[str] = mapped_column(String(20), default="")
    relevancia: Mapped[int] = mapped_column(Integer, default=0)
    ambiente_adjacente: Mapped[bool] = mapped_column(Boolean, default=False)
    reflexo: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_escopo: Mapped[str] = mapped_column(Text, default="")

    comodo: Mapped["Comodo"] = relationship(back_populates="fotos")
    evidencias: Mapped[list["Evidencia"]] = relationship(
        back_populates="foto", cascade="all, delete-orphan"
    )


class Evidencia(Base, _ComId):
    """Evidence. O elo que faltava entre a foto e a frase do laudo.

    As duas confianças ficam separadas no banco, não só no cálculo: a tela de
    auditoria precisa poder mostrar "o modelo viu isso com 98% de clareza e
    só 20% de certeza de que é deste cômodo" — é essa frase que explica ao
    vistoriador por que o item não entrou."""

    __tablename__ = "evidencia"

    comodo_id: Mapped[str] = mapped_column(ForeignKey("comodo.id", ondelete="CASCADE"), index=True)
    foto_id: Mapped[str] = mapped_column(ForeignKey("foto.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("item_laudo.id", ondelete="SET NULL"), nullable=True, index=True
    )

    categoria: Mapped[str] = mapped_column(String(20))
    observacao: Mapped[str] = mapped_column(Text)
    confianca_percepcao: Mapped[int] = mapped_column(Integer, default=0)
    confianca_escopo: Mapped[int] = mapped_column(Integer, default=0)
    confianca_final: Mapped[int] = mapped_column(Integer, default=0)
    e_reflexo: Mapped[bool] = mapped_column(Boolean, default=False)
    e_ambiente_adjacente: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="aceita")
    motivo_descarte: Mapped[str] = mapped_column(String(40), default="")
    detalhe_descarte: Mapped[str] = mapped_column(Text, default="")

    # Região aproximada na foto (0..1). Fica NULA quando o modelo não soube
    # dizer — região errada é pior que região nenhuma (regra 9).
    regiao_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    regiao_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    regiao_largura: Mapped[float | None] = mapped_column(Float, nullable=True)
    regiao_altura: Mapped[float | None] = mapped_column(Float, nullable=True)

    comodo: Mapped["Comodo"] = relationship(back_populates="evidencias")
    foto: Mapped["Foto"] = relationship(back_populates="evidencias")
    item: Mapped["ItemLaudo | None"] = relationship(back_populates="evidencias")

    @property
    def regiao(self) -> dict | None:
        if self.regiao_x is None:
            return None
        return {"x": self.regiao_x, "y": self.regiao_y,
                "largura": self.regiao_largura, "altura": self.regiao_altura}


class ItemLaudo(Base, _ComId):
    """ReportItem. UMA linha do laudo, com id estável.

    O texto pode mudar (o vistoriador corrige, o revisar.py repadroniza) sem
    que a pendência se perca — era esse o problema do arquivo .txt, em que a
    pendência era localizada procurando o texto exato dentro do laudo."""

    __tablename__ = "item_laudo"

    comodo_id: Mapped[str] = mapped_column(ForeignKey("comodo.id", ondelete="CASCADE"), index=True)
    categoria: Mapped[str] = mapped_column(String(20), index=True)
    texto: Mapped[str] = mapped_column(Text)
    certeza: Mapped[int] = mapped_column(Integer, default=100)
    motivo: Mapped[str] = mapped_column(Text, default="")
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    removido: Mapped[bool] = mapped_column(Boolean, default=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora
    )

    comodo: Mapped["Comodo"] = relationship(back_populates="itens")
    evidencias: Mapped[list["Evidencia"]] = relationship(back_populates="item")
    pendencias: Mapped[list["Pendencia"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    historico: Mapped[list["HistoricoItem"]] = relationship(
        back_populates="item", cascade="all, delete-orphan",
        order_by="HistoricoItem.criado_em",
    )


class TipoPendencia:
    CERTEZA = "certeza"                  # item de certeza baixa (motor antigo)
    FALTA = "falta"                      # a conferência viu e o laudo não tem
    REPETIDO = "repetido"                # "Mais um/uma" que sobrou
    CONFLITO_ESCOPO = "scope_conflict"   # regra 19


class Pendencia(Base, _ComId):
    """ValidationItem. Aponta para o ItemLaudo por ID (regra 17).

    `texto_proposto` guarda o que o sistema sugere, sem tocar no laudo:
    nada entra sozinho, nem vindo da conferência (regra 18)."""

    __tablename__ = "pendencia"

    comodo_id: Mapped[str] = mapped_column(ForeignKey("comodo.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("item_laudo.id", ondelete="CASCADE"), nullable=True, index=True
    )
    categoria: Mapped[str] = mapped_column(String(20))
    tipo: Mapped[str] = mapped_column(String(30), default=TipoPendencia.CERTEZA)
    motivo: Mapped[str] = mapped_column(Text, default="")
    certeza: Mapped[int] = mapped_column(Integer, default=0)
    texto_proposto: Mapped[str] = mapped_column(Text, default="")

    # Preenchidos na decisão humana.
    decisao: Mapped[str] = mapped_column(String(20), default="")   # OK/CORRIGIR/REMOVER
    correcao: Mapped[str] = mapped_column(Text, default="")
    regra_sugerida: Mapped[str] = mapped_column(Text, default="")
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolvida_por_id: Mapped[str | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True
    )

    item: Mapped["ItemLaudo | None"] = relationship(back_populates="pendencias")
    # As evidências que motivaram a pendência, para a tela mostrar a foto.
    evidencia_ids: Mapped[str] = mapped_column(Text, default="")   # ids separados por vírgula

    @property
    def evidencias_relacionadas(self) -> list:
        return [e for e in self.evidencia_ids.split(",") if e]


class HistoricoItem(Base, _ComId):
    """Regra 41: dá para saber o texto anterior, o atual, quando mudou, quem
    mudou e qual pendência causou. Sem auditoria empresarial — só o rastro."""

    __tablename__ = "historico_item"

    item_id: Mapped[str] = mapped_column(ForeignKey("item_laudo.id", ondelete="CASCADE"), index=True)
    texto_anterior: Mapped[str] = mapped_column(Text, default="")
    texto_novo: Mapped[str] = mapped_column(Text, default="")
    origem: Mapped[str] = mapped_column(String(40), default="")     # ia, humano, conferencia
    pendencia_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    usuario_id: Mapped[str | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True
    )
    # Ids das evidências que sustentavam o item no momento da mudança.
    evidencia_ids: Mapped[str] = mapped_column(Text, default="")

    item: Mapped["ItemLaudo"] = relationship(back_populates="historico")


class CorrecaoHumana(Base, _ComId):
    """Regra 21: coleta ESTRUTURADA das correções, para análise futura.

    Regra 22, logo em seguida: isto NÃO treina nada sozinho. É dado guardado.
    Uma regra só passa a valer quando o vistoriador a adota explicitamente."""

    __tablename__ = "correcao_humana"

    vistoria_id: Mapped[str] = mapped_column(ForeignKey("vistoria.id", ondelete="CASCADE"), index=True)
    pendencia_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    item_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # AMBIENTE_ADJACENTE, REFLEXO, QUANTIDADE, MATERIAL, COR, DEFEITO, ...
    tipo: Mapped[str] = mapped_column(String(40))
    acao: Mapped[str] = mapped_column(String(40))          # IGNORADA, CORRIGIDA, ACEITA
    razao: Mapped[str] = mapped_column(Text, default="")
    usuario_id: Mapped[str | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True
    )


class Regra(Base, _ComId):
    """Rule. Regra geral de redação.

    Regra 23: em produção as regras novas vivem AQUI, não no repositório. O
    regras_validadas.txt continua sendo o conjunto inicial, carregado na
    primeira subida. `ativa` só vira True por adoção explícita."""

    __tablename__ = "regra"

    texto: Mapped[str] = mapped_column(Text, unique=True)
    ativa: Mapped[bool] = mapped_column(Boolean, default=False)
    origem: Mapped[str] = mapped_column(String(40), default="manual")
    # De qual vistoria/pendência ela nasceu — só para auditoria. Uma regra
    # NÃO herda o contexto do imóvel: o texto tem que ser geral.
    vistoria_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    adotada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EstadoJob:
    PENDENTE = "pending"
    PROCESSANDO = "processing"
    CONCLUIDO = "completed"
    FALHOU = "failed"
    CANCELADO = "cancelled"

    TERMINAIS = (CONCLUIDO, FALHOU, CANCELADO)


class Job(Base, _ComId):
    """Regra 26: a requisição HTTP não fica aberta durante a geração.

    Um job que estava PROCESSANDO quando o servidor caiu é marcado como
    FALHOU na subida seguinte (ver jobs.recuperar_jobs_orfaos) — mas os
    cômodos que já tinham terminado continuam CONCLUIDO e não são refeitos."""

    __tablename__ = "job"

    vistoria_id: Mapped[str] = mapped_column(ForeignKey("vistoria.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))       # laudo, conferencia, revisao
    estado: Mapped[str] = mapped_column(String(20), default=EstadoJob.PENDENTE)
    total: Mapped[int] = mapped_column(Integer, default=0)
    concluidos: Mapped[int] = mapped_column(Integer, default=0)
    mensagem: Mapped[str] = mapped_column(Text, default="")
    erro: Mapped[str] = mapped_column(Text, default="")
    comodos: Mapped[str] = mapped_column(Text, default="")     # nomes separados por vírgula
    usar_evidencias: Mapped[bool] = mapped_column(Boolean, default=True)
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelamento_pedido: Mapped[bool] = mapped_column(Boolean, default=False)

    vistoria: Mapped["Vistoria"] = relationship(back_populates="jobs")
