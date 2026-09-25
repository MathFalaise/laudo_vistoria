"""
Testes de REGRESSÃO do motor atual, escritos ANTES da evolução arquitetural
(regra 44 do pedido: nenhuma mudança pode quebrar regra já validada sem
evidência explícita).

Eles descrevem o comportamento que o sistema tinha em 25/09/2026, depois de
várias vistorias reais. Se um destes testes quebrar durante a migração, é a
migração que está errada — não o teste.

Nada aqui chama a API do Gemini.
"""

import pytest

import config
import report_writer
import style_guide
import validacao
from gemini_client import _montar_categoria, _registros, pendencias_itens_repetidos


# --------------------------------------------------------------------------
# Categorias e ordem
# --------------------------------------------------------------------------

def test_categorias_e_ordem_sao_as_oito_atuais():
    assert config.CATEGORIAS == [
        "paredes", "piso", "teto", "porta", "janela", "eletrico", "mobilia", "obs"
    ]


def test_rotulos_de_exibicao():
    assert config.ROTULOS_CATEGORIA["eletrico"] == "Componentes Elétricos"
    assert config.ROTULOS_CATEGORIA["mobilia"] == "Mobília"
    assert config.ROTULOS_CATEGORIA["obs"] == "OBS"


def test_limiares():
    assert config.LIMIAR_CERTEZA == 85
    assert config.LIMIAR_CORRECAO_AUTOMATICA == 50
    assert config.LIMIAR_CONFERENCIA == 70


def test_limiares_nao_aparecem_no_prompt():
    """O corte fica só no código: se o modelo souber o número, responde logo
    acima dele."""
    prompt = style_guide.montar_prompt_comodo("Cozinha", config.CATEGORIAS)
    for limiar in (config.LIMIAR_CERTEZA, config.LIMIAR_CORRECAO_AUTOMATICA,
                   config.LIMIAR_CONFERENCIA):
        assert f"{limiar}%" not in prompt


# --------------------------------------------------------------------------
# Formatação do item
# --------------------------------------------------------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("Uma porta em madeira.", "*Uma porta em madeira."),
    ("*Uma porta em madeira.", "*Uma porta em madeira."),
    ("  *  Uma   porta  em madeira. ", "*Uma porta em madeira."),
    ("Não se aplica.", "Não se aplica."),
    ("*Não se aplica.", "Não se aplica."),
    ("Sem observações.", "Sem observações."),
    ("", ""),
])
def test_normalizar_linha(entrada, esperado):
    assert report_writer.normalizar_linha(entrada) == esperado


def test_texto_vazio_por_categoria():
    assert report_writer.texto_vazio_da_categoria("obs") == "Sem observações."
    assert report_writer.texto_vazio_da_categoria("janela") == "Não se aplica."


def test_montar_texto_comodo_sem_linha_em_branco_entre_itens():
    dados = {"paredes": "*Paredes em pintura branca, em bom estado.\n"
                        "*Uma parede em azulejo, em bom estado."}
    texto = report_writer.montar_texto_comodo("Cozinha", dados)
    assert "*Paredes em pintura branca, em bom estado.\n*Uma parede em azulejo, em bom estado." in texto
    assert texto.startswith("COZINHA")


def test_categoria_nao_se_aplica_some_do_txt():
    """"Não se aplica." não vira bloco vazio no laudo — a categoria some."""
    dados = {"paredes": "*Paredes brancas.", "janela": "Não se aplica."}
    texto = report_writer.montar_texto_comodo("Cozinha", dados)
    assert "Janela:" not in texto
    assert "Paredes:" in texto


def test_sem_observacoes_permanece_no_txt():
    """"Sem observações." aparece: confirma que o vistoriador olhou."""
    dados = {"obs": "Sem observações."}
    texto = report_writer.montar_texto_comodo("Cozinha", dados)
    assert "OBS:" in texto and "Sem observações." in texto


def test_ida_e_volta_do_txt_do_comodo(tmp_path):
    dados = {
        "paredes": "*Paredes em pintura branca, em bom estado.",
        "piso": "*Piso em cerâmica, em bom estado.",
        "obs": "Sem observações.",
    }
    report_writer.salvar_txt_comodo(str(tmp_path), "Cozinha", dados)
    lido = report_writer.parsear_txt_comodo(str(tmp_path / "Cozinha_vistoria.txt"))
    assert lido["paredes"] == dados["paredes"]
    assert lido["piso"] == dados["piso"]
    assert lido["obs"] == dados["obs"]


# --------------------------------------------------------------------------
# TESTES elétricos/hidráulicos — trava determinística
# --------------------------------------------------------------------------

