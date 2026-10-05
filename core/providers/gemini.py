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

import time

import httpx

from core import telemetria
from core.providers.base import ConfiguracaoAusente, Imagem, Provedor, RespostaCortada

MAX_TENTATIVAS = 4
ESPERA_BASE_SEGUNDOS = 10
TEMPO_LIMITE_CHAMADA_SEGUNDOS = 300


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

    def __init__(self, cliente=None, modelo: str | None = None, dormir=time.sleep):
        from core.config import MODEL_NAME

        self.cliente = cliente if cliente is not None else criar_cliente_genai()
        self.modelo = modelo or MODEL_NAME
        self._dormir = dormir

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
        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_schema=types.Schema.model_validate(esquema),
        )
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
