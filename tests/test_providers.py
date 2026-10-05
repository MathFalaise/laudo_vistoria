"""
Camada de PROVEDORES (core/providers) — nenhum teste chama API externa.

GLM e Claude rodam contra um transporte HTTP falso (httpx.MockTransport): o
que está sob teste é o pedido que sai (autenticação, imagem, schema, modelo)
e o tratamento do que volta (nova tentativa, recusa, JSON inválido, resposta
cortada). O Gemini roda contra o cliente falso no formato do SDK, como nas
outras suítes.
"""

import json

import httpx
import pytest
from google.genai import types

import core.gemini_client as gc
from core import telemetria
from core.config import CATEGORIAS
from core.providers import (ConfiguracaoAusente, FalhaDoProvedor, Imagem, ProvedorComReserva,
                            RespostaCortada, como_provedor, criar_provedor, provedor_de_visao,
                            provedor_validador)
from core.providers.claude import ProvedorClaude
from core.providers.esquema import esquema, para_json_schema
from core.providers.gemini import ProvedorGemini
from core.providers.glm import ProvedorGLM

ESQUEMA = esquema(type="OBJECT", properties={"ok": esquema(type="BOOLEAN")}, required=["ok"])
FOTO = Imagem(dados=b"\xff\xd8jpeg-falso", mime="image/jpeg")


# --------------------------------------------------------------------------
# Schemas: a troca de types.Schema por dicionário não mudou o pedido ao Gemini
# --------------------------------------------------------------------------

@pytest.mark.parametrize("construtor, argumentos", [
    ("_schema_categorias", (CATEGORIAS,)),
    ("_schema_item_com_certeza", ()),
    ("_schema_itens_com_certeza", (CATEGORIAS,)),
    ("_schema_inventario", ()),
    ("_schema_divergencias", ()),
    ("_schema_escopo_evidencias", (7,)),
    ("_schema_evidencia_v2", (7,)),
    ("_schema_escopo_v2", (7,)),
])
def test_schemas_neutros_sao_os_mesmos_do_gemini(monkeypatch, construtor, argumentos):
    neutro = getattr(gc, construtor)(*argumentos)
    # o mesmo construtor, com o types.Schema original no lugar de esquema()
    monkeypatch.setattr(gc, "esquema", lambda **campos: types.Schema(**campos))
    original = getattr(gc, construtor)(*argumentos)
    assert types.Schema.model_validate(neutro) == original


def test_json_schema_preserva_a_ordem_e_converte_os_campos():
    convertido = para_json_schema(gc._schema_item_com_certeza())
    assert list(convertido["properties"]) == ["texto", "motivo", "certeza"]
    assert convertido["properties"]["certeza"] == {"type": "integer", "minimum": 0, "maximum": 100}
    assert convertido["required"] == ["texto", "motivo", "certeza"]
    lista = para_json_schema(gc._schema_itens_com_certeza(["piso"]))
    assert lista["properties"]["piso"]["minItems"] == 1


def test_esquema_recusa_campo_que_nao_existe():
    with pytest.raises(ValueError):
        esquema(type="STRING", formato="x")


# --------------------------------------------------------------------------
# Gemini
# --------------------------------------------------------------------------

class _Uso:
    prompt_token_count, candidates_token_count, total_token_count = 2200, 300, 2500


class _Resposta:
    def __init__(self, texto, finish=None):
        self.text = texto
        self.usage_metadata = _Uso()
        self.candidates = [type("C", (), {"finish_reason": finish})()] if finish else []


class _Models:
    def __init__(self, respostas):
        self.respostas, self.pedidos = list(respostas), []

    def generate_content(self, model, contents, config):
        self.pedidos.append({"model": model, "contents": contents, "config": config})
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class _ClienteGemini:
    def __init__(self, *respostas):
        self.models = _Models(respostas)


def test_gemini_converte_imagem_e_schema_para_o_sdk():
    cliente = _ClienteGemini(_Resposta('{"ok": true}'))
    provedor = ProvedorGemini(cliente=cliente, modelo="gemini-teste")
    assert provedor.gerar_json([FOTO, "prompt"], ESQUEMA, 100, "teste") == '{"ok": true}'
    pedido = cliente.models.pedidos[0]
    assert pedido["model"] == "gemini-teste"
    assert isinstance(pedido["contents"][0], types.Part) and pedido["contents"][1] == "prompt"
    assert pedido["config"].response_schema == types.Schema.model_validate(ESQUEMA)
    assert pedido["config"].response_mime_type == "application/json"


