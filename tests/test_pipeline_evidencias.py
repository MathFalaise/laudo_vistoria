"""
Pipeline completo do cômodo, do arquivo de foto até o texto do laudo, com o
Gemini MOCKADO (nenhum teste desta suíte chama a API).

O que está sob teste não é o modelo — é o caminho: as fotos viram evidências,
o código valida o escopo, e só o que passou chega a quem escreve. O teste
central é `test_parede_do_corredor_nao_entra_no_laudo_da_cozinha`: ele é o
critério de aceitação principal da regra 47 do pedido, escrito em código.
"""

import json

import pytest
from PIL import Image

import core.pipeline as pipeline
from core.evidencias import EscopoFoto, MotivoDescarte


# --------------------------------------------------------------------------
# Gemini falso
# --------------------------------------------------------------------------

class RespostaFalsa:
    def __init__(self, texto):
        self.text = texto
        self.candidates = []


class ModelsFalso:
    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def generate_content(self, model, contents, config):
        prompt = next(parte for parte in reversed(contents) if isinstance(parte, str))
        imagens = sum(1 for parte in contents if not isinstance(parte, str))
        if "Esta etapa NÃO escreve laudo" in prompt:
            etapa = "escopo"
        elif "Abaixo estão as EVIDÊNCIAS já validadas" in prompt:
            etapa = "consolidacao"
        elif "itens repetidos" in prompt or "linhas" in prompt.lower()[-200:]:
            etapa = "repetidos"
        else:
            etapa = "outra"
        self.chamadas.append({"etapa": etapa, "imagens": imagens, "prompt": prompt})
        resposta = self.respostas[etapa]
        if callable(resposta):
            resposta = resposta(prompt)
        return RespostaFalsa(json.dumps(resposta, ensure_ascii=False))


class ClienteFalso:
    def __init__(self, respostas):
        self.models = ModelsFalso(respostas)


def laudo_vazio():
    """Resposta de consolidação: só o que o teste preencher aparece."""
    from core.config import CATEGORIAS
    return {categoria: [{"texto": "Não se aplica.", "motivo": "", "certeza": 95}]
            for categoria in CATEGORIAS}


@pytest.fixture
def pasta_com_fotos(tmp_path):
    """Três JPEGs de verdade — codificar_imagem abre os arquivos."""
    pasta = tmp_path / "Cozinha"
    pasta.mkdir()
    for nome in ("foto1.jpg", "foto2.jpg", "foto3.jpg"):
        Image.new("RGB", (64, 48), "white").save(pasta / nome, "JPEG")
    return str(pasta)


# ==========================================================================
# O critério de aceitação principal (regra 47)
# ==========================================================================

def test_parede_do_corredor_nao_entra_no_laudo_da_cozinha(pasta_com_fotos):
    """A foto 2 da cozinha enquadra, pela porta, uma parede cinza do corredor.
    O modelo VÊ a parede com nitidez (percepção 98) e diz que ela é do
    ambiente vizinho. Ela não pode virar parede da cozinha."""
    laudo = laudo_vazio()
    laudo["paredes"] = [{
        "texto": "*Paredes em revestimento cerâmico na cor branca, em bom estado.",
        "motivo": "", "certeza": 95,
    }]

    cliente = ClienteFalso({
        "escopo": {
            "fotos": [
                {"indice": 1, "escopo": "valid", "relevancia": 95,
                 "ambiente_adjacente": False, "reflexo": False, "motivo": "cozinha inteira"},
                {"indice": 2, "escopo": "partial", "relevancia": 70,
                 "ambiente_adjacente": True, "reflexo": False,
                 "motivo": "pela porta aberta aparece o corredor"},
                {"indice": 3, "escopo": "valid", "relevancia": 90,
                 "ambiente_adjacente": False, "reflexo": False, "motivo": "bancada"},
            ],
            "evidencias": [
                {"foto_indice": 1, "categoria": "paredes",
                 "observacao": "paredes em revestimento cerâmico branco",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 96, "confianca_escopo": 96},
                {"foto_indice": 2, "categoria": "paredes",
                 "observacao": "parede em pintura cinza",
                 "ambiente_adjacente": True, "reflexo": False,
                 "confianca_percepcao": 98, "confianca_escopo": 20},
                {"foto_indice": 3, "categoria": "mobilia",
                 "observacao": "bancada em granito preto com cuba de inox",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 94, "confianca_escopo": 94},
            ],
        },
        "consolidacao": laudo,
    })

    resultado = pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")

    # 1. A evidência do corredor foi descartada, com o motivo registrado.
    descartadas = [e for e in resultado.evidencias if not e.aceita]
    assert len(descartadas) == 1
    assert descartadas[0].observacao == "parede em pintura cinza"
    assert descartadas[0].motivo_descarte is MotivoDescarte.AMBIENTE_ADJACENTE

    # 2. Ela NÃO foi oferecida a quem escreve o laudo.
    prompt_redacao = next(c["prompt"] for c in cliente.models.chamadas
                          if c["etapa"] == "consolidacao")
    assert "revestimento cerâmico branco" in prompt_redacao
    assert "pintura cinza" not in prompt_redacao

    # 3. O laudo saiu sem ela.
    assert "cinza" not in resultado.dados["paredes"]

    # 4. E o vistoriador foi avisado — não foi um descarte silencioso.
    assert len(resultado.conflitos) == 1
    pendencias = pipeline.conflitos_para_pendencias("Cozinha", resultado.conflitos)
    assert pendencias[0]["tipo"] == "scope_conflict"


