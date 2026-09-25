"""
Testes da camada de EVIDÊNCIAS E ESCOPO (core/evidencias.py).

Os sete primeiros são os casos de regressão conceituais pedidos na regra 35:
eles descrevem, em código, o problema que motivou a evolução arquitetural.
Nenhum chama a API do Gemini — a resposta do modelo é sempre construída à mão,
porque o que está sob teste é o CÓDIGO que decide o que fazer com ela.
"""

import pytest

from core.evidencias import (
    AnaliseFoto,
    EscopoFoto,
    Evidencia,
    MotivoDescarte,
    Regiao,
    StatusEvidencia,
    analise_de_dict,
    evidencia_de_dict,
    validar_escopo,
)
from core.taxonomia import Escopo

COMODO = "Cozinha"


def foto(foto_id, escopo=EscopoFoto.VALIDA, **kwargs):
    return AnaliseFoto(foto_id=foto_id, comodo_alvo=COMODO, escopo=escopo,
                       relevancia=kwargs.pop("relevancia", 95), **kwargs)


def evidencia(evidencia_id, foto_id, categoria="paredes", observacao="parede branca",
              percepcao=95, escopo=95, **kwargs):
    """Constrói uma evidência como o modelo devolveria.

    Aceita os booleanos da V1 (`e_reflexo`, `e_ambiente_adjacente`) e os
    traduz para a taxonomia da V2, para que os testes continuem afirmando
    exatamente o que afirmavam antes."""
    classificacao = kwargs.pop("classificacao", None)
    if kwargs.pop("e_reflexo", False):
        classificacao = Escopo.REFLEXO
    if kwargs.pop("e_ambiente_adjacente", False):
        classificacao = Escopo.ADJACENTE
    return Evidencia(id=evidencia_id, foto_id=foto_id, categoria=categoria,
                     observacao=observacao, confianca_percepcao=percepcao,
                     confianca_escopo=escopo,
                     escopo=classificacao or Escopo.INTERIOR, **kwargs)


def validar(evidencias, analises):
    return validar_escopo(evidencias, {a.foto_id: a for a in analises}, COMODO)


# ==========================================================================
# CASO 1 — foto da cozinha mostra uma parede do corredor
# ==========================================================================

def test_caso1_parede_de_ambiente_adjacente_nao_entra_como_parede_do_comodo():
    """A parede do corredor está nítida na foto da cozinha. Percepção 99.
    Ela NÃO pode virar parede da cozinha."""
    evidencias = [
        evidencia("e1", "f1", observacao="parede em pintura branca"),
        evidencia("e2", "f1", observacao="parede em pintura cinza",
                  percepcao=99, escopo=99, e_ambiente_adjacente=True),
    ]
    resultado = validar(evidencias, [foto("f1", EscopoFoto.PARCIAL)])

    aceitas = [e.observacao for e in resultado.aceitas]
    assert "parede em pintura branca" in aceitas
    assert "parede em pintura cinza" not in aceitas
    assert evidencias[1].motivo_descarte is MotivoDescarte.AMBIENTE_ADJACENTE


def test_caso1_ambiente_adjacente_vira_conflito_para_o_vistoriador_decidir():
    """Regra 19: não é silêncio, é pendência de scope_conflict."""
    evidencias = [evidencia("e1", "f1", e_ambiente_adjacente=True)]
    resultado = validar(evidencias, [foto("f1")])

    assert len(resultado.conflitos) == 1
    assert resultado.conflitos[0].evidencias == ["e1"]
    assert "ambiente vizinho" in resultado.conflitos[0].resumo


def test_caso1_foto_fora_de_escopo_nao_alimenta_o_comodo():
    """A foto inteira é de outro cômodo (foi parar na pasta errada)."""
    evidencias = [evidencia("e1", "f1", percepcao=100, escopo=100)]
    resultado = validar(evidencias, [foto("f1", EscopoFoto.FORA_DE_ESCOPO)])

    assert resultado.aceitas == []
    assert evidencias[0].motivo_descarte is MotivoDescarte.FOTO_FORA_DE_ESCOPO


