"""
V2: promoção de elemento de fronteira e checklist de cobertura.

Os dois mecanismos que corrigem as perdas medidas no benchmark de 107 fotos:

- **fronteira**: a V1 descartou a soleira do BWC e a porta-janela do Quarto
  Suíte como "ambiente adjacente", e as duas sumiram do laudo;
- **cobertura**: a V1 perdeu porta-papel, ganchos e porta-toalha na
  consolidação, sem que nada no sistema reclamasse.

Nenhum teste chama o Gemini.
"""

import pytest

from core.cobertura import (
    encontrar_lacunas,
    instrucoes_de_segunda_olhada,
    itens_esperados,
    tipo_de_comodo,
)
from core.evidencias import (
    AnaliseFoto,
    EscopoFoto,
    Evidencia,
    MotivoDescarte,
    TipoConflito,
    validar_escopo,
)
from core.taxonomia import Escopo

COMODO = "BWC Suíte"


def foto(foto_id, escopo=EscopoFoto.VALIDA, **kwargs):
    return AnaliseFoto(foto_id=foto_id, comodo_alvo=COMODO, escopo=escopo,
                       relevancia=kwargs.pop("relevancia", 95), **kwargs)


def ev(evidencia_id, foto_id, observacao, categoria="obs",
       escopo=Escopo.INTERIOR, percepcao=95, conf_escopo=95, **kwargs):
    return Evidencia(id=evidencia_id, foto_id=foto_id, categoria=categoria,
                     observacao=observacao, escopo=escopo,
                     confianca_percepcao=percepcao, confianca_escopo=conf_escopo,
                     **kwargs)


def validar(evidencias, analises, comodo=COMODO):
    return validar_escopo(evidencias, {a.foto_id: a for a in analises}, comodo)


# ==========================================================================
# PROMOÇÃO DE FRONTEIRA — o erro nº 1 da V1
# ==========================================================================

def test_soleira_classificada_como_adjacente_e_recuperada():
    """Benchmark, BWC Suíte: o modelo deu ADJACENTE à soleira porque ela
    divide dois pisos, e o laudo perdeu a soleira que o clássico tinha."""
    evidencias = [ev(
        "e1", "f1",
        "Soleira em granito bege separando o piso do banheiro do piso do quarto",
        categoria="piso", escopo=Escopo.ADJACENTE, conf_escopo=80,
    )]
    resultado = validar(evidencias, [foto("f1")])

    assert len(resultado.aceitas) == 1
    recuperada = resultado.aceitas[0]
    assert recuperada.escopo is Escopo.FRONTEIRA
    assert recuperada.escopo_original is Escopo.ADJACENTE
    assert recuperada.categoria == "porta"          # e vai para a categoria certa
    assert resultado.promovidas_para_fronteira == 1


def test_porta_janela_para_a_varanda_e_recuperada():
    """Benchmark, Quarto Suíte: as duas evidências da porta-janela foram
    descartadas e a categoria Janela sumiu do laudo."""
    evidencias = [
        ev("e1", "f1",
           "Esquadria de alumínio branco com vidro transparente voltada para área externa",
           categoria="janela", escopo=Escopo.ADJACENTE, conf_escopo=70),
        ev("e2", "f2", "Esquadria de alumínio branco em janela de correr com vista externa",
           categoria="janela", escopo=Escopo.EXTERIOR, conf_escopo=70),
    ]
    resultado = validar(evidencias, [foto("f1"), foto("f2")])

    assert len(resultado.aceitas) == 2
    assert all(e.escopo is Escopo.FRONTEIRA for e in resultado.aceitas)
    assert all(e.categoria == "janela" for e in resultado.aceitas)


def test_peitoril_e_recuperado():
    evidencias = [ev("e1", "f1", "Peitoril em granito cinza da janela",
                     categoria="piso", escopo=Escopo.ADJACENTE, conf_escopo=60)]
    resultado = validar(evidencias, [foto("f1")])
    assert resultado.aceitas[0].categoria == "janela"
    assert resultado.aceitas[0].escopo is Escopo.FRONTEIRA


def test_fronteira_promovida_ignora_o_piso_de_confianca_de_escopo():
    """A promoção resolveu o pertencimento por estrutura. Cobrar dela a nota
    do modelo seria descartar de novo o que acabou de ser recuperado."""
    evidencias = [ev("e1", "f1", "Batente em madeira escura entre o quarto e o corredor",
                     categoria="paredes", escopo=Escopo.ADJACENTE, conf_escopo=20)]
    resultado = validar(evidencias, [foto("f1")])
    assert len(resultado.aceitas) == 1
    assert resultado.aceitas[0].categoria == "porta"