@pytest.mark.parametrize("categoria", ["paredes", "piso", "teto", "porta", "janela", "obs"])
def test_frase_de_teste_sai_das_categorias_que_nao_se_testam(categoria):
    linha = "*Item qualquer em material, testado e em funcionamento, em bom estado."
    assert "testado e em funcionamento" not in report_writer.limpar_testes_indevidos(categoria, linha)


def test_frase_de_teste_sai_da_mobilia_sem_funcao_eletrica_ou_hidraulica():
    linha = "*Um armário em MDF na cor branca, testado e em funcionamento, em bom estado."
    limpo = report_writer.limpar_testes_indevidos("mobilia", linha)
    assert limpo == "*Um armário em MDF na cor branca, em bom estado."


def test_frase_de_teste_fica_na_peca_hidraulica():
    linha = "*Uma torneira em metal cromado, testada e em funcionamento, em bom estado."
    assert report_writer.limpar_testes_indevidos("mobilia", linha) == linha


def test_frase_de_teste_fica_no_eletrico():
    linha = "*Três placas em polímero, testadas e em funcionamento, em bom estado."
    assert report_writer.limpar_testes_indevidos("eletrico", linha) == linha


def test_tanque_bancada_cuba_e_pia_nao_sao_testados():
    """Regra do vistoriador, 22/09/2026: quem é testado é a torneira."""
    for peca in ("tanque", "bancada", "cuba", "pia"):
        linha = f"*Um(a) {peca} em granito, testado e em funcionamento, em bom estado."
        assert "em funcionamento" not in report_writer.limpar_testes_indevidos("mobilia", linha)


def test_bancada_com_torneira_mantem_o_teste():
    """A linha tem torneira: o teste é da torneira, e continua."""
    linha = ("*Uma bancada em granito na cor preta, com cuba em aço inox e torneira "
             "em metal cromado, testada e em funcionamento, em bom estado.")
    assert report_writer.limpar_testes_indevidos("mobilia", linha) == linha


# --------------------------------------------------------------------------
# ITENS REPETIDOS
# --------------------------------------------------------------------------

@pytest.mark.parametrize("linha", [
    "*Mais uma porta em madeira.",
    "*Mais um armário em MDF.",
    "*Mais dois pontos de luz.",
    "*mais três placas.",
])
def test_linha_com_mais_um_detectada(linha):
    assert report_writer.linha_com_mais_um(linha)


def test_linha_normal_nao_e_mais_um():
    assert not report_writer.linha_com_mais_um("*Duas portas em madeira.")


def test_grupos_de_itens_repetidos_agrupa_mesmo_substantivo():
    linhas = [
        "*Um armário em MDF inferior com duas portas.",
        "*Um armário aéreo em MDF com duas portas.",
        "*Uma bancada em granito.",
    ]
    grupos = report_writer.grupos_de_itens_repetidos(linhas)
    assert grupos == [[0, 1]]


def test_mais_um_vira_pendencia_junto_com_a_linha_anterior():
    registros = [
        ("*Uma porta em madeira na cor branca.", 100, ""),
        ("*Mais uma porta em madeira na cor branca.", 100, ""),
    ]
    texto, pendencias = _montar_categoria("porta", registros)
    assert len(pendencias) == 1
    assert pendencias[0]["certeza"] == 0
    assert pendencias[0]["texto"].count("\n") == 1
    assert "Mais um" in pendencias[0]["motivo"]


def test_substantivo_repetido_sem_mais_um_nao_vira_pendencia():
    """Decisão do vistoriador em 22/09/2026: a heurística de substantivo é
    palpite e já errou (bancada com cuba x bancada de apoio)."""
    registros = [
        ("*Uma bancada em granito com cuba em aço inox.", 100, ""),
        ("*Uma bancada de apoio em granito.", 100, ""),
    ]
    _, pendencias = _montar_categoria("mobilia", registros)
    assert pendencias == []


def test_pendencias_itens_repetidos_em_texto_pronto():
    texto = "*Uma placa em polímero.\n*Mais uma placa em polímero."
    assert len(pendencias_itens_repetidos("eletrico", texto)) == 1


# --------------------------------------------------------------------------
# Sistema de certeza
# --------------------------------------------------------------------------

def test_item_abaixo_do_limiar_vira_pendencia_mas_fica_no_laudo():
    registros = [("*Uma porta em madeira na cor branca.", 60, "a roseta mal aparece")]
    texto, pendencias = _montar_categoria("porta", registros)
    assert texto == "*Uma porta em madeira na cor branca."   # continua no laudo
    assert len(pendencias) == 1
    assert pendencias[0]["certeza"] == 60
    assert pendencias[0]["motivo"] == "a roseta mal aparece"


def test_item_acima_do_limiar_nao_vira_pendencia():
    registros = [("*Uma porta em madeira na cor branca.", 95, "")]
    texto, pendencias = _montar_categoria("porta", registros)
    assert texto == "*Uma porta em madeira na cor branca."
    assert pendencias == []