def test_caso1_a_foto_descartada_continua_disponivel():
    """Regra 7: a foto não some do sistema — ela só perde o direito de virar
    texto. A evidência descartada volta com o motivo, para a auditoria."""
    evidencias = [evidencia("e1", "f1")]
    resultado = validar(evidencias, [foto("f1", EscopoFoto.FORA_DE_ESCOPO)])

    assert len(resultado.descartadas) == 1
    assert resultado.descartadas[0].id == "e1"
    assert resultado.fotos_totais == 1


# ==========================================================================
# CASO 2 — espelho refletindo outro cômodo
# ==========================================================================

def test_caso2_reflexo_nao_vira_conteudo_do_comodo():
    evidencias = [
        evidencia("e1", "f1", categoria="mobilia", observacao="um espelho na parede"),
        evidencia("e2", "f1", categoria="mobilia", observacao="um armário em madeira",
                  e_reflexo=True),
    ]
    resultado = validar(evidencias, [foto("f1")])

    assert [e.id for e in resultado.aceitas] == ["e1"]
    assert evidencias[1].motivo_descarte is MotivoDescarte.REFLEXO


def test_caso2_reflexo_com_confianca_altissima_continua_descartado():
    """Reflexo é fato categórico, não questão de grau: 100% de certeza de que
    é um reflexo não o transforma em móvel do cômodo."""
    evidencias = [evidencia("e1", "f1", percepcao=100, escopo=100, e_reflexo=True)]
    assert validar(evidencias, [foto("f1")]).aceitas == []


def test_caso2_reflexo_nao_duplica_um_item_que_ja_existe():
    """A porta aparece de verdade E refletida no espelho. Tem que sobrar UMA."""
    evidencias = [
        evidencia("e1", "f1", categoria="porta", observacao="uma porta em madeira branca"),
        evidencia("e2", "f1", categoria="porta", observacao="uma porta em madeira branca",
                  e_reflexo=True),
    ]
    resultado = validar(evidencias, [foto("f1")])
    assert len(resultado.aceitas) == 1


# ==========================================================================
# CASO 3 — foto mostra só parte do cômodo
# ==========================================================================

def test_caso3_cobertura_incompleta_e_sinalizada():
    """Se nenhuma foto cobre o cômodo inteiro, o sistema não pode concluir
    que algo NÃO existe. Quem usa esta flag é a consolidação."""
    resultado = validar([evidencia("e1", "f1")], [foto("f1", EscopoFoto.PARCIAL)])
    assert resultado.cobertura_incompleta is True


def test_caso3_cobertura_completa_quando_todas_as_fotos_sao_validas():
    resultado = validar(
        [evidencia("e1", "f1"), evidencia("e2", "f2")],
        [foto("f1"), foto("f2")],
    )
    assert resultado.cobertura_incompleta is False


def test_caso3_sem_foto_utilizavel_a_cobertura_e_incompleta():
    resultado = validar([], [foto("f1", EscopoFoto.FORA_DE_ESCOPO)])
    assert resultado.cobertura_incompleta is True
    assert resultado.fotos_utilizaveis == 0


def test_caso3_foto_parcial_sustenta_evidencia_com_desconto():
    """PARCIAL não é FORA_DE_ESCOPO: a evidência vale, valendo menos."""
    uma = evidencia("e1", "f1", percepcao=90, escopo=90)
    outra = evidencia("e2", "f2", percepcao=90, escopo=90)
    r1 = validar([uma], [foto("f1", EscopoFoto.VALIDA)])
    r2 = validar([outra], [foto("f2", EscopoFoto.PARCIAL)])

    assert r1.aceitas and r2.aceitas
    assert r2.aceitas[0].confianca_final < r1.aceitas[0].confianca_final


# ==========================================================================
# CASO 4 — foto isolada contradiz todas as outras
# ==========================================================================

def test_caso4_a_foto_isolada_nao_e_descartada_por_votacao():
    """Três fotos dizem branco, uma diz azul. Proibido eleger a maioria e
    apagar a minoria — a foto isolada pode ser justamente a que mostra a
    parede certa."""
    evidencias = [
        evidencia("e1", "f1", observacao="parede em pintura branca",
                  atributos={"material": "pintura", "cor": "branca"}),
        evidencia("e2", "f2", observacao="parede em pintura branca",
                  atributos={"material": "pintura", "cor": "branca"}),
        evidencia("e3", "f3", observacao="parede em pintura branca",
                  atributos={"material": "pintura", "cor": "branca"}),
        evidencia("e4", "f4", observacao="parede em textura projetada azul",
                  atributos={"material": "pintura", "cor": "azul"}),
    ]
    resultado = validar(evidencias, [foto(f"f{i}") for i in range(1, 5)])

    ids = {e.id for e in resultado.aceitas} | {e.id for e in resultado.descartadas}
    assert "e4" in ids, "a evidência minoritária não pode sumir do sistema"
    assert evidencias[3].motivo_descarte is None, "não foi descartada"


