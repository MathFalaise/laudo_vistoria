"""
Pipeline V2 completo, do arquivo de foto ao texto do laudo, com o Gemini
MOCKADO.

O que está sob teste é o CAMINHO, não o modelo: as fotos viram evidências
exaustivas, o código valida escopo e recupera elementos de fronteira, a
checklist de cobertura dispara busca dirigida, e só então alguém escreve.
"""

import json

import pytest
from PIL import Image

import core.pipeline as pipeline
from core.config import CATEGORIAS
from core.evidencias import MotivoDescarte, TipoConflito
from core.taxonomia import Escopo


# --------------------------------------------------------------------------
# Gemini falso
# --------------------------------------------------------------------------

class _Resposta:
    def __init__(self, texto):
        self.text = texto
        self.candidates = []


class _Models:
    def __init__(self, roteiro):
        self.roteiro = roteiro
        self.chamadas = []

    def generate_content(self, model, contents, config):
        prompt = next(p for p in reversed(contents) if isinstance(p, str))
        imagens = sum(1 for p in contents if not isinstance(p, str))
        if "Esta etapa NÃO escreve laudo" in prompt:
            etapa = "evidencias"
        elif "Segunda passagem nas MESMAS fotos" in prompt:
            etapa = "dirigida"
        elif "Abaixo estão as EVIDÊNCIAS já validadas" in prompt:
            etapa = "consolidacao"
        else:
            etapa = "outra"
        self.chamadas.append({"etapa": etapa, "imagens": imagens, "prompt": prompt})
        resposta = self.roteiro.get(etapa, {"evidencias": []})
        if callable(resposta):
            resposta = resposta(prompt)
        return _Resposta(json.dumps(resposta, ensure_ascii=False))


class _Cliente:
    def __init__(self, roteiro):
        self.models = _Models(roteiro)


def laudo(**categorias):
    dados = {c: [{"texto": "Não se aplica.", "motivo": "", "certeza": 95}]
             for c in CATEGORIAS}
    for categoria, texto in categorias.items():
        dados[categoria] = [{"texto": texto, "motivo": "", "certeza": 95}]
    return dados


def evidencia(foto, categoria, observacao, escopo="room_interior",
              percepcao=95, conf_escopo=95, **extra):
    item = {"foto_indice": foto, "categoria": categoria, "observacao": observacao,
            "escopo": escopo, "confianca_percepcao": percepcao,
            "confianca_escopo": conf_escopo}
    item.update(extra)
    return item


def fotos_validas(quantidade):
    return [{"indice": i, "escopo": "valid", "relevancia": 95,
             "ambiente_adjacente": False, "reflexo": False, "motivo": "ok"}
            for i in range(1, quantidade + 1)]


@pytest.fixture
def pasta(tmp_path):
    destino = tmp_path / "BWC Suíte"
    destino.mkdir()
    for nome in ("f1.jpg", "f2.jpg", "f3.jpg"):
        Image.new("RGB", (64, 48), "white").save(destino / nome, "JPEG")
    return str(destino)


# ==========================================================================
# Fronteira recuperada — a perda nº 1 da V1
# ==========================================================================

def test_soleira_classificada_como_adjacente_chega_ao_laudo(pasta):
    """Benchmark: a V1 perdeu a soleira do BWC porque o modelo a chamou de
    ambiente adjacente. Aqui o código a recupera e ela vai para Porta."""
    cliente = _Cliente({
        "evidencias": {
            "fotos": fotos_validas(3),
            "evidencias": [
                evidencia(1, "porta", "Porta em madeira escura almofadada",
                          escopo="room_boundary",
                          atributos={"material": "madeira", "cor": "escura"}),
                # o modelo erra aqui: manda para piso e chama de adjacente
                evidencia(1, "piso",
                          "Soleira em granito bege separando o piso do banheiro do quarto",
                          escopo="adjacent_room", conf_escopo=80),
            ],
        },
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(
            porta="*Uma porta em madeira na cor escura, tipo almofadada, com soleira "
                  "em granito na cor bege, em bom estado."),
    })

    resultado = pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")

    recuperada = next(e for e in resultado.evidencias if "Soleira" in e.observacao)
    assert recuperada.aceita
    assert recuperada.escopo is Escopo.FRONTEIRA
    assert recuperada.escopo_original is Escopo.ADJACENTE
    assert recuperada.categoria == "porta"

    prompt = next(c["prompt"] for c in cliente.models.chamadas
                  if c["etapa"] == "consolidacao")
    assert "Soleira em granito bege" in prompt
    assert "soleira em granito na cor bege" in resultado.dados["porta"]