def test_o_cenario_alem_da_abertura_continua_fora():
    """A esquadria é do cômodo; o telhado do vizinho, não (item 10)."""
    evidencias = [ev("e1", "f1", "Telhado do vizinho e jardim vistos pela janela",
                     categoria="obs", escopo=Escopo.EXTERIOR, conf_escopo=90)]
    resultado = validar(evidencias, [foto("f1")])
    assert resultado.aceitas == []
    assert evidencias[0].motivo_descarte is MotivoDescarte.EXTERIOR


def test_porta_vista_no_espelho_nao_e_promovida():
    """Reflexo nunca é promovido: uma porta no espelho continua reflexo."""
    evidencias = [ev("e1", "f1", "Porta de madeira escura refletida no espelho",
                     categoria="porta", escopo=Escopo.REFLEXO)]
    resultado = validar(evidencias, [foto("f1")])
    assert resultado.aceitas == []
    assert evidencias[0].motivo_descarte is MotivoDescarte.REFLEXO
    assert evidencias[0].escopo_original is None


def test_parede_de_ambiente_vizinho_nao_e_fronteira():
    """A trava não pode virar uma porta dos fundos: parede de corredor não é
    elemento de fronteira e continua descartada."""
    evidencias = [ev("e1", "f1", "Parede em pintura cinza do corredor",
                     categoria="paredes", escopo=Escopo.ADJACENTE, conf_escopo=20)]
    resultado = validar(evidencias, [foto("f1")])
    assert resultado.aceitas == []
    assert evidencias[0].motivo_descarte is MotivoDescarte.AMBIENTE_ADJACENTE
    assert resultado.conflitos[0].tipo is TipoConflito.ESCOPO


def test_ambiguo_vira_pendencia_e_nao_texto():
    evidencias = [ev("e1", "f1", "Algo na parede que não deu para identificar",
                     escopo=Escopo.AMBIGUO)]
    resultado = validar(evidencias, [foto("f1")])
    assert resultado.aceitas == []
    assert evidencias[0].motivo_descarte is MotivoDescarte.AMBIGUO
    assert resultado.conflitos


def test_cinco_fotos_de_ambiente_adjacente_nao_promovem_escopo():
    """Item 31: corroboração melhora percepção, nunca pertencimento."""
    evidencias = [
        ev(f"e{i}", f"f{i}", "Parede em pintura cinza do corredor",
           categoria="paredes", escopo=Escopo.ADJACENTE, conf_escopo=90,
           atributos={"material": "pintura", "cor": "cinza"})
        for i in range(1, 6)
    ]
    resultado = validar(evidencias, [foto(f"f{i}") for i in range(1, 6)])
    assert resultado.aceitas == []
    assert len(resultado.descartadas) == 5


# ==========================================================================
# CONFLITO DE ATRIBUTO — o erro nº 2 da V1
# ==========================================================================

def test_conflito_de_atributo_nao_invalida_os_outros_atributos():
    """Item 30: duas fotos discordam só das dobradiças; a porta continua."""
    evidencias = [
        ev("e1", "f1", "Porta em madeira branca com dobradiças douradas",
           categoria="porta",
           atributos={"material": "madeira", "cor": "branca", "acabamento": "dourado"}),
        ev("e2", "f2", "Porta em madeira branca com dobradiças cromadas",
           categoria="porta",
           atributos={"material": "madeira", "cor": "branca", "acabamento": "cromado"}),
    ]
    resultado = validar(evidencias, [foto("f1"), foto("f2")])

    # as duas continuam disponíveis para o redator
    assert len(resultado.aceitas) == 2
    assert resultado.conflitos[0].tipo is TipoConflito.ATRIBUTO
    # o conflito é só do acabamento
    for evidencia in evidencias:
        assert evidencia.atributos_em_conflito == ["acabamento"]
        assert evidencia.atributos["material"] == "madeira"


def test_rejunte_nao_conflita_com_revestimento():
    """Benchmark: conflito falso da V1 entre "cerâmica branca" e "rejunte
    cinza" na mesma parede do BWC."""
    evidencias = [
        ev("e1", "f1", "Parede em cerâmica branca com rejunte cinza", categoria="paredes",
           atributos={"material": "cerâmica", "cor": "branca", "rejunte_cor": "cinza"}),
        ev("e2", "f2", "Parede em cerâmica branca", categoria="paredes",
           atributos={"material": "cerâmica", "cor": "branca"}),
    ]
    resultado = validar(evidencias, [foto("f1"), foto("f2")])
    assert resultado.conflitos == []
    assert len(resultado.aceitas) == 2


# ==========================================================================
# COBERTURA — o erro nº 3 da V1
# ==========================================================================