def test_caso4_contradicao_vira_conflito_e_rebaixa_os_dois_lados():
    evidencias = [
        evidencia("e1", "f1", observacao="parede em pintura branca",
                  atributos={"material": "pintura", "cor": "branca"}),
        evidencia("e2", "f2", observacao="parede em pintura azul",
                  atributos={"material": "pintura", "cor": "azul"}),
    ]
    resultado = validar(evidencias, [foto("f1"), foto("f2")])

    assert len(resultado.conflitos) == 1
    assert set(resultado.conflitos[0].evidencias) == {"e1", "e2"}
    for item in evidencias:
        assert item.status is StatusEvidencia.EM_CONFLITO
        assert item.confianca_final < 95


def test_caso4_duas_cores_no_mesmo_item_nao_sao_contradicao():
    """"parede branca com faixa em tons de verde" é uma descrição só."""
    evidencias = [
        evidencia("e1", "f1", observacao="parede em cerâmica branca com faixa verde"),
        evidencia("e2", "f2", observacao="parede em cerâmica branca com faixa verde"),
    ]
    resultado = validar(evidencias, [foto("f1"), foto("f2")])
    assert resultado.conflitos == []


def test_caso4_corroboracao_melhora_a_percepcao_quando_ela_e_o_gargalo():
    """Ver a mesma coisa em duas fotos responde melhor "o que é isso?"."""
    atributos = {"material": "porcelanato", "cor": "bege"}
    sozinha = evidencia("s1", "f9", observacao="piso em porcelanato bege",
                        categoria="piso", percepcao=70, escopo=95,
                        atributos=dict(atributos))
    base = validar([sozinha], [foto("f9")]).aceitas[0].confianca_final

    apoiadas = [
        evidencia("e1", "f1", observacao="piso em porcelanato bege",
                  categoria="piso", percepcao=70, escopo=95,
                  atributos=dict(atributos)),
        evidencia("e2", "f2", observacao="piso em porcelanato bege",
                  categoria="piso", percepcao=70, escopo=95,
                  atributos=dict(atributos)),
    ]
    com_apoio = validar(apoiadas, [foto("f1"), foto("f2")]).aceitas[0].confianca_final
    assert com_apoio > base


def test_caso4_corroboracao_nao_ajuda_quando_o_gargalo_e_o_escopo():
    """A outra metade da regra 14: repetir "vi isso" não responde "é deste
    cômodo?". Com escopo abaixo da percepção, corroborar não muda nada."""
    atributos = {"material": "porcelanato", "cor": "bege"}
    sozinha = evidencia("s1", "f9", observacao="piso em porcelanato bege",
                        categoria="piso", percepcao=95, escopo=75,
                        atributos=dict(atributos))
    base = validar([sozinha], [foto("f9")]).aceitas[0].confianca_final

    apoiadas = [
        evidencia("e1", "f1", observacao="piso em porcelanato bege",
                  categoria="piso", percepcao=95, escopo=75,
                  atributos=dict(atributos)),
        evidencia("e2", "f2", observacao="piso em porcelanato bege",
                  categoria="piso", percepcao=95, escopo=75,
                  atributos=dict(atributos)),
    ]
    com_apoio = validar(apoiadas, [foto("f1"), foto("f2")]).aceitas[0].confianca_final
    assert com_apoio == base == 75


def test_caso4_corroboracao_nao_ultrapassa_a_confianca_de_escopo():
    """O ponto da regra 14: repetir "vi isso" não responde "é deste cômodo?".
    Uma parede de corredor fotografada de cinco ângulos continua do corredor."""
    evidencias = [
        evidencia(f"e{i}", f"f{i}", observacao="piso em porcelanato bege",
                  categoria="piso", percepcao=100, escopo=72,
                  atributos={"material": "porcelanato", "cor": "bege"})
        for i in range(1, 6)
    ]
    resultado = validar(evidencias, [foto(f"f{i}") for i in range(1, 6)])
    for item in resultado.aceitas:
        assert item.confianca_final <= 72