def test_porta_janela_para_a_varanda_vira_categoria_janela(pasta):
    """Benchmark: a categoria Janela do Quarto Suíte sumiu inteira."""
    cliente = _Cliente({
        "evidencias": {
            "fotos": fotos_validas(3),
            "evidencias": [
                evidencia(1, "porta",
                          "Porta-janela de correr em alumínio branco que dá para a varanda",
                          escopo="adjacent_room", conf_escopo=70),
            ],
        },
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(
            janela="*Uma janela-porta em alumínio na cor branca, do tipo de correr, "
                   "em bom estado."),
    })
    resultado = pipeline.processar_comodo_v2(cliente, pasta, "Quarto Suíte")

    evidencia_janela = resultado.evidencias[0]
    assert evidencia_janela.categoria == "janela"
    assert evidencia_janela.escopo is Escopo.FRONTEIRA
    assert "janela-porta" in resultado.dados["janela"]


def test_parede_de_ambiente_vizinho_continua_fora(pasta):
    """A recuperação não pode virar porta dos fundos."""
    cliente = _Cliente({
        "evidencias": {
            "fotos": fotos_validas(3),
            "evidencias": [
                evidencia(1, "paredes", "Paredes em azulejo branco",
                          atributos={"material": "cerâmica", "cor": "branca"}),
                evidencia(2, "paredes", "Parede em pintura cinza do corredor",
                          escopo="adjacent_room", conf_escopo=20),
            ],
        },
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(paredes="*Paredes em azulejo na cor branca, em bom estado."),
    })
    resultado = pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")

    fora = next(e for e in resultado.evidencias if "corredor" in e.observacao)
    assert not fora.aceita
    assert fora.motivo_descarte is MotivoDescarte.AMBIENTE_ADJACENTE
    prompt = next(c["prompt"] for c in cliente.models.chamadas
                  if c["etapa"] == "consolidacao")
    assert "corredor" not in prompt


# ==========================================================================
# Cobertura e busca dirigida — a perda nº 2 da V1
# ==========================================================================

def test_lacuna_dispara_busca_dirigida_e_o_item_entra(pasta):
    """Benchmark: porta-papel, ganchos e toalheiro sumiram da V1 sem que
    nada no sistema reclamasse."""
    cliente = _Cliente({
        "evidencias": {
            "fotos": fotos_validas(3),
            "evidencias": [
                evidencia(1, "mobilia", "Bacia sanitária em louça branca"),
                evidencia(1, "mobilia", "Bancada em granito com cuba oval"),
                evidencia(1, "mobilia", "Chuveiro em metal cromado"),
                evidencia(1, "mobilia", "Box em vidro verde"),
                evidencia(1, "mobilia", "Espelho circular"),
                evidencia(1, "piso", "Piso em cerâmica branca"),
                evidencia(1, "teto", "Teto em laje pintada"),
                evidencia(1, "paredes", "Paredes em azulejo branco"),
                evidencia(1, "porta", "Porta em madeira com batente"),
                evidencia(1, "eletrico", "Ponto de iluminação com plafon"),
                evidencia(1, "eletrico", "Placa com tomada"),
                evidencia(1, "janela", "Janela basculante em alumínio"),
            ],
        },
        # a busca dirigida acha os acessórios que a primeira passagem perdeu
        "dirigida": {
            "evidencias": [
                evidencia(2, "mobilia", "Porta-papel higiênico em metal cromado"),
                evidencia(2, "mobilia", "Toalheiro em argola cromado"),
                evidencia(2, "mobilia", "Cinco ganchos cabideiros em metal cromado"),
                evidencia(2, "mobilia", "Saboneteira de parede em metal"),
            ],
        },
        "consolidacao": laudo(
            mobilia="*Um porta-papel higiênico em metal cromado, em bom estado."),
    })

    resultado = pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")

    dirigidas = [c for c in cliente.models.chamadas if c["etapa"] == "dirigida"]
    assert dirigidas, "a lacuna tinha que disparar busca dirigida"

    achados = [e.observacao for e in resultado.evidencias if e.id.startswith("d")]
    assert any("Porta-papel" in o for o in achados)
    assert any("ganchos" in o for o in achados)

    prompt = next(c["prompt"] for c in cliente.models.chamadas
                  if c["etapa"] == "consolidacao")
    for peca in ("Porta-papel", "Toalheiro", "ganchos", "Saboneteira"):
        assert peca in prompt, peca


