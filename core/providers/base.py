"""
Contrato comum dos provedores de modelo (Gemini, GLM, Claude).

O motor (`core/gemini_client.py`, `core/validacao_visual.py`) fala só com
este contrato: uma lista de partes (texto e `Imagem`), um schema neutro (ver
`core/providers/esquema.py`) e um teto de saída. Volta o TEXTO JSON da
resposta, sem nenhum objeto de SDK. O que cada provedor faz por baixo
(SDK do Google, HTTP compatível com OpenAI, API da Anthropic) não vaza daqui.

Erros também são do contrato, não do provedor:
- `RespostaCortada`: o modelo bateu no teto de saída antes de fechar o JSON;
- `FalhaDoProvedor`: a chamada não deu certo depois das novas tentativas
  (rede, 5xx, 429, resposta sem conteúdo). A mensagem nunca leva a chave nem
  o conteúdo da imagem.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass


@dataclass(frozen=True)
class Imagem:
    """Uma imagem pronta para ir a qualquer provedor: os bytes já
    redimensionados e o tipo MIME. É o que `core.image_utils` produz.

    `__repr__` não mostra os bytes: uma imagem de cliente não pode cair num
    log por acidente só porque alguém imprimiu uma lista de partes."""

    dados: bytes
    mime: str = "image/jpeg"

    def base64(self) -> str:
        return base64.b64encode(self.dados).decode("ascii")

    def __repr__(self) -> str:
        return f"Imagem({self.mime}, {len(self.dados)} bytes)"


class ErroDoProvedor(RuntimeError):
    """Base dos erros de provedor."""


class FalhaDoProvedor(ErroDoProvedor):
    """A chamada falhou depois das tentativas, ou foi recusada (4xx)."""


class RespostaCortada(ErroDoProvedor):
    """O modelo atingiu o teto de saída antes de terminar o JSON."""


class ConfiguracaoAusente(ErroDoProvedor):
    """Falta chave, modelo ou endereço para criar o provedor."""


class Provedor:
    """Interface. `nome` e `modelo` vão para a telemetria e para a
    rastreabilidade da evidência ("quem viu isto")."""

    nome: str = ""
    modelo: str = ""

    def gerar_json(self, partes: list, esquema: dict, max_tokens: int,
                   descricao: str, tipo: str = "") -> str:
        """Devolve o texto JSON da resposta. `partes` mistura `str` e
        `Imagem`, na ordem em que o modelo deve recebê-las. `tipo` é o tipo
        da chamada para a telemetria (analise, escopo, validacao...)."""
        raise NotImplementedError

    def __repr__(self) -> str:
        # Nunca a chave: só quem é e qual modelo.
        return f"{self.__class__.__name__}({self.nome}, {self.modelo})"


def esperas(tentativas: int, base: float) -> list:
    """Espera antes de cada nova tentativa: base x 1, base x 2, ..."""
    return [base * tentativa for tentativa in range(1, tentativas)]