def test_caso4_corroboracao_exige_fotos_diferentes():
    """Três evidências da MESMA foto não são três confirmações."""
    evidencias = [
        evidencia(f"e{i}", "f1", observacao="piso em porcelanato bege",
                  categoria="piso", percepcao=80, escopo=80,
                  atributos={"material": "porcelanato", "cor": "bege"})
        for i in range(1, 4)
    ]
    resultado = validar(evidencias, [foto("f1")])
    assert all(not e.corroborada_por for e in resultado.aceitas)


# ==========================================================================
# CASO 5 — material ambíguo
# ==========================================================================

def test_caso5_material_ambiguo_nao_vira_afirmacao():
    """Percepção baixa = o modelo não distinguiu o material. Não escreve."""
    evidencias = [evidencia("e1", "f1", observacao="bancada, material indefinido",
                            categoria="mobilia", percepcao=40, escopo=95)]
    resultado = validar(evidencias, [foto("f1")])

    assert resultado.aceitas == []
    assert evidencias[0].motivo_descarte is MotivoDescarte.PERCEPCAO_INSUFICIENTE


def test_caso5_percepcao_alta_com_escopo_baixo_tambem_nao_passa():
    """Ver com nitidez não basta: tem que ser deste cômodo."""
    evidencias = [evidencia("e1", "f1", percepcao=100, escopo=40)]
    resultado = validar(evidencias, [foto("f1")])

    assert resultado.aceitas == []
    assert evidencias[0].motivo_descarte is MotivoDescarte.ESCOPO_INSUFICIENTE
    assert resultado.conflitos, "o vistoriador precisa saber que isso existe"


# ==========================================================================
# CASO 6 — quantidade ambígua
# ==========================================================================

def test_caso6_quantidade_duvidosa_nao_entra_com_percepcao_baixa():
    evidencias = [evidencia("e1", "f1", categoria="eletrico",
                            observacao="placas de tomada, quantidade incerta",
                            percepcao=45, escopo=98)]
    assert validar(evidencias, [foto("f1")]).aceitas == []


def test_caso6_a_confianca_final_e_a_da_afirmacao_menos_segura():
    evidencias = [evidencia("e1", "f1", percepcao=95, escopo=75)]
    resultado = validar(evidencias, [foto("f1")])
    assert resultado.aceitas[0].confianca_final == 75


# ==========================================================================
# CASO 7 — defeito citado na nota é geral, não vale para todo cômodo
# ==========================================================================

def test_caso7_defeito_sem_evidencia_no_comodo_nao_tem_o_que_sustentar():
    """A nota diz "paredes com furos". Neste cômodo nenhuma foto mostra furo:
    não há evidência de furo, então não há o que a consolidação escreva."""
    evidencias = [evidencia("e1", "f1", observacao="parede em pintura branca")]
    resultado = validar(evidencias, [foto("f1")])

    texto = " ".join(e.observacao for e in resultado.aceitas)
    assert "furo" not in texto


def test_caso7_defeito_visto_no_comodo_sobrevive():
    evidencias = [
        evidencia("e1", "f1", observacao="parede em pintura branca"),
        evidencia("e2", "f1", observacao="furos na parede ao lado da porta"),
    ]
    resultado = validar(evidencias, [foto("f1")])
    assert any("furos" in e.observacao for e in resultado.aceitas)


# ==========================================================================
# Estrutura, região e conversão da resposta do modelo
# ==========================================================================

def test_regiao_valida_e_lida():
    regiao = Regiao.de_dict({"x": 0.05, "y": 0.10, "largura": 0.75, "altura": 0.65})
    assert regiao and regiao.x == 0.05 and regiao.largura == 0.75


@pytest.mark.parametrize("dados", [
    None, {}, {"x": 0.1}, {"x": 0.1, "y": 0.1, "largura": 0, "altura": 0.5},
    {"x": 2.0, "y": 0.1, "largura": 0.5, "altura": 0.5},
    {"x": "a", "y": "b", "largura": "c", "altura": "d"},
])
def test_regiao_invalida_vira_none_em_vez_de_palpite(dados):
    """Regra 9: se o modelo não souber onde está, não inventa."""
    assert Regiao.de_dict(dados) is None


