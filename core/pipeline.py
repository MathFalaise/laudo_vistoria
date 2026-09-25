"""
PIPELINE do cômodo — a orquestração que o CLI e a API web compartilham.

    FOTOS
      -> ANÁLISE DA FOTO (modelo: escopo + evidências cruas)
      -> VALIDAÇÃO DE ESCOPO (código: determinística, em core.evidencias)
      -> CONSOLIDAÇÃO (modelo: escreve o laudo só com o que passou)
      -> TRAVAS DO MOTOR ANTIGO (repetidos, segunda olhada, testes indevidos)
      -> LAUDO + PENDÊNCIAS
      -> CONFERÊNCIA (inalterada, em conferir.py)
      -> VALIDAÇÃO HUMANA (inalterada, em core.validacao)

Existe um caminho antigo e um novo, e os dois continuam funcionando:

- `processar_comodo_classico` é o motor de sempre, UMA chamada por cômodo,
  bit a bit o que rodou nas vistorias reais até 24/09/2026;
- `processar_comodo_evidencias` é o caminho novo, com escopo.

Manter os dois é proposital. O caminho novo custa um prompt a mais por lote de
fotos e muda o texto que sai; antes de ele virar padrão sem volta, o
vistoriador precisa rodar os dois no mesmo imóvel e comparar. Quem escolhe é
`config.USAR_MOTOR_DE_EVIDENCIAS` (e a flag `--classico` do main.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.config import CATEGORIAS, FOTOS_POR_LOTE_ESCOPO
from core.evidencias import (
    AnaliseFoto,
    ConflitoEscopo,
    Evidencia,
    ResultadoEscopo,
    validar_escopo,
)
from core.gemini_client import (
    analisar_comodo,
    analisar_escopo_e_evidencias,
    consolidar_evidencias,
)
from core.image_utils import codificar_imagem, listar_fotos

# Motivo das pendências de conflito de escopo. O prefixo é o que o vistoriador
# lê primeiro no arquivo, e ele precisa saber de cara que aquilo NÃO está no
# laudo — ao contrário das pendências de certeza, que estão.
PREFIXO_CONFLITO = "CONFLITO DE ESCOPO — não entrou no laudo"

TIPO_CONFLITO_ESCOPO = "scope_conflict"


@dataclass
class ResultadoComodo:
    """Tudo o que o processamento de um cômodo produziu.

    O CLI usa `dados` e `incertos` (é o contrato antigo, intacto) e grava o
    resto num JSON ao lado do laudo. A API web persiste o grafo inteiro:
    Photo -> Evidence -> ReportItem -> ValidationItem."""

    nome_comodo: str
    dados: dict
    incertos: list
    evidencias: list = field(default_factory=list)
    analises: dict = field(default_factory=dict)
    conflitos: list = field(default_factory=list)
    fotos_utilizaveis: int = 0
    fotos_totais: int = 0
    cobertura_incompleta: bool = False

    def evidencias_aceitas(self) -> list:
        return [e for e in self.evidencias if e.aceita]

    def para_dict(self) -> dict:
        return {
            "comodo": self.nome_comodo,
            "fotos_totais": self.fotos_totais,
            "fotos_utilizaveis": self.fotos_utilizaveis,
            "cobertura_incompleta": self.cobertura_incompleta,
            "analises": {
                foto_id: {
                    "escopo": analise.escopo.value,
                    "relevancia": analise.relevancia,
                    "ambiente_adjacente": analise.ambiente_adjacente,
                    "reflexo": analise.reflexo,
                    "motivo": analise.motivo,
                }
                for foto_id, analise in self.analises.items()
            },
            "evidencias": [evidencia.para_dict() for evidencia in self.evidencias],
            "conflitos": [
                {
                    "categoria": conflito.categoria,
                    "resumo": conflito.resumo,
                    "evidencias": conflito.evidencias,
                    "fotos": conflito.fotos,
                }
                for conflito in self.conflitos
            ],
        }


def _lotes(sequencia: list, tamanho: int) -> list:
    return [sequencia[i:i + tamanho] for i in range(0, len(sequencia), tamanho)]


def conflitos_para_pendencias(nome_comodo: str, conflitos: list) -> list:
    """Transforma conflitos de escopo em pendências para o vistoriador.

    Regra 18/19 do pedido: o sistema NÃO resolve isso sozinho. Ele mostra a
    foto, diz por que ficou em dúvida, e espera a decisão.

    A certeza vai 0 de propósito: não é "o modelo tem 0% de certeza do item",
    é "este sistema não tem o direito de decidir isto" — e a leitura do
    arquivo ordena as pendências pela certeza, então conflito aparece no topo."""
    pendencias = []
    for conflito in conflitos:
        pendencias.append({
            "comodo": nome_comodo,
            "categoria": conflito.categoria,
            "tipo": TIPO_CONFLITO_ESCOPO,
            "texto": conflito.resumo,
            "certeza": 0,
            "motivo": (
                f"{PREFIXO_CONFLITO}. Fotos envolvidas: "
                f"{', '.join(conflito.fotos) or '(não identificadas)'}. "
                "Se isto pertence a este cômodo, use CORRIGIR e escreva a "
                "linha do laudo; se pertence a outro ambiente, use REMOVER."
            ),
        })
    return pendencias


def processar_comodo_classico(
    cliente, pasta_comodo: str, nome_comodo: str, notas_extras: str = ""
) -> ResultadoComodo:
    """Motor original: UMA chamada por cômodo, fotos direto para o laudo.

    Mantido intacto e testado — é o que gerou todas as vistorias reais até
    24/09/2026."""
    caminhos = listar_fotos(pasta_comodo)
    if not caminhos:
        return ResultadoComodo(nome_comodo=nome_comodo, dados={}, incertos=[])

    blocos = [codificar_imagem(caminho) for caminho in caminhos]
    dados, incertos = analisar_comodo(cliente, blocos, nome_comodo, notas_extras)
    return ResultadoComodo(
        nome_comodo=nome_comodo, dados=dados, incertos=incertos,
        fotos_totais=len(caminhos), fotos_utilizaveis=len(caminhos),
    )


def processar_comodo_evidencias(
    cliente,
    pasta_comodo: str,
    nome_comodo: str,
    notas_extras: str = "",
    ids_fotos: list | None = None,
    progresso=None,
) -> ResultadoComodo:
    """Motor novo: fotos -> evidências -> escopo validado -> laudo.

    `ids_fotos` permite que a camada web passe os identificadores do banco em
    vez dos nomes de arquivo, para que Evidence.foto_id aponte para Photo.id.
    Sem ele, o id é o nome do arquivo — que é o que o CLI tem.

    Sobre as fotos irem em LOTES: o Gemini cobra por imagem, e cada foto é
    enviada uma única vez de qualquer jeito. O lote existe para o JSON de
    saída caber em max_output_tokens (uma lista de evidências de 60 fotos não
    cabe) e para o modelo não diluir a atenção. O custo extra é o texto do
    prompt repetido por lote, não uma segunda leitura das imagens."""
    caminhos = listar_fotos(pasta_comodo)
    if not caminhos:
        return ResultadoComodo(nome_comodo=nome_comodo, dados={}, incertos=[])

    import os

    identificadores = ids_fotos or [os.path.basename(caminho) for caminho in caminhos]
    if len(identificadores) != len(caminhos):
        raise ValueError(
            f"{len(identificadores)} id(s) de foto para {len(caminhos)} arquivo(s) "
            f"em '{nome_comodo}' — os dois têm que ser paralelos."
        )

    analises: dict = {}
    evidencias: list = []
    blocos_todos: list = []

    lotes_caminhos = _lotes(caminhos, FOTOS_POR_LOTE_ESCOPO)
    lotes_ids = _lotes(identificadores, FOTOS_POR_LOTE_ESCOPO)

    for numero, (lote_caminhos, lote_ids) in enumerate(zip(lotes_caminhos, lotes_ids), start=1):
        if progresso:
            progresso(f"escopo: lote {numero}/{len(lotes_caminhos)} "
                      f"({len(lote_caminhos)} foto(s))")
        blocos = [codificar_imagem(caminho) for caminho in lote_caminhos]
        blocos_todos.extend(blocos)
        analises_lote, evidencias_lote = analisar_escopo_e_evidencias(
            cliente, blocos, lote_ids, nome_comodo, notas_extras
        )
        analises.update(analises_lote)
        evidencias.extend(evidencias_lote)

    # Aqui o CÓDIGO decide. Nada do que vem abaixo depende de o modelo ter
    # obedecido alguma instrução do prompt.
    resultado_escopo = validar_escopo(evidencias, analises, nome_comodo)

    if progresso:
        progresso(
            f"escopo validado: {len(resultado_escopo.aceitas)} evidência(s) aceita(s), "
            f"{len(resultado_escopo.descartadas)} descartada(s), "
            f"{len(resultado_escopo.conflitos)} conflito(s)"
        )

    if not resultado_escopo.aceitas:
        # Nenhuma evidência sobreviveu: NÃO se escreve laudo por dedução.
        # Regra 16 — falso negativo (cômodo vazio, com pendência explicando)
        # é melhor que falso positivo (laudo inventado).
        dados = {categoria: "" for categoria in CATEGORIAS}
        incertos = [{
            "categoria": "obs",
            "texto": "",
            "certeza": 0,
            "motivo": (
                "nenhuma evidência deste cômodo passou pela validação de escopo "
                f"({resultado_escopo.fotos_utilizaveis} de {resultado_escopo.fotos_totais} "
                "foto(s) utilizável(is)) — o laudo deste cômodo não foi escrito, "
                "confira as fotos"
            ),
        }]
    else:
        if progresso:
            progresso("redigindo o laudo a partir das evidências aprovadas")
        dados, incertos = consolidar_evidencias(
            cliente, nome_comodo, resultado_escopo, blocos_todos, notas_extras
        )

    return ResultadoComodo(
        nome_comodo=nome_comodo,
        dados=dados,
        incertos=incertos,
        evidencias=evidencias,
        analises=analises,
        conflitos=resultado_escopo.conflitos,
        fotos_utilizaveis=resultado_escopo.fotos_utilizaveis,
        fotos_totais=resultado_escopo.fotos_totais,
        cobertura_incompleta=resultado_escopo.cobertura_incompleta,
    )


def processar_comodo(
    cliente,
    pasta_comodo: str,
    nome_comodo: str,
    notas_extras: str = "",
    usar_evidencias: bool | None = None,
    ids_fotos: list | None = None,
    progresso=None,
) -> ResultadoComodo:
    """Ponto de entrada único. Escolhe o motor e devolve sempre a mesma coisa."""
    from core.config import USAR_MOTOR_DE_EVIDENCIAS

    if usar_evidencias is None:
        usar_evidencias = USAR_MOTOR_DE_EVIDENCIAS
    if usar_evidencias:
        return processar_comodo_evidencias(
            cliente, pasta_comodo, nome_comodo, notas_extras, ids_fotos, progresso
        )
    return processar_comodo_classico(cliente, pasta_comodo, nome_comodo, notas_extras)
