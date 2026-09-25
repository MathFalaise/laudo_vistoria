"""
Taxonomia canônica, elementos de fronteira, rodapé, atributos e elétricos.

Cada teste aqui nasceu de um erro REAL do benchmark de 107 fotos (BWC Suíte +
Quarto Suíte, 18/09/2026). Os nomes dizem qual.

Nenhum chama o Gemini: o que está sob teste é a camada determinística.
"""

import pytest

from core.taxonomia import (
    Escopo,
    EstadoRodape,
    atributos_conflitantes,
    categoria_canonica,
    e_cenario_alem_da_abertura,
    e_configuracao_e_nao_quantidade,
    e_elemento_de_fronteira,
    escopo_de_texto,
    estado_do_rodape,
    tipos_eletricos_presentes,
)


# ==========================================================================
# 1 a 7 — categoria canônica
# ==========================================================================

def test_1_soleira_vai_para_porta_mesmo_dividindo_dois_pisos():
    """Benchmark: a V1 mandou a soleira do BWC para Piso e o laudo a perdeu."""
    assert categoria_canonica(
        "piso", "Soleira em granito bege separando o piso do banheiro do piso do quarto"
    ) == "porta"


def test_1b_soleira_continua_porta_mesmo_se_o_modelo_disser_piso():
    assert categoria_canonica("piso", "soleira em granito") == "porta"
    assert categoria_canonica("paredes", "soleira de madeira") == "porta"


def test_2_porta_janela_vai_para_janela():
    """Benchmark: a porta-janela do Quarto Suíte virou 2 conflitos e a
    categoria Janela sumiu do laudo."""
    for observacao in ("porta-janela de correr em alumínio branco",
                       "porta janela que dá para a varanda",
                       "janela-porta de correr"):
        assert categoria_canonica("porta", observacao) == "janela", observacao


def test_3_peitoril_vai_para_janela():
    assert categoria_canonica("piso", "peitoril em granito cinza") == "janela"
    assert categoria_canonica("paredes", "peitoril da janela") == "janela"


def test_4_box_vai_para_mobilia_mesmo_tendo_folhas_de_correr():
    """Benchmark: a V1 mandou o box do BWC para a categoria Porta."""
    assert categoria_canonica(
        "porta", "Box de banheiro com folhas em vidro Blindex verde, trilho e porta de correr"
    ) == "mobilia"


@pytest.mark.parametrize("observacao", [
    "porta-papel higiênico em metal cromado",
    "papeleira de parede",
])
def test_5_porta_papel_vai_para_mobilia(observacao):
    assert categoria_canonica("obs", observacao) == "mobilia"


@pytest.mark.parametrize("observacao", [
    "porta-toalha em metal cromado",
    "toalheiro tipo argola",
])
def test_6_porta_toalha_vai_para_mobilia(observacao):
    assert categoria_canonica("obs", observacao) == "mobilia"


def test_7_ganchos_vao_para_mobilia():
    """Benchmark: a V1 jogou "suportes para toalhas e ganchos" na OBS."""
    assert categoria_canonica("obs", "cinco ganchos cabideiros em metal cromado") == "mobilia"


def test_batente_e_vistas_vao_para_porta():
    assert categoria_canonica("paredes", "batente em madeira escura") == "porta"
    assert categoria_canonica("paredes", "vistas em madeira na cor escura") == "porta"


def test_rodape_vai_para_piso():
    assert categoria_canonica("paredes", "rodapé em madeira clara") == "piso"


def test_categoria_proposta_vale_quando_nao_ha_termo_decisivo():
    assert categoria_canonica("paredes", "parede em pintura lisa branca") == "paredes"
    assert categoria_canonica("teto", "laje pintada de branco") == "teto"


def test_categoria_desconhecida_cai_no_vocabulario():
    assert categoria_canonica("sei la", "uma bancada em granito") == "mobilia"
    assert categoria_canonica("", "tomada de três pinos") == "eletrico"


def test_categoria_sem_pista_vai_para_obs():
    assert categoria_canonica("", "algo que ninguém identificou") == "obs"


def test_a_categoria_devolvida_e_sempre_uma_das_oito():
    from core.config import CATEGORIAS
    for proposta, observacao in [("x", "y"), ("piso", "soleira"), ("", ""),
                                 ("porta", "box de vidro")]:
        assert categoria_canonica(proposta, observacao) in CATEGORIAS


# ==========================================================================
# 8 e 9 — rejunte não é revestimento; rodapé
# ==========================================================================

