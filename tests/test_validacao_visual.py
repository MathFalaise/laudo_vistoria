"""
VALIDAÇÃO VISUAL SELETIVA na V2 (core/validacao_visual.py), de ponta a
ponta, com analista e validador FALSOS — nenhuma API é chamada.

O que está sob teste é a autoridade de cada um: o analista propõe, o
validador confirma/contesta OLHANDO A FOTO, e o código decide (o veto só vale
depois de validar_escopo, e nada que o código descartou volta).
"""

import json

import pytest
from PIL import Image

import core.pipeline as pipeline
from core.config import CATEGORIAS
from core.evidencias import MotivoDescarte, StatusEvidencia, TipoConflito
from core.providers import FalhaDoProvedor, Imagem, Provedor
from core.validacao_visual import (PoliticaValidacao, interpretar_decisoes, selecionar,
                                   validar_evidencias)


# --------------------------------------------------------------------------
# Provedores falsos
# --------------------------------------------------------------------------

def _etapa(prompt: str) -> str:
    if "AUDITOR VISUAL" in prompt:
        return "validacao"
    if "Segunda olhada DIRIGIDA na MESMA foto" in prompt:
        return "reanalise"
    if "Esta etapa NÃO escreve laudo" in prompt:
        return "evidencias"
    if "Segunda passagem nas MESMAS fotos" in prompt:
        return "dirigida"
    if "Abaixo estão os OBJETOS identificados" in prompt:
        return "consolidacao"
    return "outra"


class Falso(Provedor):
    """Responde por etapa. Cada resposta pode ser dict, função(prompt) ou
    exceção; uma LISTA é consumida uma por chamada."""

    def __init__(self, nome, roteiro, modelo="falso-1"):
        self.nome, self.modelo, self.roteiro, self.chamadas = nome, modelo, roteiro, []

    def gerar_json(self, partes, esquema, max_tokens, descricao, tipo=""):
        prompt = next(p for p in reversed(partes) if isinstance(p, str))
        etapa = _etapa(prompt)
        self.chamadas.append({"etapa": etapa, "tipo": tipo, "prompt": prompt,
                              "imagens": sum(isinstance(p, Imagem) for p in partes)})
        # como os provedores reais: uma linha de telemetria por chamada
        from core import telemetria
        telemetria.registrar(telemetria.RegistroChamada(
            provedor=self.nome, modelo=self.modelo, tipo=tipo, sucesso=True, duracao_s=0.0))
        resposta = self.roteiro.get(etapa, {"evidencias": []})
        if isinstance(resposta, list):
            resposta = resposta.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        if callable(resposta):
            resposta = resposta(prompt)
        return resposta if isinstance(resposta, str) else json.dumps(resposta, ensure_ascii=False)

    def etapas(self):
        return [c["etapa"] for c in self.chamadas]


def laudo_com(texto_piso="*Piso em cerâmica na cor cinza, em bom estado."):
    dados = {c: [{"texto": "Não se aplica.", "motivo": "", "certeza": 95}] for c in CATEGORIAS}
    dados["piso"] = [{"texto": texto_piso, "motivo": "", "certeza": 95}]
    return dados


def ev(foto, categoria, observacao, percepcao=95, escopo_conf=95, escopo="room_interior", **extra):
    return {"foto_indice": foto, "categoria": categoria, "observacao": observacao,
            "escopo": escopo, "confianca_percepcao": percepcao, "confianca_escopo": escopo_conf,
            **extra}


def fotos_validas(n):
    return [{"indice": i, "escopo": "valid", "relevancia": 95, "ambiente_adjacente": False,
             "reflexo": False, "motivo": "ok"} for i in range(1, n + 1)]


def decisao(evidence_id, decision, reason="olhei a foto", **extra):
    return {"decisoes": [{"evidence_id": evidence_id, "decision": decision, "reason": reason, **extra}]}


@pytest.fixture
def pasta(tmp_path):
    pasta = tmp_path / "BWC"
    pasta.mkdir()
    for nome in ("f1.jpg", "f2.jpg"):
        Image.new("RGB", (64, 48), "white").save(pasta / nome)
    return pasta


def rodar(pasta, analista, validador, **opcoes):
    return pipeline.processar_comodo(analista, str(pasta), "BWC", motor=pipeline.MOTOR_V2,
                                     validador=validador, **opcoes)


def _por_obs(resultado, trecho):
    return next(e for e in resultado.evidencias if trecho in e.observacao)


EVIDENCIAS_BASE = {
    "fotos": fotos_validas(2),
    "evidencias": [
        ev(1, "paredes", "paredes em pintura branca", atributos={"material": "pintura", "cor": "branca"}),
        ev(2, "mobilia", "bacia sanitária ZQX com caixa acoplada", percepcao=70,
           atributos={"tipo": "caixa acoplada"}),
    ],
}