def test_a_foto_do_corredor_continua_registrada(pasta_com_fotos):
    """Regra 7: a foto não é apagada. O sistema sabe qual foto era, por que
    foi rebaixada, e mantém isso disponível para auditoria."""
    cliente = ClienteFalso({
        "escopo": {
            "fotos": [
                {"indice": 1, "escopo": "valid", "relevancia": 95,
                 "ambiente_adjacente": False, "reflexo": False, "motivo": "ok"},
                {"indice": 2, "escopo": "out_of_scope", "relevancia": 5,
                 "ambiente_adjacente": True, "reflexo": False,
                 "motivo": "esta foto é do corredor, não da cozinha"},
                {"indice": 3, "escopo": "valid", "relevancia": 95,
                 "ambiente_adjacente": False, "reflexo": False, "motivo": "ok"},
            ],
            "evidencias": [
                {"foto_indice": 1, "categoria": "piso", "observacao": "piso em porcelanato bege",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 95, "confianca_escopo": 95},
                {"foto_indice": 2, "categoria": "piso", "observacao": "piso em cerâmica cinza",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 99, "confianca_escopo": 99},
            ],
        },
        "consolidacao": laudo_vazio(),
    })

    resultado = pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")

    assert resultado.fotos_totais == 3
    assert resultado.fotos_utilizaveis == 2
    analise = resultado.analises["foto2.jpg"]
    assert analise.escopo is EscopoFoto.FORA_DE_ESCOPO
    assert "corredor" in analise.motivo
    # a evidência dela existe, com o motivo do descarte
    fora = [e for e in resultado.evidencias if e.foto_id == "foto2.jpg"]
    assert fora and fora[0].motivo_descarte is MotivoDescarte.FOTO_FORA_DE_ESCOPO


def test_reflexo_no_espelho_nao_vira_movel_do_comodo(pasta_com_fotos):
    cliente = ClienteFalso({
        "escopo": {
            "fotos": [{"indice": i, "escopo": "valid", "relevancia": 90,
                       "ambiente_adjacente": False, "reflexo": i == 1,
                       "motivo": "espelho" if i == 1 else "ok"} for i in (1, 2, 3)],
            "evidencias": [
                {"foto_indice": 1, "categoria": "mobilia", "observacao": "um espelho na parede",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 97, "confianca_escopo": 97},
                {"foto_indice": 1, "categoria": "mobilia",
                 "observacao": "um guarda-roupa em madeira",
                 "ambiente_adjacente": False, "reflexo": True,
                 "confianca_percepcao": 92, "confianca_escopo": 92},
            ],
        },
        "consolidacao": laudo_vazio(),
    })

    resultado = pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")
    prompt = next(c["prompt"] for c in cliente.models.chamadas if c["etapa"] == "consolidacao")
    assert "espelho" in prompt
    assert "guarda-roupa" not in prompt


# ==========================================================================
# Custo: as fotos são enviadas uma vez só
# ==========================================================================

def test_cada_foto_e_enviada_uma_vez_na_analise_de_escopo(pasta_com_fotos):
    cliente = ClienteFalso({
        "escopo": {
            "fotos": [{"indice": i, "escopo": "valid", "relevancia": 90,
                       "ambiente_adjacente": False, "reflexo": False, "motivo": ""}
                      for i in (1, 2, 3)],
            "evidencias": [
                {"foto_indice": 1, "categoria": "paredes", "observacao": "parede branca",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 95, "confianca_escopo": 95},
            ],
        },
        "consolidacao": laudo_vazio(),
    })
    pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")

    escopo = [c for c in cliente.models.chamadas if c["etapa"] == "escopo"]
    assert sum(c["imagens"] for c in escopo) == 3, "cada foto, exatamente uma vez"