def test_gemini_tenta_de_novo_em_falha_de_rede_e_registra_telemetria():
    esperas = []
    cliente = _ClienteGemini(httpx.ConnectError("caiu"), _Resposta('{"ok": true}'))
    provedor = ProvedorGemini(cliente=cliente, modelo="m", dormir=esperas.append)
    with telemetria.coletar() as chamadas:
        provedor.gerar_json(["p"], ESQUEMA, 100, "teste", tipo="escopo")
    assert esperas == [10]
    assert chamadas[0]["tentativas"] == 2 and chamadas[0]["tipo"] == "escopo"
    assert chamadas[0]["tokens_entrada"] == 2200 and chamadas[0]["tokens_saida"] == 300


def test_gemini_resposta_cortada_e_erro():
    cliente = _ClienteGemini(_Resposta('{"ok":', finish=types.FinishReason.MAX_TOKENS))
    with pytest.raises(RespostaCortada):
        ProvedorGemini(cliente=cliente, modelo="m").gerar_json(["p"], ESQUEMA, 10, "teste")


def test_cliente_no_formato_do_sdk_vira_provedor_gemini():
    assert isinstance(como_provedor(_ClienteGemini()), ProvedorGemini)
    with pytest.raises(TypeError):
        como_provedor(object())


# --------------------------------------------------------------------------
# GLM (OpenCode Zen, formato compatível com OpenAI)
# --------------------------------------------------------------------------

def _transporte(respostas, pedidos):
    fila = list(respostas)

    def tratar(pedido):
        pedidos.append(pedido)
        resposta = fila.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
    return httpx.MockTransport(tratar)


