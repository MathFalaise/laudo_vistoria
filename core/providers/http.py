"""
POST com novas tentativas, comum aos provedores HTTP (GLM e Claude).

Repete em: falha de rede e tempo limite (`httpx.TransportError`), 5xx e 429.
O 429 aqui é limite de VAZÃO (por minuto), não a cota diária do Gemini:
espera o `Retry-After` do servidor, com teto, e tenta de novo. Erro 4xx de
outro tipo (chave errada, modelo inexistente, pedido inválido) não melhora
repetindo — falha na hora.

A mensagem de erro leva o status e um trecho curto do corpo de erro da API,
nunca a chave nem o pedido (que carrega a imagem do cliente).
"""

from __future__ import annotations

import time

import httpx

from core.providers.base import FalhaDoProvedor

TENTATIVAS_HTTP = 4
ESPERA_BASE_HTTP = 5
ESPERA_MAXIMA_RETRY_AFTER = 60
TEMPO_LIMITE_HTTP = 300          # o mesmo teto por chamada do Gemini
_TRECHO_ERRO = 200


def _retry_after(resposta: httpx.Response) -> float | None:
    valor = resposta.headers.get("retry-after", "").strip()
    try:
        return min(float(valor), ESPERA_MAXIMA_RETRY_AFTER) if valor else None
    except ValueError:
        return None


def _resumo_erro(resposta: httpx.Response) -> str:
    try:
        corpo = resposta.json()
        erro = corpo.get("error", corpo) if isinstance(corpo, dict) else corpo
        if isinstance(erro, dict):
            texto = " ".join(str(erro.get(chave, "")) for chave in ("type", "message")).strip()
        else:
            texto = str(erro)
    except ValueError:
        texto = resposta.text
    texto = " ".join(texto.split())
    return texto[:_TRECHO_ERRO] + ("..." if len(texto) > _TRECHO_ERRO else "")


def postar(cliente: httpx.Client, url: str, corpo: dict, cabecalhos: dict,
           descricao: str, nome_provedor: str, dormir=time.sleep) -> tuple:
    """Devolve (resposta, tentativas). Levanta FalhaDoProvedor no fim."""
    ultima = ""
    for tentativa in range(1, TENTATIVAS_HTTP + 1):
        try:
            resposta = cliente.post(url, json=corpo, headers=cabecalhos)
        except httpx.TransportError as erro:
            ultima = erro.__class__.__name__
            espera = None
        else:
            if resposta.status_code < 400:
                return resposta, tentativa
            ultima = f"HTTP {resposta.status_code}: {_resumo_erro(resposta)}"
            if resposta.status_code != 429 and resposta.status_code < 500:
                raise FalhaDoProvedor(f"{nome_provedor} recusou {descricao} ({ultima})")
            espera = _retry_after(resposta)
        if tentativa == TENTATIVAS_HTTP:
            break
        espera = espera if espera is not None else ESPERA_BASE_HTTP * tentativa
        print(f"  Falha transitória no {nome_provedor} para {descricao} ({ultima.split(':')[0]}), "
              f"tentativa {tentativa}/{TENTATIVAS_HTTP}. Aguardando {espera:g}s...", flush=True)
        dormir(espera)
    raise FalhaDoProvedor(
        f"{nome_provedor} falhou em {descricao} depois de {TENTATIVAS_HTTP} tentativas ({ultima})")