def test_8_revestimento_branco_com_rejunte_cinza_nao_e_conflito():
    """Benchmark: a V1 abriu conflito falso entre "cerâmica branca" e
    "rejunte cinza" na mesma parede do BWC."""
    a = {"material": "cerâmica", "cor": "branca", "rejunte_cor": "cinza"}
    b = {"material": "cerâmica", "cor": "branca"}
    assert atributos_conflitantes(a, b) == []


def test_8b_cor_do_rejunte_diferente_entre_fotos_e_conflito_do_rejunte():
    a = {"cor": "branca", "rejunte_cor": "cinza"}
    b = {"cor": "branca", "rejunte_cor": "preto"}
    assert atributos_conflitantes(a, b) == ["rejunte_cor"]


def test_9_rodape_ausente_quando_o_revestimento_desce_ate_o_piso():
    """Benchmark: no BWC o azulejo desce até o piso e NÃO há rodapé; os dois
    motores escreveram "com rodapé em cerâmica branca"."""
    assert estado_do_rodape([
        "Piso em cerâmica branca",
        "Paredes em azulejo branco, com o revestimento até o piso, sem rodapé",
    ]) is EstadoRodape.AUSENTE


def test_9b_frase_de_revestimento_ate_o_piso_basta():
    assert estado_do_rodape([
        "azulejo cerâmico que desce até o piso na junção com o piso",
    ]) is EstadoRodape.AUSENTE


def test_10_rodape_de_madeira_e_reconhecido():
    """Benchmark: no Quarto Suíte o rodapé é de madeira clara; o clássico
    escreveu "cerâmica bege" por inferir do piso."""
    assert estado_do_rodape([
        "Piso em cerâmica bege",
        "Rodapé em madeira clara acompanhando os móveis",
    ]) is EstadoRodape.PRESENTE


def test_10b_rodape_nao_visivel_nao_vira_ausente():
    """Não ver não é o mesmo que não haver (item 26)."""
    assert estado_do_rodape(["Piso em cerâmica bege"]) is EstadoRodape.NAO_VISIVEL
    assert estado_do_rodape([]) is EstadoRodape.NAO_VISIVEL


# ==========================================================================
# 11 a 19 — contagem e componentes elétricos
# ==========================================================================

def test_12_tipos_eletricos_sao_extraidos_sem_contagem():
    tipos = tipos_eletricos_presentes([
        "uma tomada estilo três pinos",
        "interruptor simples ao lado da porta",
        "placa cega",
        "ponto de iluminação com plafon",
    ])
    assert set(tipos) >= {"tomada", "interruptor", "placa cega", "ponto de iluminação"}


def test_13_uma_tomada_nao_significa_uma_unica_tomada_no_comodo():
    """Item 18: "uma tomada estilo três pinos" descreve uma INSTÂNCIA."""
    assert e_configuracao_e_nao_quantidade("uma tomada estilo três pinos")


@pytest.mark.parametrize("texto", [
    "tomada dupla", "tomada tripla", "interruptor duplo", "interruptor triplo",
    "módulo com duas saídas", "conjunto de três módulos",
])
def test_14_configuracao_nao_vira_contagem_de_placas(texto):
    assert e_configuracao_e_nao_quantidade(texto)


def test_15_tipos_eletricos_sobrevivem_a_lista_grande():
    tipos = tipos_eletricos_presentes([
        "tomada", "tomada", "tomada", "interruptor", "interruptor",
        "placa cega", "saída de internet RJ45", "quadro de disjuntores",
        "ar-condicionado split", "ventilador de teto",
    ])
    assert set(tipos) >= {
        "tomada", "interruptor", "placa cega", "saída de dados",
        "quadro de disjuntores", "ar-condicionado", "ventilador",
    }


def test_eletrico_sem_evidencia_nao_inventa_tipo():
    assert tipos_eletricos_presentes([]) == []
    assert tipos_eletricos_presentes(["uma bancada em granito"]) == []


# ==========================================================================
# 17 a 21 — fronteira, cenário, escopo
# ==========================================================================

@pytest.mark.parametrize("observacao", [
    "porta em madeira escura com batente e vistas",
    "soleira em granito bege",
    "peitoril em granito cinza",
    "esquadria de alumínio branco",
    "porta-janela de correr que dá para a varanda",
    "trilho da janela de correr",
    "caixilho em alumínio branco",
])
def test_17_elementos_de_fronteira_sao_reconhecidos(observacao):
    assert e_elemento_de_fronteira(observacao), observacao


