"""
benchmark.py --provedores: as MESMAS fotos em cada configuração, e números
(não opinião) para comparar. Provedores falsos — nenhuma API é chamada.
"""

import argparse

import pytest
from PIL import Image
from test_validacao_visual import Falso, analista_padrao, decisao

import benchmark


@pytest.fixture
def imovel(tmp_path):
    pasta = tmp_path / "Imovel" / "BWC"
    pasta.mkdir(parents=True)
    for nome in ("f1.jpg", "f2.jpg"):
        Image.new("RGB", (64, 48), "white").save(pasta / nome)
    return tmp_path / "Imovel"


def test_configuracao_aceita_analista_e_validador():
    assert benchmark.configuracao("glm+claude") == ("glm", "claude")
    assert benchmark.configuracao("gemini") == ("gemini", None)
    with pytest.raises(argparse.ArgumentTypeError):
        benchmark.configuracao("openai")
    with pytest.raises(argparse.ArgumentTypeError):
        benchmark.configuracao("glm+claude+gemini")


def test_compara_provedores_nas_mesmas_fotos(imovel):
    feitos = {}

    def fabrica(nome):
        if nome == "claude":
            feitos[nome] = Falso("claude", {"validacao": decisao(
                "f2.jpg#2", "rejected", "não há caixa acoplada")}, modelo="claude-x")
        else:
            feitos[nome] = analista_padrao()
            feitos[nome].nome, feitos[nome].modelo = nome, f"{nome}-modelo"
        return feitos[nome]

    relatorio = benchmark.rodar_provedores(
        str(imovel), ["BWC"], [("gemini", None), ("glm", "claude")], fabrica=fabrica)

    assert relatorio["configuracoes"] == ["gemini", "glm+claude"]
    sem, com = (relatorio["comodos"]["BWC"]["medidas"][r] for r in ("gemini", "glm+claude"))
    # as mesmas fotos: o mesmo número de evidências nas duas passagens
    assert sem["evidencias"] == com["evidencias"] == 2
    # o validador tirou a bacia: uma aceita a menos; e DOIS conflitos a mais —
    # o da validação e a lacuna "bacia sanitária" que a cobertura, recalculada
    # depois do veto, passou a apontar (dúvida para o vistoriador, nunca "não existe")
    assert com["aceitas"] == sem["aceitas"] - 1 and com["conflitos"] == sem["conflitos"] + 2
    assert com["validacao"]["rejeitadas"] == 1 and sem["validacao"] is None
    assert com["chamadas"] > sem["chamadas"]
    assert "claude:claude-x" in com["por_modelo"]
    assert relatorio["totais"]["glm+claude"]["chamadas"] == com["chamadas"]
    assert "glm+claude" in relatorio["comodos"]["BWC"]["comparacao_com_gemini"]
    # provedor falso não registra tokens: custo desconhecido, nunca zero
    assert relatorio["totais"]["gemini"]["custo_usd"] in (None, 0.0)
    benchmark.imprimir_provedores(relatorio)