def analista_padrao(**extra):
    roteiro = {"evidencias": json.loads(json.dumps(EVIDENCIAS_BASE)), "dirigida": {"evidencias": []},
               "consolidacao": laudo_com()}
    roteiro.update(extra)
    return Falso("glm", roteiro, modelo="glm-5.3-flash")


# --------------------------------------------------------------------------
# Seleção
# --------------------------------------------------------------------------

def test_evidencia_clara_nao_chama_o_validador(pasta):
    analista = analista_padrao(evidencias={"fotos": fotos_validas(2), "evidencias": [
        ev(1, "paredes", "paredes em pintura branca")]})
    validador = Falso("claude", {})
    resultado = rodar(pasta, analista, validador)
    assert validador.chamadas == []
    assert resultado.validacao["selecionadas"] == 0
    assert resultado.evidencias[0].origem == "glm:glm-5.3-flash"


def test_evidencia_duvidosa_vai_ao_validador_com_a_foto(pasta):
    validador = Falso("claude", {"validacao": decisao("f2.jpg#2", "approved")})
    resultado = rodar(pasta, analista_padrao(), validador)
    assert validador.etapas() == ["validacao"]
    chamada = validador.chamadas[0]
    # A FOTO vai junto (uma imagem) — validar só o texto seria concordar com o texto
    assert chamada["imagens"] == 1 and chamada["tipo"] == "validacao"
    assert "bacia sanitária ZQX com caixa acoplada" in chamada["prompt"]
    assert "paredes em pintura branca" not in chamada["prompt"]      # essa não precisou
    bacia = _por_obs(resultado, "bacia")
    assert bacia.validacao == "aprovada" and bacia.aceita and bacia.validacao_por == "claude:falso-1"


# --------------------------------------------------------------------------
# Decisões
# --------------------------------------------------------------------------

def test_rejeitada_sai_do_laudo_e_vira_pendencia_de_validacao(pasta):
    analista = analista_padrao()
    validador = Falso("claude", {"validacao": decisao(
        "f2.jpg#2", "rejected", "não há caixa acoplada visível; parece válvula de parede")})
    resultado = rodar(pasta, analista, validador)
    bacia = _por_obs(resultado, "bacia")
    assert bacia.status is StatusEvidencia.DESCARTADA
    assert bacia.motivo_descarte is MotivoDescarte.VALIDACAO_VISUAL
    consolidacao = next(c for c in analista.chamadas if c["etapa"] == "consolidacao")
    assert "ZQX" not in consolidacao["prompt"]
    conflito = next(c for c in resultado.conflitos if c.tipo is TipoConflito.VALIDACAO)
    assert conflito.evidencias == [bacia.id]
    pendencia = pipeline.conflitos_para_pendencias("BWC", [conflito])[0]
    assert pendencia["motivo"].startswith(pipeline.PREFIXO_VALIDACAO)
    assert "válvula de parede" in pendencia["texto"]


def test_corrigida_atualiza_a_evidencia_e_guarda_a_original(pasta):
    analista = analista_padrao()
    validador = Falso("claude", {"validacao": decisao(
        "f2.jpg#2", "corrected", "é válvula de descarga na parede",
        corrections={"observacao": "bacia sanitária com válvula de descarga de parede",
                     "atributos": {"tipo": "válvula de parede"}})})
    resultado = rodar(pasta, analista, validador)
    bacia = _por_obs(resultado, "bacia")
    assert bacia.observacao == "bacia sanitária com válvula de descarga de parede"
    assert bacia.observacao_original == "bacia sanitária ZQX com caixa acoplada"
    assert bacia.atributos["tipo"] == "válvula de parede" and bacia.aceita
    consolidacao = next(c for c in analista.chamadas if c["etapa"] == "consolidacao")
    assert "válvula de descarga de parede" in consolidacao["prompt"]
    assert "ZQX" not in consolidacao["prompt"]


def test_corrigida_com_politica_de_conflito_nao_escolhe_lado(pasta, monkeypatch):
    monkeypatch.setenv("VALIDATION_CORRECTED_POLICY", "conflito")
    validador = Falso("claude", {"validacao": decisao(
        "f2.jpg#2", "corrected", corrections={"observacao": "bacia com válvula de parede"})})
    resultado = rodar(pasta, analista_padrao(), validador)
    bacia = _por_obs(resultado, "caixa acoplada")
    assert not bacia.aceita and bacia.validacao == "conflito_validacao"
    assert "bacia com válvula de parede" in bacia.validacao_motivo


# --------------------------------------------------------------------------
# Reanálise dirigida
# --------------------------------------------------------------------------