def test_17b_janela_que_da_para_a_varanda_continua_do_comodo():
    """Benchmark: as duas evidências da porta-janela foram descartadas como
    ambiente adjacente e a categoria Janela sumiu do laudo."""
    observacao = "Esquadria de alumínio branco com vidro transparente voltada para área externa"
    assert e_elemento_de_fronteira(observacao)
    assert categoria_canonica("janela", observacao) == "janela"


def test_18_a_varanda_em_si_continua_fora_do_escopo():
    """A esquadria é do quarto; o que se vê através dela, não."""
    assert e_cenario_alem_da_abertura("telhado do vizinho e o jardim ao fundo")
    assert e_cenario_alem_da_abertura("vista da rua com carros e calçada")


def test_18b_janela_com_vista_descreve_a_janela_nao_o_cenario():
    assert not e_cenario_alem_da_abertura(
        "janela de correr em alumínio branco com vista para o jardim"
    )


def test_19_soleira_entre_dois_pisos_continua_da_porta():
    observacao = "Soleira em granito bege entre o piso do banheiro e o piso do quarto"
    assert e_elemento_de_fronteira(observacao)
    assert categoria_canonica("piso", observacao) == "porta"


@pytest.mark.parametrize("texto,esperado", [
    ("room_interior", Escopo.INTERIOR),
    ("room_boundary", Escopo.FRONTEIRA),
    ("fronteira", Escopo.FRONTEIRA),
    ("adjacent_room", Escopo.ADJACENTE),
    ("outside", Escopo.EXTERIOR),
    ("reflection", Escopo.REFLEXO),
    ("ambiguous", Escopo.AMBIGUO),
])
def test_escopo_le_as_duas_grafias(texto, esperado):
    assert escopo_de_texto(texto) is esperado


def test_20_escopo_desconhecido_cai_em_ambiguo_e_nao_em_interior():
    """Lado seguro: o que o sistema não entendeu vira pendência, não texto."""
    assert escopo_de_texto("sei lá") is Escopo.AMBIGUO
    assert escopo_de_texto("") is Escopo.AMBIGUO


def test_so_interior_e_fronteira_alimentam_o_laudo():
    from core.taxonomia import ESCOPOS_QUE_ALIMENTAM_O_LAUDO
    assert set(ESCOPOS_QUE_ALIMENTAM_O_LAUDO) == {Escopo.INTERIOR, Escopo.FRONTEIRA}
    for fora in (Escopo.ADJACENTE, Escopo.EXTERIOR, Escopo.REFLEXO, Escopo.AMBIGUO):
        assert fora not in ESCOPOS_QUE_ALIMENTAM_O_LAUDO


# ==========================================================================
# 22 — conflito de atributo não invalida os outros
# ==========================================================================

def test_22_conflito_fica_restrito_ao_atributo():
    """Item 30: duas fotos discordam só das dobradiças; a porta continua."""
    a = {"material": "madeira", "cor": "branca", "acabamento": "dourado"}
    b = {"material": "madeira", "cor": "branca", "acabamento": "cromado"}
    assert atributos_conflitantes(a, b) == ["acabamento"]


def test_22b_atributo_ausente_de_um_lado_nao_e_conflito():
    a = {"material": "madeira", "cor": "branca", "estado": "bom"}
    b = {"material": "madeira"}
    assert atributos_conflitantes(a, b) == []


def test_22c_refinamento_de_valor_nao_e_conflito():
    a = {"cor": "branco"}
    b = {"cor": "branco gelo"}
    assert atributos_conflitantes(a, b) == []


def test_22d_conflito_real_de_material():
    a = {"material": "cerâmica"}
    b = {"material": "pintura"}
    assert atributos_conflitantes(a, b) == ["material"]


def test_22e_conflito_real_de_cor():
    a = {"cor": "branca"}
    b = {"cor": "vermelha"}
    assert atributos_conflitantes(a, b) == ["cor"]


def test_genero_nao_cria_conflito_falso():
    assert atributos_conflitantes({"cor": "branco"}, {"cor": "branca"}) == []
    assert atributos_conflitantes({"material": "cerâmico"}, {"material": "cerâmica"}) == []


def test_atributo_fora_da_lista_conhecida_e_ignorado():
    a = {"comentario_livre": "abc"}
    b = {"comentario_livre": "xyz"}
    assert atributos_conflitantes(a, b) == []