def test_busca_dirigida_vazia_vira_pendencia_e_nao_item_inventado(pasta):
    """Item 22: a cobertura levanta DÚVIDA, nunca afirma que existe."""
    cliente = _Cliente({
        "evidencias": {
            "fotos": fotos_validas(3),
            "evidencias": [evidencia(1, "paredes", "Paredes em azulejo branco")],
        },
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(paredes="*Paredes em azulejo na cor branca, em bom estado."),
    })
    resultado = pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")

    cobertura = [c for c in resultado.conflitos if c.tipo is TipoConflito.COBERTURA]
    assert cobertura, "a lacuna não resolvida tem que virar pendência"
    assert any("não encontrei evidência" in c.resumo for c in cobertura)
    assert all("NÃO quer dizer que não exista" in c.resumo for c in cobertura)


def test_busca_dirigida_e_limitada(pasta, monkeypatch):
    """Cada busca reenvia as fotos: é a parte cara do motor."""
    monkeypatch.setattr("core.config.MAX_SEGUNDAS_OLHADAS_DIRIGIDAS", 1)
    cliente = _Cliente({
        "evidencias": {"fotos": fotos_validas(3),
                       "evidencias": [evidencia(1, "paredes", "Paredes brancas")]},
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(),
    })
    pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")
    assert len([c for c in cliente.models.chamadas if c["etapa"] == "dirigida"]) == 1


# ==========================================================================
# Elétricos: composição, não contagem
# ==========================================================================

def test_a_redacao_recebe_os_tipos_eletricos_e_a_regra_de_composicao(pasta):
    cliente = _Cliente({
        "evidencias": {
            "fotos": fotos_validas(3),
            "evidencias": [
                evidencia(1, "eletrico", "Placa com uma tomada estilo três pinos",
                          instancia=1),
                evidencia(1, "eletrico", "Placa com interruptor simples", instancia=2),
                evidencia(2, "eletrico", "Placa cega", instancia=3),
                evidencia(2, "eletrico", "Saída de internet RJ45", instancia=4),
            ],
        },
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(
            eletrico="*Com placas em polímero na cor branca, sendo tomadas, "
                     "interruptores, placa cega e saída de dados, em bom estado."),
    })
    pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")

    prompt = next(c["prompt"] for c in cliente.models.chamadas
                  if c["etapa"] == "consolidacao")
    assert "tomada" in prompt and "interruptor" in prompt
    assert "placa cega" in prompt and "saída de dados" in prompt
    assert "NÃO é obrigatório escrever" in prompt
    assert "CONFIGURAÇÕES da peça, não quantidade de placas" in prompt


def test_instancias_sao_preservadas_internamente(pasta):
    """Item 17: a contagem existe no sistema mesmo sem virar número no texto."""
    cliente = _Cliente({
        "evidencias": {
            "fotos": fotos_validas(3),
            "evidencias": [
                evidencia(1, "eletrico", "Placa com tomada", instancia=i)
                for i in range(1, 5)
            ],
        },
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(eletrico="*Com placas em polímero na cor branca, "
                                       "sendo tomadas, em bom estado."),
    })
    resultado = pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")
    eletricas = [e for e in resultado.evidencias if e.categoria == "eletrico"]
    assert sorted(e.instancia for e in eletricas) == [1, 2, 3, 4]
    # e o texto não é obrigado a dizer "quatro placas"
    assert "quatro" not in resultado.dados["eletrico"].lower()


# ==========================================================================
# Rodapé
# ==========================================================================

