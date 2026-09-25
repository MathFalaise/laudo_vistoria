"""
API: fluxo completo, segurança e persistência.

Nenhum teste chama o Gemini. O processamento usa um cliente falso injetado em
`core.gemini_client.criar_cliente` — o que está sob teste é o caminho da
aplicação, não a qualidade do modelo.

Os testes marcados "critério N" são os da regra 47 do pedido.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.models import EstadoJob

EMAIL = "vistoriador@teste.local"
SENHA = "senha-de-teste-12345"


# --------------------------------------------------------------------------
# Apoio
# --------------------------------------------------------------------------

def jpeg(cor="white", tamanho=(64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(buffer, "JPEG")
    return buffer.getvalue()


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "blue").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def cliente():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def logado(cliente):
    resposta = cliente.post("/api/auth/login", json={"email": EMAIL, "senha": SENHA})
    assert resposta.status_code == 200
    return cliente


@pytest.fixture
def vistoria(logado):
    resposta = logado.post("/api/vistorias", json={
        "titulo": "R. de Teste, 100", "notas": "Paredes na cor Branco Gelo.",
    })
    assert resposta.status_code == 201
    return resposta.json()["id"]


def criar_comodo(cliente, vistoria_id, nome="Cozinha"):
    return cliente.post(f"/api/vistorias/{vistoria_id}/comodos",
                        json={"nome": nome}).json()["id"]


def enviar(cliente, comodo_id, arquivos):
    return cliente.post(
        f"/api/comodos/{comodo_id}/fotos",
        files=[("arquivos", (nome, dados, tipo)) for nome, dados, tipo in arquivos],
    )


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

    def generate_content(self, model, contents, config):
        prompt = next(p for p in reversed(contents) if isinstance(p, str))
        if "Esta etapa NÃO escreve laudo" in prompt:
            chave = "escopo"
        elif "Abaixo estão as EVIDÊNCIAS já validadas" in prompt:
            chave = "consolidacao"
        else:
            chave = "outra"
        return _Resposta(json.dumps(self.roteiro[chave], ensure_ascii=False))


class _Cliente:
    def __init__(self, roteiro):
        self.models = _Models(roteiro)


def laudo_padrao():
    from core.config import CATEGORIAS
    dados = {c: [{"texto": "Não se aplica.", "motivo": "", "certeza": 95}]
             for c in CATEGORIAS}
    dados["paredes"] = [{
        "texto": "*Paredes em pintura lisa na cor Branco Gelo, em bom estado.",
        "motivo": "", "certeza": 95,
    }]
    dados["piso"] = [{
        "texto": "*Piso em cerâmica na cor Crômio, em bom estado.",
        "motivo": "a junta não aparece bem", "certeza": 62,
    }]
    return dados


def roteiro_padrao(quantidade_fotos=2):
    return {
        "escopo": {
            "fotos": [{"indice": i, "escopo": "valid", "relevancia": 95,
                       "ambiente_adjacente": False, "reflexo": False, "motivo": "ok"}
                      for i in range(1, quantidade_fotos + 1)],
            "evidencias": [
                {"foto_indice": 1, "categoria": "paredes",
                 "observacao": "paredes em pintura branca",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 95, "confianca_escopo": 95},
                {"foto_indice": 1, "categoria": "piso",
                 "observacao": "piso em cerâmica cinza",
                 "ambiente_adjacente": False, "reflexo": False,
                 "confianca_percepcao": 70, "confianca_escopo": 90},
                # esta é de outro ambiente e não pode virar texto
                {"foto_indice": 2, "categoria": "paredes",
                 "observacao": "parede em pintura verde do corredor",
                 "ambiente_adjacente": True, "reflexo": False,
                 "confianca_percepcao": 99, "confianca_escopo": 15},
            ],
        },
        "consolidacao": laudo_padrao(),
    }


@pytest.fixture
def gemini_falso(monkeypatch):
    def aplicar(roteiro):
        import core.gemini_client as gc
        monkeypatch.setattr(gc, "criar_cliente", lambda: _Cliente(roteiro))
        return roteiro
    return aplicar


def processar(cliente, vistoria_id, **corpo):
    from app.jobs import executar_pendentes_sincronamente
    resposta = cliente.post(f"/api/vistorias/{vistoria_id}/processar", json=corpo)
    assert resposta.status_code == 202, resposta.text
    executar_pendentes_sincronamente()
    return cliente.get(f"/api/jobs/{resposta.json()['id']}").json()


# ==========================================================================
# Critérios 1-2: abrir e entrar
# ==========================================================================

def test_saude_nao_vaza_a_chave(cliente):
    dados = cliente.get("/api/saude").json()
    assert dados["ok"] is True
    assert "chave-falsa-de-teste" not in json.dumps(dados)
    assert set(dados) == {"ok", "modelo", "gemini_configurado"}


def test_login_e_logout(cliente):
    assert cliente.get("/api/vistorias").status_code == 401
    assert cliente.post("/api/auth/login",
                        json={"email": EMAIL, "senha": "errada"}).status_code == 401
    assert cliente.post("/api/auth/login",
                        json={"email": "ninguem@x.com", "senha": SENHA}).status_code == 401
    assert cliente.post("/api/auth/login",
                        json={"email": EMAIL, "senha": SENHA}).status_code == 200
    assert cliente.get("/api/vistorias").status_code == 200


def test_mensagem_de_erro_nao_diz_se_o_email_existe(cliente):
    """Mensagens diferentes entregariam quais e-mails têm conta."""
    a = cliente.post("/api/auth/login", json={"email": EMAIL, "senha": "errada"}).json()
    b = cliente.post("/api/auth/login", json={"email": "x@y.z", "senha": "errada"}).json()
    assert a["detail"] == b["detail"]


def test_logout_invalida_a_sessao_no_servidor(cliente):
    cliente.post("/api/auth/login", json={"email": EMAIL, "senha": SENHA})
    token = cliente.cookies.get("laudo_sessao")
    cliente.post("/api/auth/logout")
    assert cliente.get("/api/vistorias", cookies={"laudo_sessao": token}).status_code == 401


def test_cookie_de_sessao_e_httponly(cliente):
    resposta = cliente.post("/api/auth/login", json={"email": EMAIL, "senha": SENHA})
    cabecalho = resposta.headers.get("set-cookie", "").lower()
    assert "httponly" in cabecalho
    assert "samesite=lax" in cabecalho


@pytest.mark.parametrize("metodo,rota", [
    ("get", "/api/vistorias"), ("post", "/api/vistorias"),
    ("get", "/api/regras"), ("get", "/api/jobs/qualquer"),
    ("get", "/api/vistorias/x/pendencias"), ("get", "/api/vistorias/x/laudo"),
    ("get", "/api/vistorias/x/exportar/laudo.txt"),
    ("get", "/api/fotos/x/miniatura"), ("get", "/api/comodos/x/evidencias"),
])
def test_todas_as_rotas_de_dados_exigem_sessao(cliente, metodo, rota):
    assert getattr(cliente, metodo)(rota).status_code == 401


def test_senha_nao_e_guardada_em_texto():
    from sqlalchemy import select
    from app.db import SessaoBanco
    from app.models import Usuario
    with SessaoBanco() as sessao:
        usuario = sessao.scalar(select(Usuario).where(Usuario.email == EMAIL))
        assert usuario is not None
        assert SENHA not in usuario.senha_hash
        assert usuario.senha_hash.startswith("scrypt$")


# ==========================================================================
# Critérios 3-5: vistoria, cômodos, fotos
# ==========================================================================

def test_criar_vistoria_e_comodo(logado):
    vistoria_id = logado.post("/api/vistorias", json={"titulo": "Casa 1"}).json()["id"]
    assert logado.post(f"/api/vistorias/{vistoria_id}/comodos",
                       json={"nome": "Sala"}).status_code == 201
    detalhe = logado.get(f"/api/vistorias/{vistoria_id}").json()
    assert [c["nome"] for c in detalhe["lista_comodos"]] == ["Sala"]


def test_comodo_repetido_nao_duplica(logado, vistoria):
    primeiro = criar_comodo(logado, vistoria, "Sala")
    segundo = criar_comodo(logado, vistoria, "Sala")
    assert primeiro == segundo


def test_upload_de_varias_fotos(logado, vistoria):
    comodo = criar_comodo(logado, vistoria)
    resposta = enviar(logado, comodo, [
        ("a.jpg", jpeg(), "image/jpeg"),
        ("b.png", png(), "image/png"),
    ])
    assert resposta.status_code == 201
    assert len(resposta.json()["aceitas"]) == 2
    assert resposta.json()["recusadas"] == []


def test_arquivo_que_nao_e_imagem_e_recusado_pelo_conteudo(logado, vistoria):
    """Regra 28: extensão não é prova. O nome diz .jpg, o conteúdo não é."""
    comodo = criar_comodo(logado, vistoria)
    resposta = enviar(logado, comodo, [("virus.jpg", b"MZ\x90\x00isto e um exe", "image/jpeg")])
    assert resposta.status_code == 201
    assert resposta.json()["aceitas"] == []
    assert "não é uma imagem" in resposta.json()["recusadas"][0]["motivo"]


def test_um_arquivo_ruim_nao_derruba_os_bons(logado, vistoria):
    comodo = criar_comodo(logado, vistoria)
    resposta = enviar(logado, comodo, [
        ("boa.jpg", jpeg(), "image/jpeg"),
        ("ruim.jpg", b"nada", "image/jpeg"),
    ]).json()
    assert len(resposta["aceitas"]) == 1 and len(resposta["recusadas"]) == 1


def test_foto_grande_demais_e_recusada(logado, vistoria, monkeypatch):
    import app.storage as storage
    monkeypatch.setattr(storage, "TAMANHO_MAX_FOTO", 1000)
    comodo = criar_comodo(logado, vistoria)
    resposta = enviar(logado, comodo, [("grande.jpg", jpeg(tamanho=(800, 800)), "image/jpeg")])
    assert "maior que o limite" in resposta.json()["recusadas"][0]["motivo"]


def test_heic_e_aceito_de_verdade(logado, vistoria):
    """Regra 28: suporte real a HEIC, não só a extensão na lista."""
    from app.storage import HEIC_DISPONIVEL
    if not HEIC_DISPONIVEL:
        pytest.skip("pillow-heif não instalado neste ambiente")

    import pillow_heif
    imagem = Image.new("RGB", (64, 64), "red")
    heif = pillow_heif.from_pillow(imagem)
    buffer = io.BytesIO()
    heif.save(buffer, format="HEIF")

    comodo = criar_comodo(logado, vistoria)
    resposta = enviar(logado, comodo, [("iphone.HEIC", buffer.getvalue(), "image/heic")])
    assert resposta.status_code == 201, resposta.text
    aceitas = resposta.json()["aceitas"]
    assert len(aceitas) == 1
    # Foi convertida para JPEG, porque o navegador não exibe HEIC.
    assert aceitas[0]["mime"] == "image/jpeg"
    # E a miniatura abre.
    assert logado.get(f"/api/fotos/{aceitas[0]['id']}/miniatura").status_code == 200


def test_miniatura_e_arquivo_original(logado, vistoria):
    comodo = criar_comodo(logado, vistoria)
    foto = enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg")]).json()["aceitas"][0]
    mini = logado.get(f"/api/fotos/{foto['id']}/miniatura")
    assert mini.status_code == 200 and mini.headers["content-type"] == "image/jpeg"
    assert logado.get(f"/api/fotos/{foto['id']}/arquivo").status_code == 200


def test_remover_foto(logado, vistoria):
    comodo = criar_comodo(logado, vistoria)
    foto = enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg")]).json()["aceitas"][0]
    assert logado.delete(f"/api/fotos/{foto['id']}").status_code == 200
    assert logado.get(f"/api/comodos/{comodo}/fotos").json() == []


# --- ZIP -------------------------------------------------------------------

def zip_de(entradas: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for nome, dados in entradas.items():
            zf.writestr(nome, dados)
    return buffer.getvalue()


def test_zip_preserva_os_comodos(logado, vistoria):
    dados = zip_de({
        "Cozinha/1.jpg": jpeg(), "Cozinha/2.jpg": jpeg(),
        "Sala/1.jpg": jpeg(),
    })
    resposta = logado.post(f"/api/vistorias/{vistoria}/zip",
                           files={"arquivo": ("v.zip", dados, "application/zip")})
    assert resposta.status_code == 201
    assert {c["comodo"]: c["fotos"] for c in resposta.json()["comodos"]} == {
        "Cozinha": 2, "Sala": 1
    }


def test_zip_slip_e_bloqueado(logado, vistoria):
    """Entrada "../../etc/passwd" é recusada — o formato ZIP permite, e
    extrair sem checar é a falha clássica."""
    dados = zip_de({"../../fora.jpg": jpeg(), "Cozinha/boa.jpg": jpeg()})
    resposta = logado.post(f"/api/vistorias/{vistoria}/zip",
                           files={"arquivo": ("v.zip", dados, "application/zip")})
    assert resposta.status_code == 201
    comodos = {c["comodo"] for c in resposta.json()["comodos"]}
    assert comodos == {"Cozinha"}


def test_zip_com_caminho_absoluto_e_ignorado():
    from app.storage import ler_zip_de_vistoria
    dados = zip_de({"/etc/senha.jpg": jpeg(), "Sala/ok.jpg": jpeg()})
    assert set(ler_zip_de_vistoria(dados)) == {"Sala"}


def test_zip_com_muitos_arquivos_e_recusado(monkeypatch):
    import app.storage as storage
    from app.storage import ArquivoRejeitado, ler_zip_de_vistoria
    monkeypatch.setattr(storage, "MAX_ARQUIVOS_ZIP", 2)
    dados = zip_de({f"Sala/{i}.jpg": jpeg() for i in range(5)})
    with pytest.raises(ArquivoRejeitado, match="limite"):
        ler_zip_de_vistoria(dados)


def test_zip_sem_imagem_da_mensagem_util(logado, vistoria):
    dados = zip_de({"leiame.txt": b"nada aqui"})
    resposta = logado.post(f"/api/vistorias/{vistoria}/zip",
                           files={"arquivo": ("v.zip", dados, "application/zip")})
    assert resposta.status_code == 400
    assert "uma pasta por cômodo" in resposta.json()["detail"]


def test_path_traversal_no_caminho_do_banco():
    """Última linha de defesa: mesmo um caminho malicioso já gravado no banco
    não é servido."""
    from app.storage import ArquivoRejeitado, caminho_absoluto
    for caminho in ("../../../etc/passwd", "..\\..\\windows\\system32\\config\\sam"):
        with pytest.raises(ArquivoRejeitado):
            caminho_absoluto(caminho)


# ==========================================================================
# Critérios 6-9: processar, progresso, laudo, evidências
# ==========================================================================

def test_processar_cria_job_e_conclui(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])

    job = processar(logado, vistoria)
    assert job["estado"] == EstadoJob.CONCLUIDO
    assert job["concluidos"] == 1


def test_processar_sem_foto_recusa(logado, vistoria):
    criar_comodo(logado, vistoria)
    resposta = logado.post(f"/api/vistorias/{vistoria}/processar", json={})
    assert resposta.status_code == 400
    assert "Nenhum cômodo com fotos" in resposta.json()["detail"]


def test_laudo_sai_no_formato_de_sempre(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    laudo = logado.get(f"/api/vistorias/{vistoria}/laudo").json()
    texto = laudo["texto"]
    assert texto.startswith("COZINHA")
    assert "Paredes:" in texto
    assert "*Paredes em pintura lisa na cor Branco Gelo, em bom estado." in texto
    # Sem linha em branco entre itens, e sem Markdown.
    assert "\n\n*" not in texto
    assert "#" not in texto and "**" not in texto


def test_criterio_principal_parede_de_outro_comodo_nao_entra(logado, vistoria, gemini_falso):
    """O critério que fecha a regra 47: a evidência marcada como de ambiente
    adjacente não vira texto, mas continua visível para auditoria."""
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    texto = logado.get(f"/api/vistorias/{vistoria}/laudo").json()["texto"]
    assert "verde" not in texto

    evidencias = logado.get(f"/api/comodos/{comodo}/evidencias").json()
    descartada = [e for e in evidencias if "verde" in e["observacao"]]
    assert len(descartada) == 1
    assert descartada[0]["status"] == "descartada"
    assert descartada[0]["motivo_descarte"] == "ambiente_adjacente"
    assert descartada[0]["confianca_percepcao"] == 99   # o modelo VIU bem
    assert descartada[0]["confianca_escopo"] == 15      # e não era daqui


def test_evidencias_descartadas_continuam_listadas(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)
    evidencias = logado.get(f"/api/comodos/{comodo}/evidencias").json()
    assert len(evidencias) == 3
    assert {e["status"] for e in evidencias} == {"aceita", "descartada"}


def test_item_do_laudo_aponta_para_as_evidencias(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    laudo = logado.get(f"/api/vistorias/{vistoria}/laudo").json()
    paredes = next(c for c in laudo["comodos"][0]["categorias"] if c["categoria"] == "paredes")
    assert paredes["itens"][0]["evidencias"], "o item tem que apontar para a evidência"


def test_reprocessar_e_opcional(logado, vistoria, gemini_falso):
    """Regra 26: não repetir processamento já terminado sem necessidade."""
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    assert logado.post(f"/api/vistorias/{vistoria}/processar", json={}).status_code == 400
    resposta = logado.post(f"/api/vistorias/{vistoria}/processar",
                           json={"reprocessar_concluidos": True})
    assert resposta.status_code == 202


def test_foto_nova_marca_o_comodo_como_pendente(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)
    enviar(logado, comodo, [("c.jpg", jpeg(), "image/jpeg")])
    detalhe = logado.get(f"/api/vistorias/{vistoria}").json()
    assert detalhe["lista_comodos"][0]["estado"] == "pendente"


# ==========================================================================
# Critérios 10-11: pendência e correção
# ==========================================================================

def test_pendencia_de_certeza_baixa_aparece(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    pendencias = logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
    piso = [p for p in pendencias if p["categoria"] == "piso"]
    assert piso and piso[0]["certeza"] == 62
    assert "junta" in piso[0]["motivo"]


def test_conflito_de_escopo_vira_pendencia_com_a_foto(logado, vistoria, gemini_falso):
    """Regras 19 e 20: a tela precisa mostrar a foto envolvida."""
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    pendencias = logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
    conflitos = [p for p in pendencias if p["tipo"] == "scope_conflict"]
    assert conflitos, "o descarte não pode ser silencioso"
    assert conflitos[0]["fotos"], "a pendência tem que apontar para a foto"
    assert conflitos[0]["evidencias"][0]["observacao"].startswith("parede em pintura verde")
    # e vem primeiro na lista
    assert pendencias[0]["tipo"] == "scope_conflict"


def test_decisao_corrigir_muda_o_laudo(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    pendencia = next(p for p in logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
                     if p["categoria"] == "piso")
    resposta = logado.post(f"/api/pendencias/{pendencia['id']}/decisao", json={
        "decisao": "CORRIGIR",
        "correcao": "*Piso em porcelanato na cor Crômio, em bom estado.",
    })
    assert resposta.status_code == 200
    texto = logado.get(f"/api/vistorias/{vistoria}/laudo").json()["texto"]
    assert "porcelanato" in texto
    assert "*Piso em cerâmica na cor Crômio" not in texto


def test_decisao_remover_tira_do_laudo(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    pendencia = next(p for p in logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
                     if p["categoria"] == "piso")
    logado.post(f"/api/pendencias/{pendencia['id']}/decisao", json={"decisao": "REMOVER"})
    assert "Piso em cerâmica" not in logado.get(f"/api/vistorias/{vistoria}/laudo").json()["texto"]


def test_conflito_com_corrigir_acrescenta_ao_laudo(logado, vistoria, gemini_falso):
    """O vistoriador olhou a foto e decidiu que a parede é, sim, do cômodo."""
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    conflito = next(p for p in logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
                    if p["tipo"] == "scope_conflict")
    resposta = logado.post(f"/api/pendencias/{conflito['id']}/decisao", json={
        "decisao": "CORRIGIR",
        "correcao": "*Uma parede em pintura lisa na cor verde, em bom estado.",
        "tipo_correcao": "AMBIENTE_ADJACENTE",
        "razao": "conferi na foto: a parede é da cozinha mesmo",
    })
    assert resposta.status_code == 200
    assert "verde" in logado.get(f"/api/vistorias/{vistoria}/laudo").json()["texto"]


def test_decisao_invalida_e_recusada(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)
    pendencia = logado.get(f"/api/vistorias/{vistoria}/pendencias").json()[0]
    resposta = logado.post(f"/api/pendencias/{pendencia['id']}/decisao",
                           json={"decisao": "TALVEZ"})
    assert resposta.status_code == 400


def test_corrigir_sem_texto_e_recusado(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)
    pendencia = next(p for p in logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
                     if p["categoria"] == "piso")
    resposta = logado.post(f"/api/pendencias/{pendencia['id']}/decisao",
                           json={"decisao": "CORRIGIR", "correcao": "   "})
    assert resposta.status_code == 400


def test_pendencia_sobrevive_a_mudanca_do_texto(logado, vistoria, gemini_falso):
    """Regra 17: o vínculo é por ID. Editar o item não solta a pendência."""
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    pendencia = next(p for p in logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
                     if p["categoria"] == "piso")
    logado.patch(f"/api/itens/{pendencia['item_id']}",
                 json={"texto": "*Piso totalmente reescrito, em bom estado."})

    de_novo = next(p for p in logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
                   if p["id"] == pendencia["id"])
    assert de_novo["item_texto"] == "*Piso totalmente reescrito, em bom estado."
    assert logado.post(f"/api/pendencias/{pendencia['id']}/decisao",
                       json={"decisao": "OK"}).status_code == 200


def test_historico_registra_quem_mudou_o_que(logado, vistoria, gemini_falso):
    """Regra 41: texto anterior, atual, quando, quem, e qual pendência."""
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    pendencia = next(p for p in logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
                     if p["categoria"] == "piso")
    logado.post(f"/api/pendencias/{pendencia['id']}/decisao", json={
        "decisao": "CORRIGIR", "correcao": "*Piso em porcelanato, em bom estado.",
    })
    historico = logado.get(f"/api/itens/{pendencia['item_id']}/historico").json()
    assert len(historico) == 2                       # criação + correção
    assert historico[0]["origem"] == "ia"
    assert historico[1]["origem"] == "humano"
    assert historico[1]["pendencia_id"] == pendencia["id"]
    assert "cerâmica" in historico[1]["texto_anterior"]


def test_regra_so_e_adotada_explicitamente(logado, vistoria, gemini_falso):
    """Regra 22: nada de "corrigiu 10 vezes, o sistema aprendeu"."""
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    antes = len(logado.get("/api/regras").json())
    pendencia = next(p for p in logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
                     if p["categoria"] == "piso")
    # correção SEM regra: nada muda no conjunto de regras
    logado.post(f"/api/pendencias/{pendencia['id']}/decisao", json={
        "decisao": "CORRIGIR", "correcao": "*Piso em porcelanato, em bom estado."})
    assert len(logado.get("/api/regras").json()) == antes

    # só quando o campo REGRA é preenchido
    conflito = next(p for p in logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
                    if p["tipo"] == "scope_conflict")
    logado.post(f"/api/pendencias/{conflito['id']}/decisao", json={
        "decisao": "REMOVER",
        "regra": "Nunca descrever parede vista através de porta aberta como do cômodo fotografado.",
    })
    depois = logado.get("/api/regras").json()
    assert len(depois) == antes + 1
    assert any("porta aberta" in r["texto"] for r in depois)


def test_correcao_humana_e_guardada_estruturada(logado, vistoria, gemini_falso):
    """Regra 21: coleta estruturada — sem treinar nada (regra 22)."""
    from sqlalchemy import select
    from app.db import SessaoBanco
    from app.models import CorrecaoHumana

    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    conflito = next(p for p in logado.get(f"/api/vistorias/{vistoria}/pendencias").json()
                    if p["tipo"] == "scope_conflict")
    logado.post(f"/api/pendencias/{conflito['id']}/decisao", json={
        "decisao": "REMOVER", "tipo_correcao": "AMBIENTE_ADJACENTE",
        "razao": "a parede pertence ao corredor",
    })
    with SessaoBanco() as sessao:
        registros = sessao.scalars(
            select(CorrecaoHumana).where(CorrecaoHumana.vistoria_id == vistoria)
        ).all()
    assert len(registros) == 1
    assert registros[0].tipo == "AMBIENTE_ADJACENTE"
    assert registros[0].acao == "IGNORADA"
    assert "corredor" in registros[0].razao


# ==========================================================================
# Critério 12: exportação
# ==========================================================================

def test_exportar_txt(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    resposta = logado.get(f"/api/vistorias/{vistoria}/exportar/laudo.txt")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/plain")
    assert "attachment" in resposta.headers["content-disposition"]
    assert resposta.text.startswith("COZINHA")


def test_exportar_zip_no_layout_do_cli(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    resposta = logado.get(f"/api/vistorias/{vistoria}/exportar/vistoria.zip")
    assert resposta.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as zf:
        nomes = zf.namelist()
        assert "Laudo_Vistoria_Completo.txt" in nomes
        assert "Pendencias_Validacao.txt" in nomes
        assert "Cozinha/Cozinha_vistoria.txt" in nomes
        assert "Cozinha/_evidencias.json" in nomes
        assert any(n.startswith("Cozinha/") and n.endswith(".jpg") for n in nomes)
        # o .txt do cômodo tem o formato de sempre
        assert zf.read("Cozinha/Cozinha_vistoria.txt").decode("utf-8").startswith("COZINHA")


# ==========================================================================
# Critérios 13-17: reiniciar e continuar vendo tudo
# ==========================================================================

def test_tudo_sobrevive_ao_reinicio(logado, vistoria, gemini_falso):
    """Critérios 13 a 17: reiniciar o servidor e continuar vendo a vistoria,
    as fotos, o laudo e as pendências."""
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    antes = {
        "laudo": logado.get(f"/api/vistorias/{vistoria}/laudo").json()["texto"],
        "pendencias": len(logado.get(f"/api/vistorias/{vistoria}/pendencias").json()),
        "fotos": len(logado.get(f"/api/comodos/{comodo}/fotos").json()),
        "evidencias": len(logado.get(f"/api/comodos/{comodo}/evidencias").json()),
    }
    assert antes["laudo"] and antes["pendencias"] and antes["fotos"] == 2

    # "reinicia": novo ciclo de vida da aplicação, mesmo banco e mesmo disco
    with TestClient(app) as outro:
        outro.post("/api/auth/login", json={"email": EMAIL, "senha": SENHA})
        depois = {
            "laudo": outro.get(f"/api/vistorias/{vistoria}/laudo").json()["texto"],
            "pendencias": len(outro.get(f"/api/vistorias/{vistoria}/pendencias").json()),
            "fotos": len(outro.get(f"/api/comodos/{comodo}/fotos").json()),
            "evidencias": len(outro.get(f"/api/comodos/{comodo}/evidencias").json()),
        }
        assert depois == antes
        # e a foto ainda abre do disco
        foto = outro.get(f"/api/comodos/{comodo}/fotos").json()[0]
        assert outro.get(f"/api/fotos/{foto['id']}/arquivo").status_code == 200


def test_job_interrompido_por_reinicio_e_sinalizado():
    """Regra 26: um job PROCESSANDO que morreu com o processo não pode ficar
    eternamente 'em andamento' — mas os cômodos concluídos continuam."""
    from sqlalchemy import select
    from app.db import SessaoBanco
    from app.jobs import recuperar_jobs_orfaos
    from app.models import (Comodo, EstadoComodo, EstadoJob, Job, Vistoria)

    with SessaoBanco() as sessao:
        v = Vistoria(titulo="interrompida")
        sessao.add(v)
        sessao.flush()
        concluido = Comodo(vistoria_id=v.id, nome="Pronto", estado=EstadoComodo.CONCLUIDO)
        no_meio = Comodo(vistoria_id=v.id, nome="No meio", estado=EstadoComodo.PROCESSANDO)
        sessao.add_all([concluido, no_meio,
                        Job(vistoria_id=v.id, tipo="laudo", estado=EstadoJob.PROCESSANDO)])
        sessao.commit()
        ids = (v.id, concluido.id, no_meio.id)

    assert recuperar_jobs_orfaos() >= 1

    with SessaoBanco() as sessao:
        assert sessao.get(Comodo, ids[1]).estado == EstadoComodo.CONCLUIDO
        assert sessao.get(Comodo, ids[2]).estado == EstadoComodo.PENDENTE
        job = sessao.scalar(select(Job).where(Job.vistoria_id == ids[0]))
        assert job.estado == EstadoJob.FALHOU
        assert "reiniciado" in job.erro


# ==========================================================================
# Importação da vistoria antiga (regra 42)
# ==========================================================================

def test_importar_vistoria_antiga(logado):
    laudo = (
        "COZINHA\n\n"
        "Paredes:\n*Paredes em revestimento cerâmico na cor branca, em bom estado.\n\n"
        "Piso:\n*Piso em cerâmica na cor Crômio, em bom estado.\n\n"
        "OBS:\nSem observações.\n"
    )
    dados = zip_de({
        "Cozinha/foto1.jpg": jpeg(),
        "Cozinha/Cozinha_vistoria.txt": laudo.encode("utf-8"),
        "Laudo_Vistoria_Completo.txt": laudo.encode("utf-8"),
    })
    resposta = logado.post("/api/importar",
                           data={"titulo": "Vistoria antiga", "notas": "importada"},
                           files={"arquivo": ("antiga.zip", dados, "application/zip")})
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["fotos_importadas"] == 1
    assert corpo["comodos_com_laudo"] == 1

    vistoria_id = corpo["vistoria"]["id"]
    texto = logado.get(f"/api/vistorias/{vistoria_id}/laudo").json()["texto"]
    assert "revestimento cerâmico na cor branca" in texto


def test_importacao_nao_inventa_evidencia(logado):
    """Regra 42: não inventar dados que o arquivo antigo não tem. O laudo
    importado não ganha evidências fabricadas."""
    laudo = "SALA\n\nParedes:\n*Paredes em pintura branca, em bom estado.\n"
    dados = zip_de({"Sala/Sala_vistoria.txt": laudo.encode("utf-8"),
                    "Sala/f.jpg": jpeg()})
    resposta = logado.post("/api/importar", data={"titulo": "Sem evidência"},
                           files={"arquivo": ("a.zip", dados, "application/zip")})
    vistoria_id = resposta.json()["vistoria"]["id"]
    comodo = logado.get(f"/api/vistorias/{vistoria_id}").json()["lista_comodos"][0]
    assert logado.get(f"/api/comodos/{comodo['id']}/evidencias").json() == []


# ==========================================================================
# A chave do Gemini nunca sai (critério 18)
# ==========================================================================

def test_nenhuma_resposta_contem_a_chave(logado, vistoria, gemini_falso):
    gemini_falso(roteiro_padrao())
    comodo = criar_comodo(logado, vistoria)
    enviar(logado, comodo, [("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg")])
    processar(logado, vistoria)

    rotas = [
        "/api/saude", "/api/vistorias", "/api/regras",
        f"/api/vistorias/{vistoria}", f"/api/vistorias/{vistoria}/laudo",
        f"/api/vistorias/{vistoria}/pendencias", f"/api/comodos/{comodo}/evidencias",
        f"/api/vistorias/{vistoria}/exportar/laudo.txt",
    ]
    for rota in rotas:
        corpo = logado.get(rota).text
        assert "chave-falsa-de-teste" not in corpo, rota
        assert "GEMINI_API_KEY" not in corpo, rota