def test_categoria_sem_registros_vira_pendencia_de_certeza_zero():
    texto, pendencias = _montar_categoria("janela", [])
    assert texto == "Não se aplica."
    assert pendencias[0]["certeza"] == 0


def test_nao_se_aplica_com_certeza_baixa_vira_pendencia():
    registros = [("Não se aplica.", 40, "as fotos não mostram o cômodo inteiro")]
    texto, pendencias = _montar_categoria("janela", registros)
    assert texto == "Não se aplica."
    assert len(pendencias) == 1


def test_nao_se_aplica_nao_convive_com_item_real():
    registros = [
        ("Não se aplica.", 90, ""),
        ("*Uma janela em alumínio na cor branca.", 95, ""),
    ]
    texto, _ = _montar_categoria("janela", registros)
    assert texto == "*Uma janela em alumínio na cor branca."


def test_registros_normaliza_e_limita_certeza():
    itens = [
        {"texto": "Uma porta.", "motivo": "  x  y ", "certeza": 300},
        {"texto": "Outra porta.", "motivo": "", "certeza": "nao numero"},
    ]
    registros = _registros(itens)
    assert registros[0] == ("*Uma porta.", 100, "x y")
    assert registros[1] == ("*Outra porta.", 0, "")


def test_registros_quebra_texto_multilinha_em_varias_linhas():
    itens = [{"texto": "Uma porta.\nUma janela.", "motivo": "", "certeza": 90}]
    assert len(_registros(itens)) == 2


# --------------------------------------------------------------------------
# Validação humana: OK / CORRIGIR / REMOVER
# --------------------------------------------------------------------------

def test_decisao_ok_nao_altera_o_texto():
    pendencia = {"texto": "*Uma porta em madeira.", "decisao": "OK"}
    novo, erro = validacao.aplicar_no_texto("*Uma porta em madeira.", "porta", pendencia)
    assert erro is None
    assert novo == "*Uma porta em madeira."


def test_decisao_corrigir_troca_a_linha():
    pendencia = {"texto": "*Uma porta em madeira.", "decisao": "CORRIGIR",
                 "correcao": "*Uma porta em alumínio."}
    novo, erro = validacao.aplicar_no_texto("*Uma porta em madeira.", "porta", pendencia)
    assert erro is None
    assert novo == "*Uma porta em alumínio."


def test_decisao_corrigir_sem_correcao_e_erro():
    pendencia = {"texto": "*Uma porta em madeira.", "decisao": "CORRIGIR", "correcao": ""}
    _, erro = validacao.aplicar_no_texto("*Uma porta em madeira.", "porta", pendencia)
    assert erro and "CORREÇÃO" in erro


def test_decisao_remover_tira_a_linha_e_deixa_texto_vazio_certo():
    pendencia = {"texto": "*Uma porta em madeira.", "decisao": "REMOVER"}
    novo, erro = validacao.aplicar_no_texto("*Uma porta em madeira.", "porta", pendencia)
    assert erro is None
    assert novo == "Não se aplica."


def test_corrigir_varias_linhas_vira_uma_so():
    texto = "*Uma porta em madeira.\n*Mais uma porta em madeira."
    pendencia = {"texto": texto, "decisao": "CORRIGIR", "correcao": "*Duas portas em madeira."}
    novo, erro = validacao.aplicar_no_texto(texto, "porta", pendencia)
    assert erro is None
    assert novo == "*Duas portas em madeira."


def test_item_que_nao_existe_mais_no_laudo_devolve_erro():
    pendencia = {"texto": "*Uma porta que sumiu.", "decisao": "OK"}
    _, erro = validacao.aplicar_no_texto("*Outra porta.", "porta", pendencia)
    assert erro and "não encontrado" in erro


# --- pendência tipo "falta" (proposta da conferência) ---

def test_falta_com_ok_acrescenta_ao_laudo():
    pendencia = {"texto": "*Um varal de teto.", "tipo": "falta", "decisao": "OK"}
    novo, erro = validacao.aplicar_no_texto("*Uma bancada.", "mobilia", pendencia)
    assert erro is None
    assert novo == "*Uma bancada.\n*Um varal de teto."


def test_falta_com_remover_descarta_a_proposta():
    pendencia = {"texto": "*Um varal de teto.", "tipo": "falta", "decisao": "REMOVER"}
    novo, erro = validacao.aplicar_no_texto("*Uma bancada.", "mobilia", pendencia)
    assert erro is None
    assert novo == "*Uma bancada."


