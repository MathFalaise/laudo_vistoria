"""
Senha, sessão e a dependência que protege as rotas.

Hashing com `hashlib.scrypt`, da biblioteca padrão. Escolha deliberada: uma
dependência a menos para instalar (bcrypt precisa de roda compilada, e este
projeto tem que subir numa máquina qualquer), e scrypt é um KDF sério, com
custo de memória — não é um SHA cru com sal.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import (COOKIE_SEGURO, DURACAO_SESSAO_HORAS, NOME_COOKIE_SESSAO)
from app.db import obter_sessao
from app.models import Sessao, Usuario, agora

# Parâmetros do scrypt. n=2**15, r=8, p=1 usa 32 MB e leva ~100 ms nesta
# máquina: caro o bastante para força bruta, barato o bastante para um login.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_TAMANHO_SAL = 16
_TAMANHO_CHAVE = 32

# O OpenSSL recusa scrypt acima de 32 MB por padrão, e 128 * n * r dá
# exatamente 32 MB aqui — sem este limite explícito o hash falha com
# "memory limit exceeded". Precisa ser passado também na CONFERÊNCIA, senão
# a verificação quebra em senhas que o próprio sistema gerou.
_SCRYPT_MAXMEM = 96 * 1024 * 1024


def gerar_hash_senha(senha: str) -> str:
    sal = os.urandom(_TAMANHO_SAL)
    chave = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=_SCRYPT_N,
                           r=_SCRYPT_R, p=_SCRYPT_P, dklen=_TAMANHO_CHAVE,
                           maxmem=_SCRYPT_MAXMEM)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${sal.hex()}${chave.hex()}"


def conferir_senha(senha: str, armazenado: str) -> bool:
    """Comparação em tempo constante. Formato desconhecido devolve False em
    vez de estourar — senha malformada no banco não pode virar 500 nem, pior,
    virar autenticação."""
    try:
        algoritmo, n, r, p, sal_hex, chave_hex = armazenado.split("$")
        if algoritmo != "scrypt":
            return False
        chave = hashlib.scrypt(
            senha.encode("utf-8"), salt=bytes.fromhex(sal_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(chave_hex)),
            maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(chave, bytes.fromhex(chave_hex))


def _hash_token(token: str) -> str:
    """O banco guarda o hash, não o token: vazar o banco não entrega sessões."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def criar_sessao(sessao_db: Session, usuario: Usuario, resposta: Response) -> str:
    token = secrets.token_urlsafe(32)
    registro = Sessao(
        usuario_id=usuario.id,
        token_hash=_hash_token(token),
        expira_em=datetime.now(timezone.utc) + timedelta(hours=DURACAO_SESSAO_HORAS),
    )
    sessao_db.add(registro)
    sessao_db.commit()

    resposta.set_cookie(
        NOME_COOKIE_SESSAO,
        token,
        max_age=DURACAO_SESSAO_HORAS * 3600,
        httponly=True,       # JavaScript não lê: XSS não rouba a sessão
        samesite="lax",      # barra CSRF em navegação de terceiros
        secure=COOKIE_SEGURO,
        path="/",
    )
    return token


def encerrar_sessao(sessao_db: Session, token: str | None, resposta: Response) -> None:
    if token:
        registro = sessao_db.scalar(
            select(Sessao).where(Sessao.token_hash == _hash_token(token))
        )
        if registro:
            sessao_db.delete(registro)
            sessao_db.commit()
    resposta.delete_cookie(NOME_COOKIE_SESSAO, path="/")


def usuario_atual(
    laudo_sessao: str | None = Cookie(default=None, alias=NOME_COOKIE_SESSAO),
    sessao_db: Session = Depends(obter_sessao),
) -> Usuario:
    """Dependência que protege as rotas. Toda rota de dados usa esta — não
    existe rota de vistoria aberta (regra 27)."""
    nao_autenticado = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessão inválida ou expirada.",
    )
    if not laudo_sessao:
        raise nao_autenticado

    registro = sessao_db.scalar(
        select(Sessao).where(Sessao.token_hash == _hash_token(laudo_sessao))
    )
    if registro is None:
        raise nao_autenticado

    expira = registro.expira_em
    if expira.tzinfo is None:                       # SQLite devolve naive
        expira = expira.replace(tzinfo=timezone.utc)
    if expira < datetime.now(timezone.utc):
        sessao_db.delete(registro)
        sessao_db.commit()
        raise nao_autenticado

    usuario = sessao_db.get(Usuario, registro.usuario_id)
    if usuario is None or not usuario.ativo:
        raise nao_autenticado

    registro.ultimo_uso = agora()
    sessao_db.commit()
    return usuario


def limpar_sessoes_expiradas(sessao_db: Session) -> int:
    agora_utc = datetime.now(timezone.utc)
    expiradas = sessao_db.scalars(select(Sessao)).all()
    removidas = 0
    for registro in expiradas:
        expira = registro.expira_em
        if expira.tzinfo is None:
            expira = expira.replace(tzinfo=timezone.utc)
        if expira < agora_utc:
            sessao_db.delete(registro)
            removidas += 1
    if removidas:
        sessao_db.commit()
    return removidas