def _ok_glm(conteudo='{"ok": true}', finish="stop"):
    return httpx.Response(200, json={
        "choices": [{"message": {"content": conteudo}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 1500, "completion_tokens": 200, "total_tokens": 1700}})


def _glm(respostas, pedidos, esperas=None, **opcoes):
    return ProvedorGLM(chave="chave-secreta-glm", base_url="https://zen.teste/v1",
                       transport=_transporte(respostas, pedidos),
                       dormir=(esperas.append if esperas is not None else lambda s: None), **opcoes)


def test_glm_pedido_autenticacao_imagem_schema_e_modelo():
    pedidos = []
    provedor = _glm([_ok_glm()], pedidos, modelo="glm-teste")
    with telemetria.coletar() as chamadas:
        assert provedor.gerar_json([FOTO, "prompt"], ESQUEMA, 512, "teste", "evidencias") == '{"ok": true}'
    pedido = pedidos[0]
    assert str(pedido.url) == "https://zen.teste/v1/chat/completions"
    assert pedido.headers["authorization"] == "Bearer chave-secreta-glm"
    corpo = json.loads(pedido.content)
    assert corpo["model"] == "glm-teste" and corpo["max_tokens"] == 512
    imagem, texto = corpo["messages"][0]["content"]
    assert imagem["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert texto == {"type": "text", "text": "prompt"}
    assert corpo["response_format"]["json_schema"]["schema"] == para_json_schema(ESQUEMA)
    assert chamadas[0]["imagens"] == 1 and chamadas[0]["tokens_saida"] == 200
    # preço do glm-5.3-flash não se aplica ao "glm-teste": custo desconhecido
    assert chamadas[0]["custo_usd"] is None


def test_glm_modelo_padrao_e_custo_conhecido(monkeypatch):
    monkeypatch.delenv("GLM_MODEL", raising=False)
    pedidos = []
    with telemetria.coletar() as chamadas:
        _glm([_ok_glm()], pedidos).gerar_json(["p"], ESQUEMA, 10, "teste")
    assert json.loads(pedidos[0].content)["model"] == "glm-5.3-flash"
    assert chamadas[0]["custo_usd"] == round(1500 / 1e6 * 0.15 + 200 / 1e6 * 0.50, 6)


def test_glm_tenta_de_novo_em_503_e_respeita_retry_after_no_429():
    pedidos, esperas = [], []
    provedor = _glm([httpx.Response(503), httpx.Response(429, headers={"retry-after": "2"}),
                     _ok_glm()], pedidos, esperas)
    with telemetria.coletar() as chamadas:
        provedor.gerar_json(["p"], ESQUEMA, 10, "teste")
    assert len(pedidos) == 3 and esperas == [5, 2]
    assert chamadas[0]["tentativas"] == 3


def test_glm_timeout_esgota_as_tentativas():
    pedidos, esperas = [], []
    provedor = _glm([httpx.ReadTimeout("lento")] * 4, pedidos, esperas)
    with pytest.raises(FalhaDoProvedor, match="4 tentativas"):
        provedor.gerar_json(["p"], ESQUEMA, 10, "teste")
    assert len(pedidos) == 4


def test_glm_erro_4xx_nao_repete_e_nao_vaza_a_chave():
    pedidos = []
    provedor = _glm([httpx.Response(401, json={"error": {"type": "auth", "message": "chave inválida"}})],
                    pedidos)
    with pytest.raises(FalhaDoProvedor) as erro:
        provedor.gerar_json([FOTO, "p"], ESQUEMA, 10, "teste")
    assert len(pedidos) == 1
    assert "401" in str(erro.value) and "chave-secreta-glm" not in str(erro.value)
    assert "chave-secreta-glm" not in repr(provedor)


@pytest.mark.parametrize("resposta, erro", [
    (httpx.Response(200, text="<html>gateway</html>"), FalhaDoProvedor),
    (httpx.Response(200, json={"choices": []}), FalhaDoProvedor),
    (_ok_glm(conteudo=""), FalhaDoProvedor),
    (_ok_glm(conteudo='{"ok": tr', finish="length"), RespostaCortada),
])
def test_glm_resposta_invalida_vira_erro_controlado(resposta, erro):
    with pytest.raises(erro):
        _glm([resposta], []).gerar_json(["p"], ESQUEMA, 10, "teste")


def test_glm_formato_json_object_poe_o_schema_no_texto():
    pedidos = []
    _glm([_ok_glm()], pedidos, formato="json_object").gerar_json(["p"], ESQUEMA, 10, "teste")
    corpo = json.loads(pedidos[0].content)
    assert corpo["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in corpo["messages"][0]["content"][-1]["text"]


def test_glm_sem_chave_nao_e_criado(monkeypatch):
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    with pytest.raises(ConfiguracaoAusente):
        ProvedorGLM()


# --------------------------------------------------------------------------
# Claude (API de Mensagens da Anthropic)
# --------------------------------------------------------------------------

def _ok_claude(entrada=None, stop="tool_use"):
    return httpx.Response(200, json={
        "content": [{"type": "tool_use", "name": "responder", "input": entrada or {"ok": True}}],
        "stop_reason": stop, "usage": {"input_tokens": 1800, "output_tokens": 90}})


def _claude(respostas, pedidos, **opcoes):
    opcoes.setdefault("modelo", "claude-teste")
    return ProvedorClaude(chave="chave-secreta-claude", base_url="https://anthropic.teste",
                          transport=_transporte(respostas, pedidos), dormir=lambda s: None,
                          **opcoes)


def test_claude_pedido_imagem_ferramenta_forcada_e_modelo_configuravel():
    pedidos = []
    with telemetria.coletar() as chamadas:
        texto = _claude([_ok_claude()], pedidos).gerar_json([FOTO, "valide"], ESQUEMA, 300, "t", "validacao")
    assert json.loads(texto) == {"ok": True}
    pedido = pedidos[0]
    assert str(pedido.url) == "https://anthropic.teste/v1/messages"
    assert pedido.headers["x-api-key"] == "chave-secreta-claude"
    assert pedido.headers["anthropic-version"]
    corpo = json.loads(pedido.content)
    assert corpo["model"] == "claude-teste"
    imagem, texto_parte = corpo["messages"][0]["content"]
    assert imagem["type"] == "image" and imagem["source"]["type"] == "base64"
    assert texto_parte["text"] == "valide"
    assert corpo["tool_choice"] == {"type": "tool", "name": "responder"}
    assert corpo["tools"][0]["input_schema"] == para_json_schema(ESQUEMA)
    assert chamadas[0]["tokens_total"] == 1890 and chamadas[0]["tipo"] == "validacao"


def test_claude_sem_modelo_configurado_nao_e_criado(monkeypatch):
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    with pytest.raises(ConfiguracaoAusente, match="CLAUDE_MODEL"):
        ProvedorClaude(chave="x")


@pytest.mark.parametrize("resposta, erro", [
    (httpx.Response(200, json={"content": [{"type": "text", "text": "acho que sim"}]}), FalhaDoProvedor),
    (_ok_claude(stop="max_tokens"), RespostaCortada),
    (httpx.Response(400, json={"error": {"type": "invalid_request_error", "message": "x"}}), FalhaDoProvedor),
])
def test_claude_resposta_invalida_vira_erro_controlado(resposta, erro):
    with pytest.raises(erro):
        _claude([resposta], []).gerar_json(["p"], ESQUEMA, 10, "teste")


# --------------------------------------------------------------------------
# Escolha por ambiente, reserva e telemetria
# --------------------------------------------------------------------------

def test_padrao_continua_gemini_e_validador_desligado(monkeypatch):
    import core.config as config
    for nome in ("VISION_PROVIDER", "VISION_FALLBACK_PROVIDER", "VALIDATION_ENABLED"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setattr(config, "API_KEY", "chave-gemini-falsa")
    assert isinstance(provedor_de_visao(), ProvedorGemini)
    assert provedor_validador() is None


def test_ambiente_escolhe_glm_com_reserva_e_validador_claude(monkeypatch):
    import core.config as config
    monkeypatch.setattr(config, "API_KEY", "chave-gemini-falsa")
    monkeypatch.setenv("VISION_PROVIDER", "glm")
    monkeypatch.setenv("GLM_API_KEY", "k")
    monkeypatch.setenv("VISION_FALLBACK_PROVIDER", "gemini")
    monkeypatch.setenv("VALIDATION_ENABLED", "1")
    monkeypatch.setenv("CLAUDE_API_KEY", "k")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-qualquer")
    visao = provedor_de_visao()
    assert isinstance(visao, ProvedorComReserva) and visao.nome == "glm"
    assert isinstance(visao.reserva, ProvedorGemini)
    assert isinstance(provedor_validador(), ProvedorClaude)
    with pytest.raises(ConfiguracaoAusente):
        criar_provedor("openai")


def test_reserva_so_entra_quando_o_principal_falha():
    class Falha:
        nome, modelo = "glm", "m"

        def gerar_json(self, *a, **k):
            raise FalhaDoProvedor("fora do ar")

    class Ok:
        nome, modelo = "gemini", "g"

        def gerar_json(self, *a, **k):
            return '{"ok": true}'

    assert ProvedorComReserva(Falha(), Ok()).gerar_json(["p"], ESQUEMA, 1, "t") == '{"ok": true}'


def test_telemetria_contexto_resumo_e_nada_de_conteudo():
    with telemetria.coletar() as chamadas, telemetria.contexto(comodo="Cozinha"):
        _glm([_ok_glm()], []).gerar_json([FOTO, "prompt secreto do imóvel"], ESQUEMA, 10, "t", "escopo")
    linha = chamadas[0]
    assert linha["contexto"] == {"comodo": "Cozinha"}
    assert "prompt secreto" not in json.dumps(linha, ensure_ascii=False)
    resumo = telemetria.resumir(chamadas)
    assert resumo["glm:glm-5.3-flash"]["chamadas"] == 1
    assert resumo["glm:glm-5.3-flash"]["por_tipo"] == {"escopo": 1}


def test_preco_por_ambiente_e_custo_desconhecido_nao_vira_zero(monkeypatch):
    monkeypatch.setenv("LAUDO_PRECOS_MODELOS", '{"claude-teste": [3, 15]}')
    assert telemetria.calcular_custo("claude-teste", 1_000_000, 100_000) == 4.5
    assert telemetria.calcular_custo("modelo-sem-preco", 10, 10) is None
    resumo = telemetria.resumir([
        {"provedor": "x", "modelo": "y", "tipo": "a", "sucesso": True, "duracao_s": 1, "custo_usd": 0.1},
        {"provedor": "x", "modelo": "y", "tipo": "a", "sucesso": True, "duracao_s": 1, "custo_usd": None},
    ])
    assert resumo["x:y"]["custo_usd"] is None


def test_imagem_nao_aparece_em_repr():
    assert "jpeg-falso" not in repr(FOTO) and "bytes" in repr(FOTO)
