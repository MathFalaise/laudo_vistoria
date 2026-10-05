"""
PROVEDORES de modelo: quem o motor chama para olhar as fotos e para validar.

    VISION_PROVIDER     analista visual: evidências, segunda olhada, inventário
                        e as chamadas de texto do motor (redação, repetidos...)
    VALIDATOR_PROVIDER  validador visual seletivo (só com VALIDATION_ENABLED=1)

Valores: gemini | glm | claude. O padrão continua sendo o Gemini e o
validador desligado: trocar o modelo que gera os laudos exige teste real de
ponta a ponta (CLAUDE.md), e mandar fotos de cliente a um provedor novo é
decisão do vistoriador (LGPD), não um efeito colateral de atualizar o código.

As escolhas são lidas do ambiente NA HORA de criar o provedor, não na
importação — o mesmo processo pode comparar provedores (benchmark).
"""

from __future__ import annotations

import os

from core.providers.base import (ConfiguracaoAusente, ErroDoProvedor, FalhaDoProvedor, Imagem,
                                 Provedor, RespostaCortada)

PROVEDORES = ("gemini", "glm", "claude")

__all__ = [
    "PROVEDORES", "ConfiguracaoAusente", "ErroDoProvedor", "FalhaDoProvedor", "Imagem",
    "Provedor", "RespostaCortada", "ProvedorComReserva", "como_provedor", "criar_provedor",
    "provedor_de_visao", "provedor_validador", "validacao_ligada",
]


def criar_provedor(nome: str, **opcoes) -> Provedor:
    nome = (nome or "").strip().lower()
    if nome == "gemini":
        from core.providers.gemini import ProvedorGemini
        return ProvedorGemini(**opcoes)
    if nome == "glm":
        from core.providers.glm import ProvedorGLM
        return ProvedorGLM(**opcoes)
    if nome == "claude":
        from core.providers.claude import ProvedorClaude
        return ProvedorClaude(**opcoes)
    raise ConfiguracaoAusente(f"provedor desconhecido: {nome!r} (use um de {PROVEDORES})")


class ProvedorComReserva(Provedor):
    """Usa o principal; se ELE falhar (rede, 5xx, recusa, resposta cortada),
    repete a MESMA chamada no reserva. Só existe se VISION_FALLBACK_PROVIDER
    estiver configurado — nunca por padrão. A reserva não inventa nada: é a
    mesma pergunta, com as mesmas fotos, a outro modelo."""

    def __init__(self, principal: Provedor, reserva: Provedor):
        self.principal, self.reserva = principal, reserva
        self.nome = principal.nome
        self.modelo = principal.modelo

    def gerar_json(self, partes, esquema, max_tokens, descricao, tipo=""):
        try:
            return self.principal.gerar_json(partes, esquema, max_tokens, descricao, tipo)
        except ErroDoProvedor as erro:
            print(f"  {self.principal.nome} falhou em {descricao} ({erro.__class__.__name__}); "
                  f"usando o reserva ({self.reserva.nome}).", flush=True)
            return self.reserva.gerar_json(partes, esquema, max_tokens, descricao, tipo)


def provedor_de_visao(nome: str | None = None) -> Provedor:
    principal = criar_provedor(nome or os.environ.get("VISION_PROVIDER") or "gemini")
    reserva = os.environ.get("VISION_FALLBACK_PROVIDER", "").strip()
    if reserva and reserva != principal.nome:
        return ProvedorComReserva(principal, criar_provedor(reserva))
    return principal


def validacao_ligada() -> bool:
    return os.environ.get("VALIDATION_ENABLED", "").strip().lower() in ("1", "true", "sim", "on", "yes")


def provedor_validador(nome: str | None = None, forcar: bool = False) -> Provedor | None:
    """O validador, ou None se a validação estiver desligada."""
    if not (forcar or validacao_ligada()):
        return None
    return criar_provedor(nome or os.environ.get("VALIDATOR_PROVIDER") or "claude")


def como_provedor(cliente) -> Provedor:
    """Aceita um Provedor ou um cliente no formato do SDK do Gemini (qualquer
    objeto com `.models.generate_content`) — é o que os testes antigos e quem
    ainda chama com um `genai.Client` passam."""
    if isinstance(cliente, Provedor):
        return cliente
    if hasattr(cliente, "models"):
        from core.providers.gemini import ProvedorGemini
        return ProvedorGemini(cliente=cliente)
    raise TypeError(f"não sei usar {type(cliente).__name__} como provedor de modelo")
