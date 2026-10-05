"""
VALIDAÇÃO VISUAL SELETIVA — o auditor que olha a foto de novo.

Onde entra, no grafo da V2 (core/pipeline.processar_comodo_v2):

    FOTOS
      -> ANÁLISE (analista: VISION_PROVIDER)          evidências cruas
      -> ESCOPO (código: validar_escopo)               aceita / descarta / conflito
      -> BUSCA DIRIGIDA (analista, se a cobertura pede)
      -> POLÍTICA (código: selecionar)                 quem vai ao validador
      -> VALIDAÇÃO (validador: VALIDATOR_PROVIDER)     1 chamada por foto, com a foto
      -> REANÁLISE (analista, se o validador pede)     só aquele ponto, máx. 1
      -> VALIDAÇÃO de novo (só das reanalisadas)
      -> ESCOPO de novo (código)                       o veto vira descarte + pendência
      -> COBERTURA -> CONSOLIDAÇÃO -> LAUDO            como sempre

Hierarquia (pedido do vistoriador, 05/10/2026): fatos confirmados em campo
(--notas) > regras do código > evidência validada > analista > validador >
texto. Por isso:

- o validador só recebe o que o CÓDIGO aceitou, e só pode TIRAR (vetar) ou
  CORRIGIR a descrição do mesmo objeto — nunca devolver ao laudo o que o
  código descartou (reflexo continua reflexo), nunca acrescentar objeto;
- o veto é aplicado por `validar_escopo`, depois de todas as regras;
- conflito entre fotos (atributo) NÃO vai ao validador: não é votação; os
  dois lados continuam indo ao vistoriador;
- resposta fora do formato não é interpretada: a evidência fica num estado
  seguro, conforme VALIDATION_FAILURE_POLICY;
- falha do validador nunca vira aprovação.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field

from core import telemetria
from core.config import (CATEGORIAS, LIMIAR_VALIDACAO, MAX_EVIDENCIAS_VALIDADAS_POR_COMODO,
                         MAX_REANALISES)
from core.evidencias import StatusEvidencia
from core.providers import como_provedor
from core.providers.esquema import esquema

DECISOES = ("approved", "rejected", "corrected", "needs_reanalysis")

# Evidência achada pela busca DIRIGIDA (id "d1:foto#3"): o modelo foi
# mandado procurar aquilo, que é quando ele mais tende a "achar". Sempre vai
# ao validador.
_DA_BUSCA_DIRIGIDA = re.compile(r"^d\d+:")


@dataclass
class PoliticaValidacao:
    """O que vai ao validador e o que fazer com cada resposta. Os números
    vêm de core/config.py; o ambiente só escolhe entre comportamentos."""

    modo: str = "selective"               # selective | all
    limiar: int = LIMIAR_VALIDACAO
    max_por_comodo: int = MAX_EVIDENCIAS_VALIDADAS_POR_COMODO
    max_reanalises: int = MAX_REANALISES
    falha: str = "pendencia"              # pendencia | manter
    corrigida: str = "aplicar"            # aplicar | conflito


def politica_do_ambiente() -> PoliticaValidacao:
    def escolha(nome, opcoes, padrao):
        valor = os.environ.get(nome, "").strip().lower() or padrao
        if valor not in opcoes:
            raise ValueError(f"{nome}={valor!r}: use um de {opcoes}")
        return valor

    try:
        reanalises = int(os.environ.get("MAX_REANALISES", MAX_REANALISES))
    except ValueError as erro:
        raise ValueError("MAX_REANALISES precisa ser um número inteiro") from erro
    return PoliticaValidacao(
        modo=escolha("VALIDATION_POLICY", ("selective", "all"), "selective"),
        max_reanalises=max(0, min(reanalises, MAX_REANALISES)),
        falha=escolha("VALIDATION_FAILURE_POLICY", ("pendencia", "manter"), "pendencia"),
        corrigida=escolha("VALIDATION_CORRECTED_POLICY", ("aplicar", "conflito"), "aplicar"),
    )


@dataclass
class RelatorioValidacao:
    selecionadas: int = 0
    excedentes: int = 0
    chamadas_validador: int = 0
    chamadas_reanalise: int = 0
    aprovadas: int = 0
    rejeitadas: int = 0
    corrigidas: int = 0
    reanalisadas: int = 0
    nao_resolvidas: int = 0
    falhas: int = 0
    motivos_selecao: dict = field(default_factory=dict)

    @property
    def alterou(self) -> bool:
        return bool(self.rejeitadas or self.corrigidas or self.reanalisadas
                    or self.nao_resolvidas or self.falhas)

    def para_dict(self) -> dict:
        return {**asdict(self), "alterou": self.alterou}


# --------------------------------------------------------------------------
# Nó POLÍTICA
# --------------------------------------------------------------------------

def motivo_de_selecao(evidencia, politica: PoliticaValidacao) -> str:
    """Por que esta evidência vai ao validador ("" = não vai). Critérios no
    código, não no prompt."""
    if politica.modo == "all":
        return "politica_all"
    if _DA_BUSCA_DIRIGIDA.match(evidencia.id):
        return "busca_dirigida"
    if evidencia.escopo_original is not None:
        return "fronteira_promovida"
    if evidencia.atributos.get("defeito") or evidencia.categoria == "obs":
        return "defeito_ou_observacao"
    if evidencia.confianca_final < politica.limiar:
        return "confianca_baixa"
    return ""


def selecionar(aceitas: list, politica: PoliticaValidacao) -> tuple:
    """(selecionadas, excedentes, motivos). Só evidência ACEITA pelo código e
    fora de conflito: conflito de atributo é do vistoriador, e o que o código
    descartou não tem volta. Passando do teto, vão as de menor confiança."""
    candidatas = []
    for evidencia in aceitas:
        if evidencia.status is not StatusEvidencia.ACEITA or evidencia.validacao:
            continue
        motivo = motivo_de_selecao(evidencia, politica)
        if motivo:
            candidatas.append((evidencia, motivo))
    candidatas.sort(key=lambda par: (par[0].confianca_final, par[0].id))
    escolhidas = candidatas[:politica.max_por_comodo]
    excedentes = [evidencia for evidencia, _ in candidatas[politica.max_por_comodo:]]
    motivos: dict = {}
    for _, motivo in escolhidas:
        motivos[motivo] = motivos.get(motivo, 0) + 1
    return [evidencia for evidencia, _ in escolhidas], excedentes, motivos


# --------------------------------------------------------------------------
# Schemas das respostas (o código valida de novo: schema é pedido, não garantia)
# --------------------------------------------------------------------------

def _esquema_atributos() -> dict:
    return esquema(type="OBJECT", properties={
        chave: esquema(type="STRING")
        for chave in ("material", "cor", "acabamento", "rejunte_material",
                      "rejunte_cor", "tipo", "estado", "defeito")
    })


def esquema_decisoes(ids: list) -> dict:
    decisao = esquema(
        type="OBJECT",
        properties={
            "evidence_id": esquema(type="STRING", enum=list(ids)),
            "decision": esquema(type="STRING", enum=list(DECISOES)),
            "reason": esquema(type="STRING"),
            "corrections": esquema(type="OBJECT", properties={
                "observacao": esquema(type="STRING"), "atributos": _esquema_atributos()}),
            "focus": esquema(type="STRING"),
        },
        required=["evidence_id", "decision", "reason"],
        property_ordering=["evidence_id", "decision", "reason", "corrections", "focus"],
    )
    return esquema(type="OBJECT",
                   properties={"decisoes": esquema(type="ARRAY", items=decisao, min_items=1)},
                   required=["decisoes"])


def esquema_reanalises(ids: list) -> dict:
    from core.gemini_client import _VALORES_DE_ESCOPO

    evidencia = esquema(
        type="OBJECT",
        properties={
            "categoria": esquema(type="STRING", enum=list(CATEGORIAS)),
            "observacao": esquema(type="STRING"),
            "escopo": esquema(type="STRING", enum=list(_VALORES_DE_ESCOPO)),
            "confianca_percepcao": esquema(type="INTEGER", minimum=0, maximum=100),
            "confianca_escopo": esquema(type="INTEGER", minimum=0, maximum=100),
            "atributos": _esquema_atributos(),
        },
        required=["categoria", "observacao", "escopo", "confianca_percepcao", "confianca_escopo"],
        property_ordering=["categoria", "observacao", "escopo", "confianca_percepcao",
                           "confianca_escopo", "atributos"],
    )
    item = esquema(
        type="OBJECT",
        properties={"evidence_id": esquema(type="STRING", enum=list(ids)),
                    "encontrado": esquema(type="BOOLEAN"), "evidencia": evidencia},
        required=["evidence_id", "encontrado"],
        property_ordering=["evidence_id", "encontrado", "evidencia"],
    )
    return esquema(type="OBJECT",
                   properties={"reanalises": esquema(type="ARRAY", items=item, min_items=1)},
                   required=["reanalises"])


class RespostaInvalida(ValueError):
    """A resposta do modelo não está no formato exigido. Não se interpreta."""


def _ler_lista(texto: str, chave: str) -> list:
    from core.gemini_client import _extrair_json

    try:
        dados = _extrair_json(texto)
    except (ValueError, TypeError) as erro:
        raise RespostaInvalida(f"JSON inválido: {erro.__class__.__name__}") from erro
    lista = dados.get(chave) if isinstance(dados, dict) else None
    if not isinstance(lista, list):
        raise RespostaInvalida(f'falta a lista "{chave}"')
    return lista


def interpretar_decisoes(texto: str, ids: list) -> dict:
    """{id: decisão validada} — só o que está no formato. Id repetido,
    decisão fora do enum, correção sem observação e reanálise sem foco ficam
    de fora (viram falha daquela evidência, não palpite)."""
    validas, vistos, repetidos = {}, set(), set()
    for item in _ler_lista(texto, "decisoes"):
        if not isinstance(item, dict):
            continue
        evidencia_id, decisao = item.get("evidence_id"), item.get("decision")
        if evidencia_id not in ids:
            continue
        if evidencia_id in vistos:
            repetidos.add(evidencia_id)
            continue
        vistos.add(evidencia_id)
        if decisao not in DECISOES:
            continue
        motivo = " ".join(str(item.get("reason") or "").split())
        correcoes = item.get("corrections") if isinstance(item.get("corrections"), dict) else {}
        foco = " ".join(str(item.get("focus") or "").split())
        if decisao == "corrected" and not str(correcoes.get("observacao") or "").strip():
            continue
        if decisao == "needs_reanalysis" and not foco:
            continue
        validas[evidencia_id] = {"decision": decisao, "reason": motivo,
                                 "corrections": correcoes, "focus": foco}
    for evidencia_id in repetidos:
        validas.pop(evidencia_id, None)
    return validas


# --------------------------------------------------------------------------
# Nós VALIDAÇÃO e REANÁLISE
# --------------------------------------------------------------------------

def _rotulo(provedor) -> str:
    return f"{provedor.nome}:{provedor.modelo}"


def _por_foto(evidencias: list) -> dict:
    grupos: dict = {}
    for evidencia in evidencias:
        grupos.setdefault(evidencia.foto_id, []).append(evidencia)
    return grupos


def _marcar_falha(evidencia, politica, motivo: str, por: str) -> None:
    if politica.falha == "pendencia":
        evidencia.validacao = "falha"
        evidencia.validacao_motivo = (
            f"a validação visual não pôde ser concluída ({motivo}) — o item não entra "
            "no laudo sem conferência")
    else:
        evidencia.validacao = "falha_mantida"
        evidencia.validacao_motivo = f"a validação visual falhou ({motivo}); mantida pela política"
    evidencia.validacao_por = por


def _aplicar_decisao(evidencia, decisao: dict, politica, por: str, fila: list,
                     relatorio: RelatorioValidacao) -> None:
    tipo, motivo = decisao["decision"], decisao["reason"] or "(sem motivo)"
    evidencia.validacao_por = por
    if tipo == "approved":
        evidencia.validacao, evidencia.validacao_motivo = "aprovada", motivo
        relatorio.aprovadas += 1
    elif tipo == "rejected":
        evidencia.validacao = "rejeitada"
        evidencia.validacao_motivo = f"o validador visual não viu sustentação na foto: {motivo}"
        relatorio.rejeitadas += 1
    elif tipo == "corrected":
        correcoes = decisao["corrections"]
        nova = " ".join(str(correcoes.get("observacao")).split())
        if politica.corrigida == "conflito":
            # Analista e validador discordam: os dois lados vão ao
            # vistoriador e nenhum dos dois vira texto.
            evidencia.validacao = "conflito_validacao"
            evidencia.validacao_motivo = (
                f"o analista registrou isto, e o validador visual leu na foto: \"{nova}\" "
                f"({motivo}) — confira qual descrição é a certa")
        else:
            evidencia.observacao_original = evidencia.observacao_original or evidencia.observacao
            evidencia.observacao = nova
            atributos = correcoes.get("atributos")
            if isinstance(atributos, dict):
                evidencia.atributos.update({
                    str(chave): " ".join(str(valor).split())
                    for chave, valor in atributos.items() if str(valor).strip()})
            evidencia.validacao, evidencia.validacao_motivo = "corrigida", motivo
        relatorio.corrigidas += 1
    else:  # needs_reanalysis
        if evidencia.revisao < politica.max_reanalises:
            fila.append((evidencia, decisao["focus"], motivo))
        else:
            evidencia.validacao = "nao_resolvida"
            evidencia.validacao_motivo = (
                "o validador visual continuou em dúvida mesmo depois da reanálise "
                f"({decisao['focus']}) — confira na foto")
            relatorio.nao_resolvidas += 1


def _validar_foto(validador, foto_id, evidencias, analises, imagens, nome_comodo,
                  notas_extras, politica, fila, relatorio) -> None:
    from core.gemini_client import _gerar_com_retry
    from core.style_guide import montar_prompt_validacao_visual

    por = _rotulo(validador)
    ids = [e.id for e in evidencias]
    analise = analises.get(foto_id)
    descricao_foto = {"escopo": analise.escopo.value if analise else "",
                      "motivo": analise.motivo if analise else ""}
    itens = [{"id": e.id, "categoria": e.categoria, "observacao": e.observacao,
              "atributos": e.atributos, "escopo": e.escopo.value} for e in evidencias]
    relatorio.chamadas_validador += 1
    try:
        with telemetria.contexto(foto=foto_id):
            texto = _gerar_com_retry(
                validador,
                [imagens[foto_id], montar_prompt_validacao_visual(
                    nome_comodo, itens, descricao_foto, notas_extras)],
                esquema_decisoes(ids), 4096,
                f"a validação visual de uma foto de '{nome_comodo}'", tipo="validacao",
            )
        decisoes = interpretar_decisoes(texto, ids)
    except Exception as erro:  # noqa: BLE001 — falha nunca vira aprovação
        for evidencia in evidencias:
            _marcar_falha(evidencia, politica, erro.__class__.__name__, por)
            relatorio.falhas += 1
        return
    for evidencia in evidencias:
        decisao = decisoes.get(evidencia.id)
        if decisao is None:
            _marcar_falha(evidencia, politica, "resposta sem decisão válida para este item", por)
            relatorio.falhas += 1
        else:
            _aplicar_decisao(evidencia, decisao, politica, por, fila, relatorio)


def _reanalisar_foto(analista, foto_id, pedidos, imagens, nome_comodo, notas_extras,
                     politica, relatorio) -> list:
    """Devolve as evidências reanalisadas (atualizadas no lugar), que voltam
    ao validador. As não encontradas/falhas ficam marcadas e não voltam."""
    from core.evidencias import evidencia_de_dict
    from core.gemini_client import _gerar_com_retry
    from core.style_guide import montar_prompt_reanalise_dirigida

    por = _rotulo(como_provedor(analista))
    ids = [evidencia.id for evidencia, _, _ in pedidos]
    relatorio.chamadas_reanalise += 1
    try:
        with telemetria.contexto(foto=foto_id):
            texto = _gerar_com_retry(
                analista,
                [imagens[foto_id], montar_prompt_reanalise_dirigida(nome_comodo, [
                    {"id": e.id, "observacao": e.observacao, "focus": foco, "reason": motivo}
                    for e, foco, motivo in pedidos], notas_extras)],
                esquema_reanalises(ids), 4096,
                f"a reanálise dirigida de uma foto de '{nome_comodo}'", tipo="reanalise",
            )
        respostas = {}
        for item in _ler_lista(texto, "reanalises"):
            if isinstance(item, dict) and item.get("evidence_id") in ids:
                respostas.setdefault(item["evidence_id"], []).append(item)
    except Exception as erro:  # noqa: BLE001
        for evidencia, _, _ in pedidos:
            _marcar_falha(evidencia, politica, f"reanálise: {erro.__class__.__name__}", por)
            relatorio.falhas += 1
        return []

    voltam = []
    for evidencia, foco, _ in pedidos:
        itens = respostas.get(evidencia.id, [])
        item = itens[0] if len(itens) == 1 else None
        if item is None or not isinstance(item.get("encontrado"), bool):
            _marcar_falha(evidencia, politica, "reanálise sem resposta válida para este item", por)
            relatorio.falhas += 1
            continue
        if not item["encontrado"] or not isinstance(item.get("evidencia"), dict):
            evidencia.validacao = "nao_resolvida"
            evidencia.validacao_motivo = (
                f"na reanálise dirigida ({foco}) a foto não sustentou o item — confira")
            evidencia.validacao_por = por
            relatorio.nao_resolvidas += 1
            continue
        nova = evidencia_de_dict(item["evidencia"], evidencia.id, evidencia.foto_id)
        if not nova.observacao:
            _marcar_falha(evidencia, politica, "reanálise sem observação", por)
            relatorio.falhas += 1
            continue
        # A MESMA evidência, atualizada: id, foto e instância ficam; o que o
        # analista viu de novo substitui o que ele tinha visto.
        evidencia.observacao_original = evidencia.observacao_original or evidencia.observacao
        evidencia.categoria = nova.categoria
        evidencia.observacao = nova.observacao
        evidencia.escopo = nova.escopo
        evidencia.confianca_percepcao = nova.confianca_percepcao
        evidencia.confianca_escopo = nova.confianca_escopo
        evidencia.atributos = nova.atributos
        evidencia.revisao += 1
        evidencia.origem = por
        evidencia.validacao = ""
        relatorio.reanalisadas += 1
        voltam.append(evidencia)
    return voltam


def validar_evidencias(validador, analista, aceitas: list, analises: dict, imagens: dict,
                       nome_comodo: str, notas_extras: str = "",
                       politica: PoliticaValidacao | None = None,
                       progresso=None) -> RelatorioValidacao:
    """Roda os nós POLÍTICA -> VALIDAÇÃO -> REANÁLISE -> VALIDAÇÃO.

    Altera as evidências NO LUGAR (campos de validação, observação corrigida,
    reanálise) e devolve o relatório. Não decide nada sobre o laudo: quem
    transforma o resultado em aceite/descarte é `validar_escopo`, chamado
    depois pelo pipeline. Termina sempre: a reanálise só acontece enquanto
    `revisao < max_reanalises`."""
    politica = politica or politica_do_ambiente()
    relatorio = RelatorioValidacao()
    selecionadas, excedentes, motivos = selecionar(aceitas, politica)
    relatorio.selecionadas, relatorio.excedentes = len(selecionadas), len(excedentes)
    relatorio.motivos_selecao = motivos
    for evidencia in excedentes:
        evidencia.validacao = "nao_validada_limite"
        evidencia.validacao_motivo = "passou do teto de validações do cômodo; seguiu como o escopo decidiu"

    pendentes = [e for e in selecionadas if e.foto_id in imagens]
    for evidencia in selecionadas:
        if evidencia.foto_id not in imagens:
            _marcar_falha(evidencia, politica, "foto da evidência não encontrada", _rotulo(validador))
            relatorio.falhas += 1

    rodada = 0
    while pendentes:
        rodada += 1
        fila: list = []
        grupos = _por_foto(pendentes)
        for numero, (foto_id, do_grupo) in enumerate(sorted(grupos.items()), start=1):
            if progresso:
                progresso(f"validação visual (rodada {rodada}): foto {numero}/{len(grupos)}, "
                          f"{len(do_grupo)} evidência(s)")
            _validar_foto(validador, foto_id, do_grupo, analises, imagens, nome_comodo,
                          notas_extras, politica, fila, relatorio)
        pendentes = []
        for foto_id, pedidos in sorted(_por_foto_pedidos(fila).items()):
            if progresso:
                progresso(f"reanálise dirigida: {len(pedidos)} ponto(s) numa foto")
            pendentes.extend(_reanalisar_foto(analista, foto_id, pedidos, imagens, nome_comodo,
                                              notas_extras, politica, relatorio))
    return relatorio


def _por_foto_pedidos(fila: list) -> dict:
    grupos: dict = {}
    for pedido in fila:
        grupos.setdefault(pedido[0].foto_id, []).append(pedido)
    return grupos

