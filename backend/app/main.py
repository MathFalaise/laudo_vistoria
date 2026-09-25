"""
Aplicação FastAPI.

    NAVEGADOR -> FRONTEND -> ESTA API -> core/ (motor) -> GEMINI

O navegador nunca fala com o Gemini: a chave é lida por este processo, a
partir do ambiente, e não existe rota que a devolva.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api import roteador
from app.config import (DIRETORIO_FRONTEND, ADMIN_EMAIL, ADMIN_SENHA,
                        ORIGENS_PERMITIDAS, preparar_diretorios)
from app.db import SessaoBanco, criar_esquema
from app.jobs import iniciar_trabalhador, parar_trabalhador, recuperar_jobs_orfaos
from app.models import Usuario
from app.security import gerar_hash_senha
from app.servicos import semear_regras

logging.basicConfig(
    level=os.environ.get("LAUDO_LOG", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("laudo")


def _criar_admin_inicial() -> None:
    """Cria o primeiro usuário, se não houver nenhum e o ambiente disser qual.

    Sem senha no ambiente, NÃO se cria usuário com senha padrão: uma aplicação
    que sobe na internet com admin/admin é pior do que uma que não sobe."""
    if not ADMIN_EMAIL or not ADMIN_SENHA:
        return
    with SessaoBanco() as sessao:
        if sessao.scalar(select(Usuario).limit(1)) is not None:
            return
        if len(ADMIN_SENHA) < 10:
            logger.error(
                "LAUDO_ADMIN_SENHA tem menos de 10 caracteres — usuário inicial "
                "NÃO criado. Escolha uma senha maior e suba de novo."
            )
            return
        sessao.add(Usuario(
            email=ADMIN_EMAIL.strip().lower(),
            nome="Vistoriador",
            senha_hash=gerar_hash_senha(ADMIN_SENHA),
        ))
        sessao.commit()
        logger.info("usuário inicial criado: %s", ADMIN_EMAIL)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    preparar_diretorios()
    criar_esquema()
    _criar_admin_inicial()
    with SessaoBanco() as sessao:
        criadas = semear_regras(sessao)
        if criadas:
            logger.info("%d regra(s) importada(s) do regras_validadas.txt", criadas)
    orfaos = recuperar_jobs_orfaos()
    if orfaos:
        logger.warning("%d job(s) interrompido(s) por reinício foram marcados", orfaos)
    iniciar_trabalhador()
    try:
        yield
    finally:
        parar_trabalhador()


app = FastAPI(
    title="Laudo de Vistoria",
    version="2.0.0",
    lifespan=ciclo_de_vida,
    # /docs fica desligado por padrão: a API é de uso interno e o esquema
    # entrega a superfície inteira para quem achar a URL.
    docs_url="/docs" if os.environ.get("LAUDO_DOCS") == "1" else None,
    redoc_url=None,
)

if ORIGENS_PERMITIDAS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ORIGENS_PERMITIDAS,
        allow_credentials=True,     # o cookie de sessão precisa disto
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(roteador)


@app.get("/api/saude")
def saude():
    """Sonda para o Docker. Não diz nada sobre dados nem sobre a chave."""
    from core.config import MODEL_NAME
    return {"ok": True, "modelo": MODEL_NAME,
            "gemini_configurado": bool(os.environ.get("GEMINI_API_KEY"))}


# O build do frontend, servido pela própria API em produção — um contêiner só
# (regra 25: nada de arquitetura de dezenas de serviços).
if DIRETORIO_FRONTEND.is_dir():
    app.mount("/assets", StaticFiles(directory=DIRETORIO_FRONTEND / "assets"),
              name="assets")

    @app.get("/{caminho:path}")
    def servir_frontend(caminho: str):
        """SPA: qualquer rota que não seja /api cai no index.html, para o
        roteamento do React funcionar em recarga de página."""
        if caminho.startswith("api/"):
            return JSONResponse({"detail": "Rota não encontrada."}, status_code=404)
        arquivo = DIRETORIO_FRONTEND / caminho
        if caminho and arquivo.is_file() and arquivo.resolve().is_relative_to(
            DIRETORIO_FRONTEND.resolve()
        ):
            return FileResponse(arquivo)
        return FileResponse(DIRETORIO_FRONTEND / "index.html")