def test_regiao_e_recortada_para_dentro_da_imagem():
    regiao = Regiao.de_dict({"x": 0.8, "y": 0.8, "largura": 0.9, "altura": 0.9})
    assert regiao.largura == pytest.approx(0.2)
    assert regiao.altura == pytest.approx(0.2)


def test_escopo_desconhecido_cai_no_lado_seguro():
    """Resposta que o sistema não entendeu não vira foto válida."""
    analise = analise_de_dict({"escopo": "sei la"}, "f1", COMODO)
    assert analise.escopo is EscopoFoto.FORA_DE_ESCOPO
    assert not analise.utilizavel


@pytest.mark.parametrize("texto,esperado", [
    ("valid", EscopoFoto.VALIDA),
    ("VÁLIDA", EscopoFoto.VALIDA),
    ("partial", EscopoFoto.PARCIAL),
    ("parcial", EscopoFoto.PARCIAL),
    ("out_of_scope", EscopoFoto.FORA_DE_ESCOPO),
])
def test_escopo_aceita_as_duas_grafias(texto, esperado):
    assert analise_de_dict({"escopo": texto}, "f1", COMODO).escopo is esperado


def test_evidencia_de_dict_normaliza_e_limita():
    item = evidencia_de_dict(
        {"categoria": " paredes ", "observacao": "  parede   branca ",
         "confianca_percepcao": 300, "confianca_escopo": "x", "reflexo": 1},
        "e1", "f1",
    )
    assert item.categoria == "paredes"
    assert item.observacao == "parede branca"
    assert item.confianca_percepcao == 100
    assert item.confianca_escopo == 0
    assert item.e_reflexo is True


def test_categoria_inventada_pelo_modelo_e_normalizada():
    """V2: o modelo propõe, o código decide. Categoria fora das oito não
    derruba a evidência — ela é normalizada pelo vocabulário."""
    evidencias = [evidencia("e1", "f1", categoria="quintal",
                            observacao="parede em pintura branca")]
    resultado = validar(evidencias, [foto("f1")])
    assert resultado.aceitas[0].categoria == "paredes"
    assert resultado.aceitas[0].categoria_proposta == "quintal"


def test_observacao_vazia_e_descartada():
    evidencias = [evidencia("e1", "f1", observacao="   ")]
    validar(evidencias, [foto("f1")])
    assert evidencias[0].motivo_descarte is MotivoDescarte.OBSERVACAO_VAZIA


def test_evidencia_sem_analise_da_foto_nao_passa():
    """Sem análise de escopo, a foto não pode alimentar o laudo — é a regra
    40: estar na pasta do cômodo não atribui nada ao cômodo."""
    resultado = validar_escopo([evidencia("e1", "f_desconhecida")], {}, COMODO)
    assert resultado.aceitas == []
    assert resultado.descartadas[0].motivo_descarte is MotivoDescarte.FOTO_FORA_DE_ESCOPO


def test_por_categoria_agrupa_as_oito():
    from core.config import CATEGORIAS
    resultado = validar([evidencia("e1", "f1")], [foto("f1")])
    agrupado = resultado.por_categoria()
    assert set(agrupado) == set(CATEGORIAS)
    assert [e.id for e in agrupado["paredes"]] == ["e1"]


def test_evidencia_serializa_para_o_banco():
    evidencias = [evidencia("e1", "f1", regiao=Regiao(0.1, 0.2, 0.3, 0.4),
                            atributos={"material": "pintura", "cor": "branca"})]
    validar(evidencias, [foto("f1")])
    dados = evidencias[0].para_dict()
    assert dados["id"] == "e1"
    assert dados["regiao"] == {"x": 0.1, "y": 0.2, "largura": 0.3, "altura": 0.4}
    assert dados["status"] == "aceita"
    assert dados["confianca_final"] > 0
    # campos novos da V2
    assert dados["escopo"] == "room_interior"
    assert dados["atributos"] == {"material": "pintura", "cor": "branca"}
    assert dados["instancia"] == 1
    assert dados["e_fronteira"] is False