def test_falta_com_corrigir_acrescenta_o_texto_do_vistoriador():
    pendencia = {"texto": "*Um varal.", "tipo": "falta", "decisao": "CORRIGIR",
                 "correcao": "*Um varal de teto em alumínio."}
    novo, erro = validacao.aplicar_no_texto("*Uma bancada.", "mobilia", pendencia)
    assert erro is None
    assert novo.endswith("*Um varal de teto em alumínio.")


def test_falta_substitui_o_texto_de_categoria_vazia():
    pendencia = {"texto": "*Um gancho na parede.", "tipo": "falta", "decisao": "OK"}
    novo, erro = validacao.aplicar_no_texto("Sem observações.", "obs", pendencia)
    assert erro is None
    assert novo == "*Um gancho na parede."


# --------------------------------------------------------------------------
# Arquivo de pendências: ida e volta
# --------------------------------------------------------------------------

def test_salvar_e_ler_pendencias(tmp_path):
    pendencias = [{
        "comodo": "Cozinha", "categoria": "porta", "certeza": 60,
        "motivo": "a roseta mal aparece", "texto": "*Uma porta em madeira.",
    }]
    validacao.salvar_pendencias(str(tmp_path), pendencias)
    lidas = validacao.ler_pendencias(str(tmp_path))
    assert len(lidas) == 1
    assert lidas[0]["comodo"] == "Cozinha"
    assert lidas[0]["categoria"] == "porta"          # rótulo volta a ser chave
    assert lidas[0]["texto"] == "*Uma porta em madeira."
    assert lidas[0]["certeza"] == "60"


def test_pendencia_de_varias_linhas_sobrevive_ao_arquivo(tmp_path):
    pendencias = [{
        "comodo": "Sala", "categoria": "porta", "certeza": 0, "motivo": "x",
        "texto": "*Uma porta.\n*Mais uma porta.",
    }]
    validacao.salvar_pendencias(str(tmp_path), pendencias)
    lidas = validacao.ler_pendencias(str(tmp_path))
    assert lidas[0]["texto"] == "*Uma porta.\n*Mais uma porta."


def test_tipo_falta_sobrevive_ao_arquivo(tmp_path):
    pendencias = [{
        "comodo": "Sala", "categoria": "mobilia", "certeza": 90, "motivo": "x",
        "texto": "*Um varal.", "tipo": "falta",
    }]
    validacao.salvar_pendencias(str(tmp_path), pendencias)
    assert validacao.ler_pendencias(str(tmp_path))[0]["tipo"] == "falta"


def test_decisao_e_lida_sem_acento_e_em_maiuscula(tmp_path):
    caminho = tmp_path / validacao.NOME_ARQUIVO_PENDENCIAS
    caminho.write_text(
        "cabeçalho\n\n--- #1 ---\nCômodo: Sala\nCategoria: Porta\nCerteza: 60%\n"
        "Motivo: x\nItem: *Uma porta.\nDECISÃO: corrigir\nCORREÇÃO: *Outra porta.\nREGRA:\n",
        encoding="utf-8",
    )
    assert validacao.ler_pendencias(str(tmp_path))[0]["decisao"] == "CORRIGIR"


def test_arquivo_sem_pendencia_diz_isso(tmp_path):
    validacao.salvar_pendencias(str(tmp_path), [])
    conteudo = (tmp_path / validacao.NOME_ARQUIVO_PENDENCIAS).read_text(encoding="utf-8")
    assert "Nenhuma pendência em aberto." in conteudo
    assert validacao.ler_pendencias(str(tmp_path)) == []


# --------------------------------------------------------------------------
# Regras adotadas
# --------------------------------------------------------------------------

def test_regras_validadas_entram_no_prompt():
    regras = style_guide.carregar_regras_validadas()
    assert regras, "o repositório já tem regras adotadas"
    prompt = style_guide.montar_prompt_comodo("Cozinha", config.CATEGORIAS)
    assert "REGRAS ADOTADAS PELO VISTORIADOR" in prompt
    assert regras[0][:60] in prompt


def test_regra_do_vaso_sanitario_esta_adotada():
    texto = " ".join(style_guide.carregar_regras_validadas()).lower()
    assert "vaso sanitário" in texto and "mobília" in texto


def test_prompt_traz_as_regras_gerais_criticas():
    prompt = style_guide.montar_prompt_comodo("Cozinha", config.CATEGORIAS)
    for trecho in ("A FOTO MANDA, A NOTA ORIENTA", "DEFEITO NÃO SE ESPALHA",
                   "ITENS REPETIDOS", "TESTES", "Não se aplica.", "Sem observações."):
        assert trecho in prompt


def test_notas_extras_entram_no_prompt():
    prompt = style_guide.montar_prompt_comodo("Cozinha", config.CATEGORIAS,
                                              "Paredes na cor Branco Gelo.")
    assert "Branco Gelo" in prompt