def _reanalise(observacao, encontrado=True):
    item = {"evidence_id": "f2.jpg#2", "encontrado": encontrado}
    if encontrado:
        item["evidencia"] = {"categoria": "mobilia", "observacao": observacao,
                             "escopo": "room_interior", "confianca_percepcao": 90,
                             "confianca_escopo": 95, "atributos": {"tipo": "válvula de parede"}}
    return {"reanalises": [item]}


def test_reanalise_chama_o_analista_uma_vez_e_o_validador_de_novo(pasta):
    analista = analista_padrao(reanalise=_reanalise("bacia sanitária com válvula de descarga de parede"))
    validador = Falso("claude", {"validacao": [
        decisao("f2.jpg#2", "needs_reanalysis", focus="tipo de descarga: caixa ou válvula"),
        decisao("f2.jpg#2", "approved"),
    ]})
    resultado = rodar(pasta, analista, validador)
    reanalises = [c for c in analista.chamadas if c["etapa"] == "reanalise"]
    assert len(reanalises) == 1 and reanalises[0]["imagens"] == 1      # SÓ a foto da dúvida
    assert "tipo de descarga" in reanalises[0]["prompt"]
    assert validador.etapas() == ["validacao", "validacao"]
    bacia = _por_obs(resultado, "válvula")
    # a MESMA evidência, atualizada no lugar: mesmo id, sem duplicar
    assert bacia.id == "f2.jpg#2" and bacia.revisao == 1 and bacia.validacao == "aprovada"
    assert bacia.observacao_original == "bacia sanitária ZQX com caixa acoplada"
    assert len(resultado.evidencias) == 2
    assert resultado.validacao["reanalisadas"] == 1


def test_limite_de_reanalise_encerra_sem_afirmar(pasta):
    analista = analista_padrao(reanalise=_reanalise("bacia sanitária com descarga"))
    validador = Falso("claude", {"validacao": [
        decisao("f2.jpg#2", "needs_reanalysis", focus="tipo de descarga"),
        decisao("f2.jpg#2", "needs_reanalysis", focus="tipo de descarga"),
    ]})
    resultado = rodar(pasta, analista, validador)
    assert [c["etapa"] for c in analista.chamadas].count("reanalise") == 1
    bacia = _por_obs(resultado, "bacia")
    assert bacia.validacao == "nao_resolvida" and not bacia.aceita


def test_reanalise_que_nao_acha_o_item_nao_o_mantem(pasta):
    analista = analista_padrao(reanalise=_reanalise("", encontrado=False))
    validador = Falso("claude", {"validacao": decisao("f2.jpg#2", "needs_reanalysis", focus="existe?")})
    bacia = _por_obs(rodar(pasta, analista, validador), "bacia")
    assert bacia.validacao == "nao_resolvida" and not bacia.aceita


# --------------------------------------------------------------------------
# Falhas: nunca viram aprovação
# --------------------------------------------------------------------------

@pytest.mark.parametrize("resposta", [
    FalhaDoProvedor("fora do ar"),
    "isto não é JSON",
    {"decisoes": [{"evidence_id": "f2.jpg#2", "decision": "talvez", "reason": "?"}]},
    {"decisoes": [{"evidence_id": "f2.jpg#2", "decision": "corrected", "reason": "?"}]},
    {"decisoes": [{"evidence_id": "f2.jpg#2", "decision": "approved", "reason": "a"},
                  {"evidence_id": "f2.jpg#2", "decision": "rejected", "reason": "b"}]},
])
def test_falha_ou_resposta_invalida_fica_em_estado_seguro(pasta, resposta):
    resultado = rodar(pasta, analista_padrao(), Falso("claude", {"validacao": resposta}))
    bacia = _por_obs(resultado, "bacia")
    assert bacia.validacao == "falha" and not bacia.aceita
    assert bacia.motivo_descarte is MotivoDescarte.VALIDACAO_VISUAL
    assert _por_obs(resultado, "paredes").aceita        # o resto do cômodo segue


def test_politica_manter_segue_o_escopo_mas_nao_marca_aprovada(pasta, monkeypatch):
    monkeypatch.setenv("VALIDATION_FAILURE_POLICY", "manter")
    resultado = rodar(pasta, analista_padrao(), Falso("claude", {"validacao": FalhaDoProvedor("x")}))
    bacia = _por_obs(resultado, "bacia")
    assert bacia.validacao == "falha_mantida" and bacia.aceita


# --------------------------------------------------------------------------
# Autoridade do código
# --------------------------------------------------------------------------

