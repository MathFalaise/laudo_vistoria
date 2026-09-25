"""
Processamento assíncrono (regra 26).

A requisição HTTP cria um Job e devolve na hora. Uma thread de trabalho pega
os jobs pendentes e processa cômodo a cômodo, gravando o estado a cada um.

Por que uma thread e não Celery/RQ: a regra 25 pede para não transformar isto
numa arquitetura de dezenas de serviços, e o trabalho é I/O puro — o processo
passa o tempo esperando o Gemini responder. Um broker traria Redis, um
supervisor e uma segunda imagem para resolver um problema que não existe aqui.

O que se paga por essa escolha: um job em andamento morre se o processo morre.
É por isso que o estado é gravado POR CÔMODO e não no fim — na volta, os
cômodos concluídos continuam concluídos e não são refeitos.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessaoBanco
from app.models import Comodo, EstadoComodo, EstadoJob, Job, agora
from app.servicos import aplicar_regras_no_motor, processar_comodo_persistindo

logger = logging.getLogger("laudo.jobs")

# Intervalo de sondagem da fila. Alto o bastante para não acordar o processo à
# toa, baixo o bastante para o botão "Processar" parecer imediato.
INTERVALO_SONDAGEM = 1.0

_parar = threading.Event()
_thread: threading.Thread | None = None


def recuperar_jobs_orfaos() -> int:
    """Marca como FALHOU os jobs que ficaram PROCESSANDO quando o processo
    caiu — senão eles ficam eternamente "em andamento" na tela.

    Os CÔMODOS não são tocados: os que estavam CONCLUIDO seguem concluídos.
    Só o que estava no meio (PROCESSANDO) volta para PENDENTE, porque um
    cômodo interrompido não tem laudo gravado."""
    with SessaoBanco() as sessao:
        jobs = sessao.scalars(
            select(Job).where(Job.estado.in_([EstadoJob.PROCESSANDO, EstadoJob.PENDENTE]))
        ).all()
        for job in jobs:
            job.estado = EstadoJob.FALHOU
            job.erro = ("O servidor foi reiniciado durante o processamento. "
                        "Os cômodos que já haviam terminado foram preservados — "
                        "rode de novo para continuar de onde parou.")
            job.terminado_em = agora()

        interrompidos = sessao.scalars(
            select(Comodo).where(Comodo.estado == EstadoComodo.PROCESSANDO)
        ).all()
        for comodo in interrompidos:
            comodo.estado = EstadoComodo.PENDENTE
            comodo.erro = "interrompido pelo reinício do servidor"

        if jobs or interrompidos:
            sessao.commit()
        return len(jobs)


def criar_job(sessao, vistoria_id: str, tipo: str, nomes_comodo: list,
              usar_evidencias: bool = True) -> Job:
    job = Job(
        vistoria_id=vistoria_id,
        tipo=tipo,
        estado=EstadoJob.PENDENTE,
        total=len(nomes_comodo),
        comodos=",".join(nomes_comodo),
        usar_evidencias=usar_evidencias,
        mensagem="na fila",
    )
    sessao.add(job)
    sessao.commit()
    return job


def _proximo_job(sessao) -> Job | None:
    return sessao.scalar(
        select(Job).where(Job.estado == EstadoJob.PENDENTE).order_by(Job.criado_em).limit(1)
    )


def _executar_job(sessao, job: Job) -> None:
    from core.gemini_client import criar_cliente

    job.estado = EstadoJob.PROCESSANDO
    job.iniciado_em = agora()
    job.mensagem = "preparando"
    sessao.commit()

    # As regras do banco entram no motor AGORA, não na subida do servidor:
    # adotar uma regra tem que valer já no próximo processamento.
    aplicar_regras_no_motor(sessao)

    try:
        cliente = criar_cliente()
    except Exception as erro:
        job.estado = EstadoJob.FALHOU
        job.erro = str(erro)
        job.terminado_em = agora()
        sessao.commit()
        return

    nomes = [nome for nome in job.comodos.split(",") if nome]
    falhas = []

    for nome in nomes:
        sessao.refresh(job)
        if job.cancelamento_pedido:
            job.estado = EstadoJob.CANCELADO
            job.mensagem = f"cancelado depois de {job.concluidos} cômodo(s)"
            job.terminado_em = agora()
            sessao.commit()
            return

        comodo = sessao.scalar(
            select(Comodo).where(Comodo.vistoria_id == job.vistoria_id, Comodo.nome == nome)
        )
        if comodo is None:
            falhas.append(f"{nome} (não encontrado)")
            continue
        if not comodo.fotos:
            falhas.append(f"{nome} (sem fotos)")
            job.concluidos += 1
            sessao.commit()
            continue

        job.mensagem = f"processando {nome}"
        sessao.commit()

        def progresso(texto, _nome=nome):
            job.mensagem = f"{_nome}: {texto}"
            sessao.commit()

        try:
            processar_comodo_persistindo(
                sessao, comodo, cliente,
                usar_evidencias=job.usar_evidencias, progresso=progresso,
            )
        except Exception as erro:
            # Isolamento por cômodo, igual ao CLI: um cômodo problemático não
            # derruba o laudo dos outros.
            logger.warning("cômodo %s falhou: %s", nome, erro.__class__.__name__)
            falhas.append(f"{nome} ({erro.__class__.__name__})")
        job.concluidos += 1
        sessao.commit()

    job.estado = EstadoJob.CONCLUIDO
    job.terminado_em = agora()
    job.mensagem = f"{job.concluidos} de {job.total} cômodo(s) processado(s)"
    if falhas:
        job.erro = "Cômodos com problema: " + "; ".join(falhas)
    sessao.commit()


def _laco():
    while not _parar.is_set():
        try:
            with SessaoBanco() as sessao:
                job = _proximo_job(sessao)
                if job is None:
                    _parar.wait(INTERVALO_SONDAGEM)
                    continue
                _executar_job(sessao, job)
        except Exception:
            # Uma falha inesperada não pode matar a thread: sem ela, a fila
            # para de andar e a aplicação vira um formulário sem motor.
            logger.exception("falha inesperada no laço de jobs")
            _parar.wait(INTERVALO_SONDAGEM * 5)


def iniciar_trabalhador() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _parar.clear()
    _thread = threading.Thread(target=_laco, name="laudo-jobs", daemon=True)
    _thread.start()
    logger.info("trabalhador de jobs iniciado")


def parar_trabalhador(espera: float = 5.0) -> None:
    _parar.set()
    if _thread is not None:
        _thread.join(timeout=espera)


def executar_pendentes_sincronamente(limite: int = 10) -> int:
    """Roda a fila na thread atual. Existe para os testes: com o trabalhador
    em background, o teste viraria uma espera com sleep."""
    processados = 0
    with SessaoBanco() as sessao:
        while processados < limite:
            job = _proximo_job(sessao)
            if job is None:
                break
            _executar_job(sessao, job)
            processados += 1
    return processados