def test_a_redacao_nao_recebe_fotos(pasta_com_fotos):
    """Regra 15: quem escreve o laudo não vê as imagens — só as evidências
    aprovadas. É o que impede o filtro de ser contornado."""
    cliente = ClienteFalso({
        "escopo": {
            "fotos": [{"indice": i, "escopo": "valid", "relevancia": 90,
                       "ambiente_adjacente": False, "reflexo": False, "motivo": ""}
                      for i in (1, 2, 3)],
            "evidencias": [
                {"foto_indice": 1, "categoria": "paredes", "observacao": "parede branca",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 95, "confianca_escopo": 95},
            ],
        },
        "consolidacao": laudo_vazio(),
    })
    pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")

    redacao = next(c for c in cliente.models.chamadas if c["etapa"] == "consolidacao")
    assert redacao["imagens"] == 0


def test_fotos_vao_em_lotes(pasta_com_fotos, monkeypatch):
    monkeypatch.setattr(pipeline, "FOTOS_POR_LOTE_ESCOPO", 2)
    cliente = ClienteFalso({
        "escopo": lambda prompt: {
            "fotos": [{"indice": i, "escopo": "valid", "relevancia": 90,
                       "ambiente_adjacente": False, "reflexo": False, "motivo": ""}
                      for i in (1, 2)],
            "evidencias": [],
        },
        "consolidacao": laudo_vazio(),
    })
    pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")
    escopo = [c for c in cliente.models.chamadas if c["etapa"] == "escopo"]
    assert len(escopo) == 2          # 3 fotos, lotes de 2
    assert sum(c["imagens"] for c in escopo) == 3


# ==========================================================================
# Falso positivo é pior que falso negativo (regra 16)
# ==========================================================================

def test_sem_evidencia_aprovada_o_laudo_nao_e_escrito(pasta_com_fotos):
    """Nenhuma foto do cômodo serviu. O sistema não deduz um laudo: ele
    devolve o cômodo vazio e uma pendência dizendo o que houve."""
    cliente = ClienteFalso({
        "escopo": {
            "fotos": [{"indice": i, "escopo": "out_of_scope", "relevancia": 0,
                       "ambiente_adjacente": True, "reflexo": False,
                       "motivo": "não é este cômodo"} for i in (1, 2, 3)],
            "evidencias": [
                {"foto_indice": 1, "categoria": "paredes", "observacao": "parede branca",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 99, "confianca_escopo": 99},
            ],
        },
        "consolidacao": laudo_vazio(),
    })

    resultado = pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")

    assert not any(c["etapa"] == "consolidacao" for c in cliente.models.chamadas)
    assert all(not texto for texto in resultado.dados.values())
    assert len(resultado.incertos) == 1
    assert "nenhuma evidência" in resultado.incertos[0]["motivo"]


def test_cobertura_incompleta_chega_ao_prompt_da_redacao(pasta_com_fotos):
    """CASO 3: com foto parcial, quem escreve é avisado de que não pode
    concluir ausência."""
    cliente = ClienteFalso({
        "escopo": {
            "fotos": [{"indice": i, "escopo": "partial", "relevancia": 60,
                       "ambiente_adjacente": False, "reflexo": False,
                       "motivo": "só metade do cômodo"} for i in (1, 2, 3)],
            "evidencias": [
                {"foto_indice": 1, "categoria": "paredes", "observacao": "parede branca",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 95, "confianca_escopo": 95},
            ],
        },
        "consolidacao": laudo_vazio(),
    })
    resultado = pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")

    assert resultado.cobertura_incompleta is True
    prompt = next(c["prompt"] for c in cliente.models.chamadas if c["etapa"] == "consolidacao")
    assert "COBERTURA INCOMPLETA" in prompt


# ==========================================================================
# As travas do motor antigo continuam valendo no caminho novo
# ==========================================================================

def test_testes_indevidos_sao_limpos_tambem_no_motor_novo(pasta_com_fotos):
    laudo = laudo_vazio()
    laudo["paredes"] = [{
        "texto": "*Paredes em pintura branca, testadas e em funcionamento, em bom estado.",
        "motivo": "", "certeza": 95,
    }]
    cliente = ClienteFalso({
        "escopo": {
            "fotos": [{"indice": i, "escopo": "valid", "relevancia": 90,
                       "ambiente_adjacente": False, "reflexo": False, "motivo": ""}
                      for i in (1, 2, 3)],
            "evidencias": [
                {"foto_indice": 1, "categoria": "paredes", "observacao": "parede branca",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 95, "confianca_escopo": 95},
            ],
        },
        "consolidacao": laudo,
    })
    resultado = pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")
    assert "testadas e em funcionamento" not in resultado.dados["paredes"]