def test_reflexo_nunca_vai_ao_validador_nem_volta_ao_laudo(pasta):
    analista = analista_padrao(evidencias={"fotos": fotos_validas(2), "evidencias": [
        ev(1, "mobilia", "criado-mudo refletido no espelho", escopo="reflection", percepcao=99),
        ev(2, "mobilia", "bacia sanitária com caixa acoplada", percepcao=70),
    ]})
    # um validador que aprova TUDO o que vê
    validador = Falso("claude", {"validacao": lambda prompt: {"decisoes": [
        {"evidence_id": i, "decision": "approved", "reason": "ok"}
        for i in ("f1.jpg#1", "f2.jpg#2") if f'"{i}"' in prompt]}})
    resultado = rodar(pasta, analista, validador)
    reflexo = _por_obs(resultado, "refletido")
    assert "refletido" not in validador.chamadas[0]["prompt"]
    assert reflexo.motivo_descarte is MotivoDescarte.REFLEXO and reflexo.validacao == ""


def test_conflito_entre_fotos_nao_vira_votacao(pasta):
    analista = analista_padrao(evidencias={"fotos": fotos_validas(2), "evidencias": [
        ev(1, "piso", "piso cerâmico", percepcao=80, atributos={"material": "cerâmica", "cor": "cinza"}),
        ev(2, "piso", "piso cerâmico", percepcao=80, atributos={"material": "cerâmica", "cor": "bege"}),
    ]})
    validador = Falso("claude", {})
    resultado = rodar(pasta, analista, validador)
    assert validador.chamadas == []          # os dois lados vão ao vistoriador
    assert any(c.tipo is TipoConflito.ATRIBUTO for c in resultado.conflitos)


def test_evidencia_da_busca_dirigida_sempre_e_validada(pasta):
    analista = analista_padrao(
        evidencias={"fotos": fotos_validas(2), "evidencias": [ev(1, "paredes", "paredes em pintura branca")]},
        dirigida=lambda prompt: {"evidencias": [ev(2, "mobilia", "porta-papel higiênico cromado")]}
        if "porta-papel" in prompt else {"evidencias": []},
    )
    validador = Falso("claude", {"validacao": lambda prompt: {"decisoes": [
        {"evidence_id": eid, "decision": "rejected", "reason": "não aparece"}
        for eid in [p.split('"')[1] for p in prompt.split("- id ")[1:]]]}})
    resultado = rodar(pasta, analista, validador)
    achadas = [e for e in resultado.evidencias if "porta-papel" in e.observacao]
    assert achadas and all(e.id.startswith("d") for e in achadas)
    assert all(e.validacao == "rejeitada" and not e.aceita for e in achadas)
    assert resultado.validacao["motivos_selecao"].get("busca_dirigida") == len(achadas)


def test_teto_de_validacoes_nao_vira_aprovacao():
    from core.evidencias import Evidencia

    evidencias = [Evidencia(id=f"f#{i}", foto_id="f", categoria="piso", observacao=f"piso {i}",
                            confianca_final=60 + i) for i in range(5)]
    selecionadas, excedentes, _ = selecionar(evidencias, PoliticaValidacao(max_por_comodo=3))
    assert [e.id for e in selecionadas] == ["f#0", "f#1", "f#2"]       # as de menor confiança
    relatorio = validar_evidencias(
        Falso("claude", {"validacao": lambda p: {"decisoes": [
            {"evidence_id": f"f#{i}", "decision": "approved", "reason": "ok"} for i in range(3)]}}),
        None, evidencias, {}, {"f": Imagem(b"x")}, "Cozinha", politica=PoliticaValidacao(max_por_comodo=3))
    assert relatorio.excedentes == 2
    assert {e.validacao for e in evidencias[3:]} == {"nao_validada_limite"}


def test_interpretar_decisoes_descarta_o_que_nao_esta_no_contrato():
    texto = json.dumps({"decisoes": [
        {"evidence_id": "a", "decision": "approved", "reason": "ok"},
        {"evidence_id": "intrusa", "decision": "approved", "reason": "ok"},
        {"evidence_id": "b", "decision": "needs_reanalysis", "reason": "?"},      # sem focus
    ]})
    assert set(interpretar_decisoes(texto, ["a", "b"])) == {"a"}


# --------------------------------------------------------------------------
# Telemetria e compatibilidade
# --------------------------------------------------------------------------

def test_sem_validador_o_caminho_e_o_de_antes(pasta):
    analista = analista_padrao()
    resultado = rodar(pasta, analista, None)
    assert resultado.validacao is None
    assert all(e.validacao == "" for e in resultado.evidencias)
    assert "reanalise" not in analista.etapas()


def test_para_dict_leva_validacao_e_rastreabilidade(pasta):
    validador = Falso("claude", {"validacao": decisao("f2.jpg#2", "approved")})
    dados = rodar(pasta, analista_padrao(), validador).para_dict()
    bacia = next(e for e in dados["evidencias"] if "bacia" in e["observacao"])
    assert bacia["validacao"] == "aprovada" and bacia["origem"] == "glm:glm-5.3-flash"
    assert dados["validacao"]["chamadas_validador"] == 1
    assert "custos" in dados and isinstance(dados["chamadas"], list)
