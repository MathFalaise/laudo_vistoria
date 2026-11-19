"""
Provedor GEMINI — o mesmo comportamento que o motor sempre teve.

Tudo aqui é o que estava em `gemini_client._gerar_com_retry` até 05/10/2026,
mudado de lugar, não de comportamento:

- nova tentativa com espera crescente SÓ em 503 (`errors.ServerError`) e
  falha de rede/tempo limite (`httpx.TransportError`); 429 não tenta de novo
  (cota diária estourada não volta em segundos);
- limite de 5 min por chamada (TEMPO_LIMITE_CHAMADA_SEGUNDOS): em
  18/09/2026 uma conexão pendurada travou o script 10+ min sem erro;
- resposta cortada por max_output_tokens é erro, não JSON pela metade.

A camada paga é obrigatória (CLAUDE.md, regra 1): a gratuita permite ao
Google usar as fotos de cliente.
"""

from __future__ import annotations

import os
import time

import httpx

from core import telemetria
from core.providers.base import ConfiguracaoAusente, Imagem, Provedor, RespostaCortada

MAX_TENTATIVAS = 4
ESPERA_BASE_SEGUNDOS = 10
TEMPO_LIMITE_CHAMADA_SEGUNDOS = 300

_RESOLUCOES_MIDIA = {
    "low": "MEDIA_RESOLUTION_LOW",
    "medium": "MEDIA_RESOLUTION_MEDIUM",
    "high": "MEDIA_RESOLUTION_HIGH",
}
_NIVEIS_RACIOCINIO = {"low", "medium", "high"}
_NIVEIS_POR_MODELO = {
    "gemini-3.8-flash": {"low", "medium", "high"},
    "gemini-3.7-flash": {"low", "medium", "high"},
    "gemini-3.6-flash": _NIVEIS_RACIOCINIO,
    "gemini-3.5-flash": _NIVEIS_RACIOCINIO,
    "gemini-3.5-flash-lite": _NIVEIS_RACIOCINIO,
}


def criar_cliente_genai(chave: str | None = None):
    """O `genai.Client` com o tempo limite do projeto."""
    from google import genai
    from google.genai import types

    from core.config import API_KEY

    chave = chave or API_KEY
    if not chave:
        raise ConfiguracaoAusente(
            "Defina a variável de ambiente GEMINI_API_KEY antes de rodar o script "
            "(gere uma em https://aistudio.google.com/apikey, num projeto com "
            "faturamento ativo — ver CLAUDE.md)."
        )
    return genai.Client(
        api_key=chave,
        http_options=types.HttpOptions(timeout=TEMPO_LIMITE_CHAMADA_SEGUNDOS * 1000),
    )