def test_item_de_certeza_baixa_continua_virando_pendencia(pasta_com_fotos):
    laudo = laudo_vazio()
    laudo["porta"] = [{
        "texto": "*Uma porta em madeira na cor branca.",
        "motivo": "a roseta mal aparece", "certeza": 60,
    }]
    cliente = ClienteFalso({
        "escopo": {
            "fotos": [{"indice": i, "escopo": "valid", "relevancia": 90,
                       "ambiente_adjacente": False, "reflexo": False, "motivo": ""}
                      for i in (1, 2, 3)],
            "evidencias": [
                {"foto_indice": 1, "categoria": "porta", "observacao": "porta branca",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 95, "confianca_escopo": 95},
            ],
        },
        "consolidacao": laudo,
    })
    resultado = pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")

    assert resultado.dados["porta"] == "*Uma porta em madeira na cor branca."
    pendencias = [p for p in resultado.incertos if p["categoria"] == "porta"]
    assert pendencias and pendencias[0]["certeza"] == 60


# ==========================================================================
# Contrato e rastreabilidade
# ==========================================================================

def test_pasta_sem_foto_devolve_comodo_vazio(tmp_path):
    vazia = tmp_path / "Vazio"
    vazia.mkdir()
    resultado = pipeline.processar_comodo_evidencias(None, str(vazia), "Vazio")
    assert resultado.dados == {} and resultado.incertos == []


def test_ids_de_foto_da_web_sao_respeitados(pasta_com_fotos):
    """A camada web passa os ids do banco: Evidence.foto_id aponta para
    Photo.id, não para o nome do arquivo."""
    cliente = ClienteFalso({
        "escopo": {
            "fotos": [{"indice": i, "escopo": "valid", "relevancia": 90,
                       "ambiente_adjacente": False, "reflexo": False, "motivo": ""}
                      for i in (1, 2, 3)],
            "evidencias": [
                {"foto_indice": 2, "categoria": "paredes", "observacao": "parede branca",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 95, "confianca_escopo": 95},
            ],
        },
        "consolidacao": laudo_vazio(),
    })
    resultado = pipeline.processar_comodo_evidencias(
        cliente, pasta_com_fotos, "Cozinha", ids_fotos=["p-100", "p-200", "p-300"]
    )
    assert resultado.evidencias[0].foto_id == "p-200"
    assert set(resultado.analises) == {"p-100", "p-200", "p-300"}


def test_quantidade_de_ids_diferente_da_de_fotos_e_erro(pasta_com_fotos):
    with pytest.raises(ValueError, match="paralelos"):
        pipeline.processar_comodo_evidencias(
            None, pasta_com_fotos, "Cozinha", ids_fotos=["so-um"]
        )


def test_resultado_serializa_o_grafo_inteiro(pasta_com_fotos):
    cliente = ClienteFalso({
        "escopo": {
            "fotos": [{"indice": i, "escopo": "valid", "relevancia": 90,
                       "ambiente_adjacente": False, "reflexo": False, "motivo": ""}
                      for i in (1, 2, 3)],
            "evidencias": [
                {"foto_indice": 1, "categoria": "paredes", "observacao": "parede branca",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 95, "confianca_escopo": 95,
                 "regiao": {"x": 0.1, "y": 0.1, "largura": 0.5, "altura": 0.5}},
            ],
        },
        "consolidacao": laudo_vazio(),
    })
    resultado = pipeline.processar_comodo_evidencias(cliente, pasta_com_fotos, "Cozinha")
    como_dict = resultado.para_dict()

    assert json.dumps(como_dict, ensure_ascii=False)     # serializável
    assert como_dict["fotos_totais"] == 3
    assert como_dict["evidencias"][0]["regiao"] == {
        "x": 0.1, "y": 0.1, "largura": 0.5, "altura": 0.5
    }
    assert como_dict["evidencias"][0]["foto_id"] == "foto1.jpg"


def test_motor_classico_continua_disponivel(pasta_com_fotos, monkeypatch):
    """Regra 3/31: o caminho antigo não foi removido."""
    chamado = {}

    def falso_analisar(cliente, blocos, nome, notas=""):
        chamado["blocos"] = len(blocos)
        return {"paredes": "*Paredes brancas."}, []

    monkeypatch.setattr(pipeline, "analisar_comodo", falso_analisar)
    resultado = pipeline.processar_comodo_classico(None, pasta_com_fotos, "Cozinha")

    assert chamado["blocos"] == 3
    assert resultado.dados["paredes"] == "*Paredes brancas."
    assert resultado.evidencias == []


def test_processar_comodo_escolhe_o_motor(pasta_com_fotos, monkeypatch):
    chamados = []
    monkeypatch.setattr(pipeline, "processar_comodo_classico",
                        lambda *a, **k: chamados.append("classico"))
    monkeypatch.setattr(pipeline, "processar_comodo_evidencias",
                        lambda *a, **k: chamados.append("evidencias"))

    pipeline.processar_comodo(None, pasta_com_fotos, "Cozinha", usar_evidencias=False)
    pipeline.processar_comodo(None, pasta_com_fotos, "Cozinha", usar_evidencias=True)
    assert chamados == ["classico", "evidencias"]
