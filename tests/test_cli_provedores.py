"""
main.py com provedor FALSO: o CLI escolhe provedor e validador pelas opções,
grava o laudo como sempre e deixa a telemetria das chamadas na raiz do
imóvel. Nenhuma API é chamada.
"""

import json
import sys

import pytest
from PIL import Image

import main
from core.config import CATEGORIAS
from core.providers import Provedor


class _Falso(Provedor):
    def __init__(self, nome="glm", modelo="glm-5.3-flash"):
        self.nome, self.modelo, self.tipos = nome, modelo, []

    def gerar_json(self, partes, esquema, max_tokens, descricao, tipo=""):
        from core import telemetria
        self.tipos.append(tipo)
        telemetria.registrar(telemetria.RegistroChamada(
            provedor=self.nome, modelo=self.modelo, tipo=tipo, sucesso=True, duracao_s=0.1,
            tokens_entrada=1000, tokens_saida=100))
        dados = {c: [{"texto": "Não se aplica.", "motivo": "", "certeza": 95}] for c in CATEGORIAS}
        dados["piso"] = [{"texto": "*Piso em cerâmica na cor cinza, em bom estado.",
                          "motivo": "", "certeza": 95}]
        return json.dumps(dados, ensure_ascii=False)


@pytest.fixture
def imovel(tmp_path):
    comodo = tmp_path / "Imovel" / "Sala"
    comodo.mkdir(parents=True)
    Image.new("RGB", (32, 32), "white").save(comodo / "f1.jpg")
    return tmp_path / "Imovel"


def _rodar(monkeypatch, imovel, *opcoes):
    falso = _Falso()
    monkeypatch.setattr(main, "criar_cliente", lambda: falso)
    # setenv (e não delenv): o main.py grava as escolhas em os.environ, e só o
    # setenv garante que o valor original volta depois do teste.
    for nome in ("VISION_PROVIDER", "VALIDATION_ENABLED", "VALIDATOR_PROVIDER"):
        monkeypatch.setenv(nome, "")
    monkeypatch.setattr(sys, "argv", ["main.py", str(imovel), "--classico", "--sem-conferencia", *opcoes])
    main.main()
    return falso


def test_cli_grava_laudo_e_telemetria(monkeypatch, imovel, capsys):
    falso = _rodar(monkeypatch, imovel)
    assert (imovel / "Sala" / "Sala_vistoria.txt").read_text(encoding="utf-8").count("cerâmica") == 1
    telemetria = json.loads((imovel / "Telemetria_Modelos.json").read_text(encoding="utf-8"))
    assert telemetria["chamadas"][0]["contexto"]["comodo"] == "Sala"
    assert telemetria["resumo"]["glm:glm-5.3-flash"]["custo_usd"] == round(1000 / 1e6 * 0.15 + 100 / 1e6 * 0.5, 6)
    assert falso.tipos == ["analise"]
    assert "Analista: glm (glm-5.3-flash)" in capsys.readouterr().out


def test_cli_validador_fora_da_v2_e_ignorado(monkeypatch, imovel, capsys):
    monkeypatch.setenv("CLAUDE_API_KEY", "k")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-qualquer")
    _rodar(monkeypatch, imovel, "--validador", "claude")
    assert "só existe no motor --evidencias" in capsys.readouterr().out