def test_rodape_ausente_e_informado_a_redacao(pasta):
    """Benchmark: os dois motores escreveram "com rodapé em cerâmica branca"
    num BWC em que o azulejo desce até o piso."""
    cliente = _Cliente({
        "evidencias": {
            "fotos": fotos_validas(3),
            "evidencias": [
                evidencia(1, "piso", "Piso em cerâmica branca"),
                evidencia(1, "paredes",
                          "Azulejo branco que desce até o piso, sem rodapé"),
            ],
        },
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(piso="*Piso em cerâmica na cor branca, em bom estado."),
    })
    pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")
    prompt = next(c["prompt"] for c in cliente.models.chamadas
                  if c["etapa"] == "consolidacao")
    assert "NÃO escreva rodapé" in prompt


def test_rodape_nao_visivel_manda_omitir(pasta):
    cliente = _Cliente({
        "evidencias": {
            "fotos": fotos_validas(3),
            "evidencias": [evidencia(1, "piso", "Piso em cerâmica bege")],
        },
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(piso="*Piso em cerâmica na cor bege, em bom estado."),
    })
    pipeline.processar_comodo_v2(cliente, pasta, "Quarto Suíte")
    prompt = next(c["prompt"] for c in cliente.models.chamadas
                  if c["etapa"] == "consolidacao")
    assert "NÃO afirme que há rodapé nem que não há" in prompt


# ==========================================================================
# Custo e contrato
# ==========================================================================

def test_cada_foto_vai_uma_vez_na_extracao(pasta):
    cliente = _Cliente({
        "evidencias": {"fotos": fotos_validas(3),
                       "evidencias": [evidencia(1, "paredes", "Paredes brancas")]},
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(),
    })
    pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")
    extracao = [c for c in cliente.models.chamadas if c["etapa"] == "evidencias"]
    assert sum(c["imagens"] for c in extracao) == 3


def test_a_redacao_nao_recebe_fotos(pasta):
    """Item 32: quem escreve não vê as imagens, só as evidências aprovadas."""
    cliente = _Cliente({
        "evidencias": {"fotos": fotos_validas(3),
                       "evidencias": [evidencia(1, "paredes", "Paredes brancas")]},
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(),
    })
    pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")
    redacao = next(c for c in cliente.models.chamadas if c["etapa"] == "consolidacao")
    assert redacao["imagens"] == 0


def test_sem_evidencia_aprovada_o_laudo_nao_e_escrito(pasta):
    cliente = _Cliente({
        "evidencias": {
            "fotos": [{"indice": i, "escopo": "out_of_scope", "relevancia": 0,
                       "ambiente_adjacente": True, "reflexo": False,
                       "motivo": "não é este cômodo"} for i in (1, 2, 3)],
            "evidencias": [evidencia(1, "paredes", "Paredes brancas")],
        },
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(),
    })
    resultado = pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")
    assert not any(c["etapa"] == "consolidacao" for c in cliente.models.chamadas)
    assert all(not texto for texto in resultado.dados.values())
    assert "nenhuma evidência" in resultado.incertos[0]["motivo"]


def test_resultado_serializa_com_os_campos_novos(pasta):
    cliente = _Cliente({
        "evidencias": {
            "fotos": fotos_validas(3),
            "evidencias": [
                evidencia(1, "piso", "Soleira em granito bege", escopo="adjacent_room",
                          conf_escopo=80, atributos={"material": "granito", "cor": "bege"}),
            ],
        },
        "dirigida": {"evidencias": []},
        "consolidacao": laudo(porta="*Uma porta com soleira em granito, em bom estado."),
    })
    resultado = pipeline.processar_comodo_v2(cliente, pasta, "BWC Suíte")
    como_dict = resultado.para_dict()
    assert json.dumps(como_dict, ensure_ascii=False)
    evidencia_json = como_dict["evidencias"][0]
    assert evidencia_json["escopo"] == "room_boundary"
    assert evidencia_json["escopo_original"] == "adjacent_room"
    assert evidencia_json["categoria"] == "porta"
    assert evidencia_json["categoria_proposta"] == "piso"
    assert evidencia_json["atributos"] == {"material": "granito", "cor": "bege"}
