"""
Provedor GLM — GLM-5.3-Flash pelo OpenCode Zen (gateway), via HTTP.

O que foi conferido na documentação oficial em 05/10/2026, antes de
escrever isto (nada aqui é exemplo antigo da internet):

- opencode.ai/docs/zen: `glm-5.3-flash` é servido em
  `https://opencode.ai/zen/v1/chat/completions`, no formato compatível com
  OpenAI, autenticação `Authorization: Bearer <chave>`; US$ 0,15 / 0,50 por
  milhão de tokens (entrada/saída). Os provedores do Zen têm retenção zero e
  não treinam com os dados, exceto modelos gratuitos (este é pago);
- models.dev (registro de modelos mantido pelo OpenCode): GLM-5.3-Flash é
  multimodal nativo (entrada texto, imagem, vídeo, PDF), com saída
  estruturada.

O que NÃO está documentado e só um teste real confirma: que o Zen repassa a
imagem ao modelo e aceita `response_format` com JSON Schema. Por isso o
formato é configurável (GLM_FORMATO_RESPOSTA) e há teste de integração
opcional (INTEGRATION_TESTS=1). O modelo não roda localmente: isto é cliente
de API.
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

BASE_URL_PADRAO = "https://opencode.ai/zen/v1"
MODELO_PADRAO = "glm-5.3-flash"
FORMATOS = ("json_schema", "json_object")


class ProvedorGLM(Provedor):
    nome = "glm"

    def __init__(self, chave: str | None = None, base_url: str | None = None,
                 modelo: str | None = None, formato: str | None = None,
                 transport: httpx.BaseTransport | None = None, dormir=time.sleep):
        self._chave = chave or os.environ.get("GLM_API_KEY", "")
        if not self._chave:
            raise ConfiguracaoAusente(
                "Defina GLM_API_KEY (chave do OpenCode Zen) para usar o provedor glm.")
        self.base_url = (base_url or os.environ.get("GLM_BASE_URL") or BASE_URL_PADRAO).rstrip("/")
        self.modelo = modelo or os.environ.get("GLM_MODEL") or MODELO_PADRAO
        self.formato = formato or os.environ.get("GLM_FORMATO_RESPOSTA") or "json_schema"
        if self.formato not in FORMATOS:
            raise ConfiguracaoAusente(f"GLM_FORMATO_RESPOSTA deve ser um de {FORMATOS}")
        try:
            self._extra = json.loads(os.environ.get("GLM_PARAMETROS_EXTRA", "") or "{}")
        except ValueError as erro:
            raise ConfiguracaoAusente("GLM_PARAMETROS_EXTRA não é JSON válido") from erro
        self._http = httpx.Client(timeout=TEMPO_LIMITE_HTTP, transport=transport)
        self._dormir = dormir

    def _corpo(self, partes: list, esquema: dict, max_tokens: int) -> dict:
        conteudo = []
        for parte in partes:
            if isinstance(parte, Imagem):
                conteudo.append({"type": "image_url", "image_url": {
                    "url": f"data:{parte.mime};base64,{parte.base64()}"}})
            else:
                conteudo.append({"type": "text", "text": str(parte)})
        schema = para_json_schema(esquema)
        if self.formato == "json_schema":
            formato = {"type": "json_schema", "json_schema": {
                "name": "resposta", "schema": schema, "strict": False}}
        else:
            # Sem JSON Schema no gateway: pede objeto JSON e põe o schema no
            # texto. O código valida a resposta do mesmo jeito.
            formato = {"type": "json_object"}
            conteudo.append({"type": "text", "text": (
                "Responda SOMENTE com um objeto JSON válido, sem texto antes ou depois, "
                "que siga este JSON Schema:\n" + json.dumps(schema, ensure_ascii=False))})
        return {"model": self.modelo, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": conteudo}],
                "response_format": formato, **self._extra}

    def gerar_json(self, partes: list, esquema: dict, max_tokens: int,
                   descricao: str, tipo: str = "") -> str:
        inicio = time.monotonic()
        imagens = sum(1 for parte in partes if isinstance(parte, Imagem))
        tentativas, dados = 1, None
        try:
            resposta, tentativas = postar(
                self._http, f"{self.base_url}/chat/completions",
                self._corpo(partes, esquema, max_tokens),
                {"Authorization": f"Bearer {self._chave}"},
                descricao, "GLM", self._dormir,
            )
            try:
                dados = resposta.json()
                escolha = dados["choices"][0]
                texto = escolha["message"].get("content")
            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as erro:
                raise FalhaDoProvedor(f"resposta do GLM fora do formato esperado em {descricao}") from erro
            if escolha.get("finish_reason") == "length":
                raise RespostaCortada(
                    f"A resposta do GLM para {descricao} foi cortada pelo limite de "
                    "max_tokens antes de terminar o JSON.")
            if not texto or not str(texto).strip():
                raise FalhaDoProvedor(f"o GLM devolveu resposta vazia em {descricao}")
        except Exception as erro:
            self._registrar(tipo, False, inicio, tentativas, imagens, dados, erro)
            raise
        self._registrar(tipo, True, inicio, tentativas, imagens, dados)
        return str(texto)

    def _registrar(self, tipo, sucesso, inicio, tentativas, imagens, dados, erro=None):
        uso = (dados or {}).get("usage") if isinstance(dados, dict) else None
        uso = uso if isinstance(uso, dict) else {}
        telemetria.registrar(telemetria.RegistroChamada(
            provedor=self.nome, modelo=self.modelo, tipo=tipo, sucesso=sucesso,
            duracao_s=round(time.monotonic() - inicio, 3), tentativas=tentativas,
            imagens=imagens, tokens_entrada=uso.get("prompt_tokens"),
            tokens_saida=uso.get("completion_tokens"), tokens_total=uso.get("total_tokens"),
            erro=erro.__class__.__name__ if erro else "",
        ))