def test_tipo_de_comodo_pelo_nome():
    assert tipo_de_comodo("BWC Suíte") == "banheiro"
    assert tipo_de_comodo("BWC Social 02") == "banheiro"
    assert tipo_de_comodo("Quarto Suíte") == "quarto"
    assert tipo_de_comodo("Quarto 01") == "quarto"
    assert tipo_de_comodo("Cozinha") == "cozinha"
    assert tipo_de_comodo("Área de Serviço") == "area_de_servico"
    assert tipo_de_comodo("Sala") == "sala"
    assert tipo_de_comodo("Varanda") == "varanda"
    assert tipo_de_comodo("Corredor") == "corredor"
    assert tipo_de_comodo("Depósito") == "generico"


def test_banheiro_espera_os_acessorios_pequenos():
    """São exatamente os que a V1 perdeu."""
    chaves = {item.chave for item in itens_esperados("BWC Suíte")}
    assert {"portapapel", "portatoalha", "ganchos", "saboneteira"} <= chaves


def test_acessorios_faltando_viram_lacuna():
    """Benchmark: o laudo da V1 saiu sem porta-papel, ganchos e toalheiro."""
    evidencias = [
        ev("e1", "f1", "Bacia sanitária em louça branca"),
        ev("e2", "f1", "Bancada em granito com cuba oval"),
        ev("e3", "f1", "Chuveiro em metal cromado"),
        ev("e4", "f1", "Box com folhas em vidro verde"),
        ev("e5", "f1", "Espelho circular articulado"),
        ev("e6", "f1", "Piso em cerâmica branca"),
        ev("e7", "f1", "Teto em laje pintada de branco"),
        ev("e8", "f1", "Paredes em azulejo branco"),
        ev("e9", "f1", "Porta em madeira escura com batente"),
        ev("e10", "f1", "Ponto de iluminação com plafon"),
        ev("e11", "f1", "Placa com tomada e interruptor"),
        ev("e12", "f1", "Janela basculante em alumínio"),
    ]
    lacunas = encontrar_lacunas("BWC Suíte", evidencias)
    faltando = {lacuna.chave for lacuna in lacunas}
    assert {"portapapel", "portatoalha", "ganchos", "saboneteira"} <= faltando


def test_quando_o_acessorio_existe_nao_vira_lacuna():
    evidencias = [
        ev("e1", "f1", "Porta-papel higiênico em metal cromado"),
        ev("e2", "f1", "Toalheiro em argola cromado"),
        ev("e3", "f1", "Cinco ganchos cabideiros"),
        ev("e4", "f1", "Saboneteira de parede"),
    ]
    faltando = {lacuna.chave for lacuna in encontrar_lacunas("BWC Suíte", evidencias)}
    assert not ({"portapapel", "portatoalha", "ganchos", "saboneteira"} & faltando)


def test_ar_condicionado_faltando_no_quarto_vira_lacuna():
    """Benchmark: o motor clássico perdeu o split inteiro do Quarto Suíte."""
    evidencias = [ev("e1", "f1", "Paredes em pintura branca")]
    faltando = {lacuna.chave for lacuna in encontrar_lacunas("Quarto Suíte", evidencias)}
    assert "climatizacao" in faltando


def test_a_cobertura_nao_afirma_que_o_item_existe():
    """Item 22: a saída é dúvida, não afirmação. A lacuna diz onde olhar."""
    lacunas = encontrar_lacunas("BWC Suíte", [])
    assert lacunas
    for lacuna in lacunas:
        assert lacuna.onde_olhar
        assert "Revise" in lacuna.onde_olhar


def test_instrucoes_dirigidas_nao_se_repetem():
    """Porta-papel, ganchos e toalheiro compartilham a mesma busca: mandar a
    mesma frase três vezes gastaria três chamadas para o mesmo trabalho."""
    lacunas = encontrar_lacunas("BWC Suíte", [])
    instrucoes = instrucoes_de_segunda_olhada(lacunas)
    textos = [i["instrucao"] for i in instrucoes]
    assert len(textos) == len(set(textos))
    acessorios = next(i for i in instrucoes if "acessórios" in i["instrucao"])
    assert len(acessorios["procurando"]) >= 3


def test_comodo_sem_lacuna_nao_gera_segunda_olhada():
    evidencias = [
        ev("e1", "f1", "Piso em cerâmica cinza com rodapé em cerâmica"),
        ev("e2", "f1", "Teto em laje pintada de branco"),
        ev("e3", "f1", "Paredes em pintura lisa branca"),
        ev("e4", "f1", "Porta em madeira com batente e soleira"),
        ev("e5", "f1", "Ponto de iluminação com plafon de sobrepor"),
        ev("e6", "f1", "Placa com tomada e interruptor"),
    ]
    assert encontrar_lacunas("Corredor", evidencias) == []
    assert instrucoes_de_segunda_olhada([]) == []


def test_varanda_nao_exige_porta_nem_bacia():
    """Cada tipo de cômodo espera o que faz sentido nele."""
    chaves = {item.chave for item in itens_esperados("Varanda")}
    assert "bacia" not in chaves
    assert "piso" in chaves and "parede" in chaves