class ProvedorGemini(Provedor):
    """`cliente` é qualquer objeto com `.models.generate_content(model,
    contents, config)` — o `genai.Client` de verdade ou o falso dos testes."""

    nome = "gemini"

    def __init__(
        self,
        cliente=None,
        modelo: str | None = None,
        dormir=time.sleep,
        media_resolution: str | None = None,
        thinking_level: str | None = None,
    ):
        from core.config import (
            GEMINI_MEDIA_RESOLUTION,
            GEMINI_THINKING_LEVEL,
            MODEL_NAME,
        )

        self.cliente = cliente if cliente is not None else criar_cliente_genai()
        # A variável é lida também aqui (e não só no import de config.py), para
        # permitir trocar o modelo em processos de benchmark/teste controlados.
        modelo_env = os.environ.get("GEMINI_MODEL", "").strip()
        self.modelo = modelo or modelo_env or MODEL_NAME
        self.media_resolution = (
            media_resolution if media_resolution is not None
            else os.environ.get("GEMINI_MEDIA_RESOLUTION", GEMINI_MEDIA_RESOLUTION)
        ).strip().lower()
        self.thinking_level = (
            thinking_level if thinking_level is not None
            else os.environ.get("GEMINI_THINKING_LEVEL", GEMINI_THINKING_LEVEL)
        ).strip().lower()
        self._dormir = dormir

    def _montar_config(self, types, esquema: dict, max_tokens: int):
        """Monta a configuração sem alterar o pedido quando a calibração está vazia.

        Os parâmetros opcionais só são enviados quando foram explicitamente
        definidos e o SDK instalado declara suporte ao campo correspondente.
        """
        campos_suportados = getattr(types.GenerateContentConfig, "model_fields", {})
        opcoes = {
            "max_output_tokens": max_tokens,
            "response_mime_type": "application/json",
            "response_schema": types.Schema.model_validate(esquema),
        }

        if self.media_resolution:
            nome_enum = _RESOLUCOES_MIDIA.get(self.media_resolution)
            if nome_enum is None:
                raise ConfiguracaoAusente(
                    f"GEMINI_MEDIA_RESOLUTION inválida: {self.media_resolution!r} "
                    f"(use: {', '.join(_RESOLUCOES_MIDIA)})."
                )
            enum_cls = getattr(types, "MediaResolution", None)
            if (
                "media_resolution" not in campos_suportados
                or enum_cls is None
                or not hasattr(enum_cls, nome_enum)
            ):
                raise ConfiguracaoAusente(
                    "O SDK google-genai instalado não suporta media_resolution "
                    "em GenerateContentConfig."
                )
            opcoes["media_resolution"] = getattr(enum_cls, nome_enum)

        if self.thinking_level:
            niveis_modelo = _NIVEIS_POR_MODELO.get(self.modelo, _NIVEIS_RACIOCINIO)
            if self.thinking_level not in niveis_modelo:
                raise ConfiguracaoAusente(
                    f"GEMINI_THINKING_LEVEL {self.thinking_level!r} não é suportado "
                    f"pelo modelo {self.modelo!r}; use: {', '.join(sorted(niveis_modelo))}."
                )
            thinking_cls = getattr(types, "ThinkingConfig", None)
            thinking_fields = getattr(thinking_cls, "model_fields", {}) if thinking_cls else {}
            if (
                "thinking_config" not in campos_suportados
                or "thinking_level" not in thinking_fields
            ):
                raise ConfiguracaoAusente(
                    "O SDK google-genai instalado não suporta thinking_level "
                    "em ThinkingConfig."
                )
            opcoes["thinking_config"] = thinking_cls(thinking_level=self.thinking_level.upper())

        return types.GenerateContentConfig(**opcoes)

    @staticmethod
    def _parte(parte):
        from google.genai import types

        if isinstance(parte, Imagem):
            return types.Part.from_bytes(data=parte.dados, mime_type=parte.mime)
        return parte

    def gerar_json(self, partes: list, esquema: dict, max_tokens: int,
                   descricao: str, tipo: str = "") -> str:
        from google.genai import errors, types

        conteudo = [self._parte(parte) for parte in partes]
        config = self._montar_config(types, esquema, max_tokens)
        inicio = time.monotonic()
        imagens = sum(1 for parte in partes if isinstance(parte, Imagem))
        resposta, tentativa = None, 0
        try:
            for tentativa in range(1, MAX_TENTATIVAS + 1):
                try:
                    resposta = self.cliente.models.generate_content(
                        model=self.modelo, contents=conteudo, config=config,
                    )
                    break
                except (errors.ServerError, httpx.TransportError) as erro:
                    # TransportError cobre o tempo limite estourado e quedas de rede.
                    if tentativa == MAX_TENTATIVAS:
                        raise
                    espera = ESPERA_BASE_SEGUNDOS * tentativa
                    print(
                        f"  Falha transitória no Gemini para {descricao} "
                        f"({erro.__class__.__name__}), tentativa {tentativa}/{MAX_TENTATIVAS}. "
                        f"Aguardando {espera}s...",
                        flush=True,
                    )
                    self._dormir(espera)

            candidato = resposta.candidates[0] if resposta.candidates else None
            if candidato is not None and candidato.finish_reason == types.FinishReason.MAX_TOKENS:
                raise RespostaCortada(
                    f"A resposta do modelo para {descricao} foi cortada por "
                    "atingir o limite de max_output_tokens antes de terminar o JSON. "
                    "Aumente max_output_tokens em gemini_client.py e tente novamente."
                )
        except Exception as erro:
            self._registrar(tipo, False, inicio, tentativa, imagens, resposta, erro)
            raise
        self._registrar(tipo, True, inicio, tentativa, imagens, resposta)
        return resposta.text

    def _registrar(self, tipo, sucesso, inicio, tentativas, imagens, resposta, erro=None):
        uso = getattr(resposta, "usage_metadata", None)
        telemetria.registrar(telemetria.RegistroChamada(
            provedor=self.nome, modelo=self.modelo, tipo=tipo, sucesso=sucesso,
            duracao_s=round(time.monotonic() - inicio, 3), tentativas=max(1, tentativas),
            imagens=imagens,
            tokens_entrada=getattr(uso, "prompt_token_count", None),
            tokens_saida=getattr(uso, "candidates_token_count", None),
            tokens_total=getattr(uso, "total_token_count", None),
            erro=erro.__class__.__name__ if erro else "",
        ))
