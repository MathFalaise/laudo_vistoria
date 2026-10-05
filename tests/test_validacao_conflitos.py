"""
Decisões em pendências de CONFLITO (core/validacao.aplicar_no_texto).

Bug de 05/10/2026: só "Tipo: falta" era tratado como proposta, e o conflito
de escopo — cujo "Item:" é um RESUMO do conflito, não uma linha do laudo —
caía na busca da linha no texto. CORRIGIR, que é justamente o que o motivo
da pendência manda usar, falhava com "item não encontrado no laudo".

Os conflitos do validador visual (TipoConflito.VALIDACAO) chegam ao arquivo
com o mesmo tipo scope_conflict e seguem a mesma regra.

Nada aqui chama API.
"""

import pytest

import core.pipeline as pipeline
from core import validacao
from core.evidencias import ConflitoEscopo, TipoConflito
from core.report_writer import parsear_txt_comodo, salvar_txt_comodo


def _conflito(decisao: str, correcao: str = "") -> dict:
    return {"tipo": "scope_conflict", "texto": "parede verde em 1 de 6 fotos — resumo",
            "decisao": decisao, "correcao": correcao}


def test_tipo_do_conflito_e_o_do_pipeline():
    assert validacao.TIPO_CONFLITO == pipeline.TIPO_CONFLITO_ESCOPO
    assert validacao.TIPO_CONFLITO in validacao.TIPOS_PROPOSTA


def test_conflito_com_corrigir_acrescenta_a_correcao():
    # A reprodução do bug.
    novo, erro = validacao.aplicar_no_texto(
        "*Piso em cerâmica, em bom estado.", "paredes",
        _conflito("CORRIGIR", "*Parede em pintura verde, em bom estado."))
    assert erro is None
    assert novo == "*Piso em cerâmica, em bom estado.\n*Parede em pintura verde, em bom estado."


def test_conflito_com_corrigir_normaliza_a_linha():
    novo, erro = validacao.aplicar_no_texto(
        "*Uma bancada.", "mobilia", _conflito("CORRIGIR", "Um espelho sobre a bancada."))
    assert erro is None
    assert novo.split("\n")[-1] == "*Um espelho sobre a bancada."


def test_conflito_com_corrigir_em_categoria_vazia_substitui_o_vazio():
    novo, erro = validacao.aplicar_no_texto(
        "", "janela", _conflito("CORRIGIR", "*Uma janela de correr em alumínio."))
    assert erro is None
    assert novo == "*Uma janela de correr em alumínio."


def test_conflito_com_corrigir_sem_correcao_e_erro():
    novo, erro = validacao.aplicar_no_texto("*Uma bancada.", "mobilia", _conflito("CORRIGIR"))
    assert erro and "CORREÇÃO está vazia" in erro
    assert novo == "*Uma bancada."


def test_conflito_com_remover_descarta_sem_tocar_no_laudo():
    novo, erro = validacao.aplicar_no_texto("*Uma bancada.", "mobilia", _conflito("REMOVER"))
    assert erro is None
    assert novo == "*Uma bancada."


@pytest.mark.parametrize("texto", ["*Uma bancada.", ""])
def test_conflito_com_ok_fica_aberto_e_nao_acrescenta_o_resumo(texto):
    # O resumo do conflito nunca vira linha do laudo; OK é ambíguo e o
    # "deixar fora" já é o REMOVER.
    novo, erro = validacao.aplicar_no_texto(texto, "mobilia", _conflito("OK"))
    assert erro and "CORRIGIR" in erro and "REMOVER" in erro
    assert novo == texto
    assert "resumo" not in novo


def test_falta_continua_aceitando_com_ok():
    pendencia = {"tipo": "falta", "texto": "*Um varal de teto.", "decisao": "OK"}
    novo, erro = validacao.aplicar_no_texto("*Uma bancada.", "mobilia", pendencia)
    assert erro is None
    assert novo == "*Uma bancada.\n*Um varal de teto."


# --------------------------------------------------------------------------
# De ponta a ponta: conflitos_para_pendencias -> arquivo -> validar.py
# --------------------------------------------------------------------------

def test_validar_aplica_conflitos_de_escopo_e_de_validacao_visual(tmp_path):
    pasta_comodo = tmp_path / "BWC"
    pasta_comodo.mkdir()
    salvar_txt_comodo(str(pasta_comodo), "BWC", {
        "paredes": "*Paredes em revestimento cerâmico branco, em bom estado.",
        "mobilia": "*Um box em vidro temperado, em bom estado.",
    })

    conflitos = [
        ConflitoEscopo("paredes", "parede verde vista em 1 de 6 fotos", ["e1"], ["f1.jpg"]),
        ConflitoEscopo("mobilia", "bacia com caixa acoplada contestada pelo validador",
                       ["e2"], ["f2.jpg"], tipo=TipoConflito.VALIDACAO),
        ConflitoEscopo("mobilia", "espelho que reflete o quarto", ["e3"], ["f3.jpg"]),
    ]
    pendencias = pipeline.conflitos_para_pendencias("BWC", conflitos)
    assert pendencias[1]["motivo"].startswith(pipeline.PREFIXO_VALIDACAO)
    pendencias[0].update(decisao="CORRIGIR",
                         correcao="*Uma parede em pintura verde, em bom estado.")
    pendencias[1].update(decisao="CORRIGIR",
                         correcao="*Uma bacia sanitária com válvula de parede, em bom estado.")
    pendencias[2].update(decisao="OK")
    validacao.salvar_pendencias(str(tmp_path), pendencias)

    resultado = validacao.aplicar_pendencias(str(tmp_path))

    assert len(resultado["aplicadas"]) == 2
    assert resultado["comodos_alterados"] == ["BWC"]
    dados = parsear_txt_comodo(str(pasta_comodo / "BWC_vistoria.txt"))
    assert dados["paredes"].split("\n") == [
        "*Paredes em revestimento cerâmico branco, em bom estado.",
        "*Uma parede em pintura verde, em bom estado.",
    ]
    assert dados["mobilia"].split("\n") == [
        "*Um box em vidro temperado, em bom estado.",
        "*Uma bacia sanitária com válvula de parede, em bom estado.",
    ]
    # O OK ficou em aberto, com a explicação, e o resumo não entrou no laudo.
    [restante] = validacao.ler_pendencias(str(tmp_path))
    assert restante["texto"] == "espelho que reflete o quarto"
    assert "REMOVER" in restante["situacao"]
    assert "espelho" not in dados["mobilia"]
