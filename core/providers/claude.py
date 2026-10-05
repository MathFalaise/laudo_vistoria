"""
Provedor CLAUDE — API de Mensagens da Anthropic, via HTTP.

Usado como VALIDADOR visual (core/validacao_visual.py): recebe a foto e as
evidências e devolve uma decisão estruturada. Não escreve laudo.

Formato (documentação oficial da API de Mensagens): POST /v1/messages com
`x-api-key` e `anthropic-version`; imagem como bloco `image` em base64. A
saída estruturada vem por USO FORÇADO DE FERRAMENTA: uma ferramenta
"responder" cujo `input_schema` é o schema pedido, com `tool_choice` apontando
para ela — o modelo só pode responder preenchendo o schema.

O modelo é OBRIGATÓRIO em CLAUDE_MODEL: nenhum nome de modelo fica fixo no
código (pedido explícito; muda com o tempo e com o preço). Não se usa o SDK:
o HTTP direto é estável, já tem a dependência (`httpx`) e não traz vantagem
para este uso.
"""

from __future__ import annotations

import json
import os
import time

import httpx

from core import telemetria
from core.providers.base import (ConfiguracaoAusente, FalhaDoProvedor, Imagem, Provedor,
                                 RespostaCortada)
from core.providers.esquema import para_json_schema
from core.providers.http import TEMPO_LIMITE_HTTP, postar

BASE_URL_PADRAO = "https://api.anthropic.com"
VERSAO_API = "2023-06-01"
NOME_FERRAMENTA = "responder"


class ProvedorClaude(Provedor):
    nome = "claude"

    def __init__(self, chave: str | None = None, modelo: str | None = None,
                 base_url: str | None = None, transport: httpx.BaseTransport | None = None,
                 dormir=time.sleep):
        self._chave = chave or os.environ.get("CLAUDE_API_KEY", "")
        if not self._chave:
            raise ConfiguracaoAusente("Defina CLAUDE_API_KEY para usar o provedor claude.")
        self.modelo = modelo or os.environ.get("CLAUDE_MODEL", "")
        if not self.modelo:
            raise ConfiguracaoAusente(
                "Defina CLAUDE_MODEL com o modelo Claude a usar (nenhum é fixado no código).")
        self.base_url = (base_url or os.environ.get("CLAUDE_BASE_URL") or BASE_URL_PADRAO).rstrip("/")
        self._http = httpx.Client(timeout=TEMPO_LIMITE_HTTP, transport=transport)
        self._dormir = dormir

    def _corpo(self, partes: list, esquema: dict, max_tokens: int) -> dict:
        conteudo = []
        for parte in partes:
            if isinstance(parte, Imagem):
                conteudo.append({"type": "image", "source": {
                    "type": "base64", "media_type": parte.mime, "data": parte.base64()}})
            else:
                conteudo.append({"type": "text", "text": str(parte)})
        return {
            "model": self.modelo, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": conteudo}],
            "tools": [{"name": NOME_FERRAMENTA,
                       "description": "Devolve a resposta no formato estruturado pedido.",
                       "input_schema": para_json_schema(esquema)}],
            "tool_choice": {"type": "tool", "name": NOME_FERRAMENTA},
        }

    def gerar_json(self, partes: list, esquema: dict, max_tokens: int,
                   descricao: str, tipo: str = "") -> str:
        inicio = time.monotonic()
        imagens = sum(1 for parte in partes if isinstance(parte, Imagem))
        tentativas, dados = 1, None
        try:
            resposta, tentativas = postar(
                self._http, f"{self.base_url}/v1/messages",
                self._corpo(partes, esquema, max_tokens),
                {"x-api-key": self._chave, "anthropic-version": VERSAO_API},
                descricao, "Claude", self._dormir,
            )
            try:
                dados = resposta.json()
                blocos = dados["content"]
            except (ValueError, KeyError, TypeError) as erro:
                raise FalhaDoProvedor(f"resposta do Claude fora do formato esperado em {descricao}") from erro
            if dados.get("stop_reason") == "max_tokens":
                raise RespostaCortada(
                    f"A resposta do Claude para {descricao} foi cortada pelo limite de "
                    "max_tokens antes de terminar.")
            entrada = next((bloco.get("input") for bloco in blocos
                            if isinstance(bloco, dict) and bloco.get("type") == "tool_use"
                            and bloco.get("name") == NOME_FERRAMENTA), None)
            if not isinstance(entrada, dict):
                raise FalhaDoProvedor(f"o Claude não devolveu a resposta estruturada em {descricao}")
        except Exception as erro:
            self._registrar(tipo, False, inicio, tentativas, imagens, dados, erro)
            raise
        self._registrar(tipo, True, inicio, tentativas, imagens, dados)
        return json.dumps(entrada, ensure_ascii=False)

    def _registrar(self, tipo, sucesso, inicio, tentativas, imagens, dados, erro=None):
        uso = (dados or {}).get("usage") if isinstance(dados, dict) else None
        uso = uso if isinstance(uso, dict) else {}
        entrada, saida = uso.get("input_tokens"), uso.get("output_tokens")
        telemetria.registrar(telemetria.RegistroChamada(
            provedor=self.nome, modelo=self.modelo, tipo=tipo, sucesso=sucesso,
            duracao_s=round(time.monotonic() - inicio, 3), tentativas=tentativas,
            imagens=imagens, tokens_entrada=entrada, tokens_saida=saida,
            tokens_total=(entrada + saida) if entrada is not None and saida is not None else None,
            erro=erro.__class__.__name__ if erro else "",
        ))
