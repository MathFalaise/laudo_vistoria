"""
TELEMETRIA de chamadas a modelo: quanto custou cada cômodo, e com quem.

Cada provedor registra UMA linha por chamada: provedor, modelo, tipo da
chamada, tokens de entrada e saída, duração, tentativas, sucesso/falha e o
custo em US$ quando o preço do modelo é conhecido. É o que permite comparar
Gemini x GLM x GLM+Claude com números, não com impressão.

O que NUNCA entra aqui: prompt, resposta, imagem, chave de API. O contexto
guarda só identificadores (cômodo, foto, vistoria), que já estão no banco e
nas pastas do imóvel.

Uso:

    with telemetria.coletar() as chamadas:
        ...                      # tudo que for chamado aqui é registrado
    chamadas                     # lista de dicts

    with telemetria.contexto(comodo="Cozinha"):
        ...                      # as chamadas levam "comodo" junto

Os coletores são por contexto (contextvars): duas vistorias em threads
diferentes não misturam as contas.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field

logger = logging.getLogger("laudo.telemetria")

_coletores: contextvars.ContextVar = contextvars.ContextVar("laudo_coletores", default=())
_contexto: contextvars.ContextVar = contextvars.ContextVar("laudo_contexto", default={})


@dataclass
class RegistroChamada:
    provedor: str
    modelo: str
    tipo: str
    sucesso: bool
    duracao_s: float
    tentativas: int = 1
    imagens: int = 0
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    tokens_total: int | None = None
    custo_usd: float | None = None
    erro: str = ""                      # só a CLASSE do erro, nunca a mensagem
    contexto: dict = field(default_factory=dict)


def preco_por_milhao(modelo: str) -> tuple | None:
    """(entrada, saída) em US$ por milhão de tokens, ou None se não se sabe.

    A tabela-base fica em core.config.PRECOS_POR_MILHAO, com a fonte e a data
    de cada preço; LAUDO_PRECOS_MODELOS (JSON {"modelo": [entrada, saida]})
    acrescenta ou corrige sem mexer no código — o preço do Claude depende do
    modelo escolhido, e chutar um número seria pior que não ter custo."""
    from core.config import PRECOS_POR_MILHAO

    tabela = dict(PRECOS_POR_MILHAO)
    extra = os.environ.get("LAUDO_PRECOS_MODELOS", "").strip()
    if extra:
        try:
            for nome, valores in json.loads(extra).items():
                tabela[str(nome)] = (float(valores[0]), float(valores[1]))
        except (ValueError, TypeError, IndexError, AttributeError):
            logger.warning("LAUDO_PRECOS_MODELOS inválido — ignorado")
    return tabela.get(modelo)


def calcular_custo(modelo: str, entrada: int | None, saida: int | None) -> float | None:
    preco = preco_por_milhao(modelo)
    if preco is None or entrada is None or saida is None:
        return None
    return round(entrada / 1e6 * preco[0] + saida / 1e6 * preco[1], 6)


def registrar(registro: RegistroChamada) -> None:
    if registro.custo_usd is None:
        registro.custo_usd = calcular_custo(
            registro.modelo, registro.tokens_entrada, registro.tokens_saida)
    registro.contexto = {**_contexto.get(), **registro.contexto}
    linha = asdict(registro)
    for coletor in _coletores.get():
        coletor.append(linha)
    logger.info(
        "chamada provedor=%s modelo=%s tipo=%s sucesso=%s tentativas=%d "
        "tokens=%s/%s duracao=%.1fs",
        registro.provedor, registro.modelo, registro.tipo, registro.sucesso,
        registro.tentativas, registro.tokens_entrada, registro.tokens_saida,
        registro.duracao_s,
    )


@contextmanager
def coletar():
    """Coleta as chamadas feitas dentro do bloco. Coletores aninhados recebem
    todos a mesma linha (o do cômodo e o da vistoria inteira, por exemplo)."""
    lista: list = []
    marca = _coletores.set(_coletores.get() + (lista,))
    try:
        yield lista
    finally:
        _coletores.reset(marca)


@contextmanager
def contexto(**identificadores):
    marca = _contexto.set({**_contexto.get(), **identificadores})
    try:
        yield
    finally:
        _contexto.reset(marca)


def resumir(chamadas: list) -> dict:
    """Totais por provedor/modelo: chamadas, falhas, tokens, tempo e custo.

    `custo_usd` do grupo só é número se TODAS as chamadas tiverem custo; uma
    chamada sem preço deixa o total como None, em vez de um total menor que o
    real parecendo completo."""
    grupos: dict = {}
    for chamada in chamadas:
        chave = f"{chamada['provedor']}:{chamada['modelo']}"
        grupo = grupos.setdefault(chave, {
            "chamadas": 0, "falhas": 0, "tentativas": 0, "imagens": 0,
            "tokens_entrada": 0, "tokens_saida": 0, "duracao_s": 0.0,
            "custo_usd": 0.0, "por_tipo": {},
        })
        grupo["chamadas"] += 1
        grupo["falhas"] += 0 if chamada["sucesso"] else 1
        grupo["tentativas"] += chamada.get("tentativas") or 1
        grupo["imagens"] += chamada.get("imagens") or 0
        grupo["tokens_entrada"] += chamada.get("tokens_entrada") or 0
        grupo["tokens_saida"] += chamada.get("tokens_saida") or 0
        grupo["duracao_s"] = round(grupo["duracao_s"] + chamada["duracao_s"], 2)
        if grupo["custo_usd"] is not None:
            custo = chamada.get("custo_usd")
            grupo["custo_usd"] = None if custo is None else round(grupo["custo_usd"] + custo, 6)
        grupo["por_tipo"][chamada["tipo"]] = grupo["por_tipo"].get(chamada["tipo"], 0) + 1
    return grupos
