"""
Rotas HTTP.

Duas regras valem em todas elas:

1. toda rota de dados depende de `usuario_atual`. Não existe rota de vistoria
   aberta — as fotos são do imóvel de um cliente (regra 27);
2. nada de IA entra no laudo sozinho. As rotas que decidem alguma coisa sobre
   o texto exigem uma decisão humana explícita no corpo da requisição.

A chave do Gemini não aparece em nenhuma resposta, em nenhum formato — não há
endpoint que a devolva, nem campo que a inclua.
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timezone

from fastapi import (APIRouter, Cookie, Depends, File, Form, HTTPException,
                     Response, UploadFile, status)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import jobs as jobs_mod
from app import servicos
from app.config import DIRETORIO_FOTOS, TAMANHO_MAX_ZIP
from app.db import obter_sessao
from app.models import (Comodo, EstadoComodo, Evidencia, Foto, ItemLaudo, Job,
                        Pendencia, Regra, Usuario, Vistoria, novo_id)
from app.config import NOME_COOKIE_SESSAO
from app.security import (conferir_senha, criar_sessao, encerrar_sessao,
                          usuario_atual)
from app.storage import (ArquivoRejeitado, ler_zip_de_vistoria, miniatura,
                         remover_foto, salvar_foto)
from core.config import CATEGORIAS, ROTULOS_CATEGORIA

logger = logging.getLogger("laudo.api")

roteador = APIRouter(prefix="/api")


def _erro(mensagem: str, codigo: int = status.HTTP_400_BAD_REQUEST):
    return HTTPException(status_code=codigo, detail=mensagem)


def _achar(sessao: Session, modelo, identificador: str):
    objeto = sessao.get(modelo, identificador)
    if objeto is None:
        raise _erro(f"{modelo.__name__} não encontrado.", status.HTTP_404_NOT_FOUND)
    return objeto


# ==========================================================================
# Autenticação
# ==========================================================================

class EntradaLogin(BaseModel):
    email: str
    senha: str


@roteador.post("/auth/login")
def login(dados: EntradaLogin, resposta: Response,
          sessao: Session = Depends(obter_sessao)):
    usuario = sessao.scalar(select(Usuario).where(Usuario.email == dados.email.strip().lower()))
    # Mensagem única para e-mail inexistente e senha errada: dizer qual dos
    # dois falhou entrega quais e-mails existem.
    if usuario is None or not usuario.ativo or not conferir_senha(dados.senha, usuario.senha_hash):
        raise _erro("E-mail ou senha incorretos.", status.HTTP_401_UNAUTHORIZED)
    criar_sessao(sessao, usuario, resposta)
    return {"id": usuario.id, "email": usuario.email, "nome": usuario.nome}


@roteador.post("/auth/logout")
def logout(resposta: Response,
           laudo_sessao: str | None = Cookie(default=None, alias=NOME_COOKIE_SESSAO),
           sessao: Session = Depends(obter_sessao),
           usuario: Usuario = Depends(usuario_atual)):
    """Apaga a sessão do BANCO, não só o cookie.

    Limpar o cookie sozinho deixaria o token valendo no servidor: quem tivesse
    copiado o cookie continuaria dentro depois de o usuário "sair"."""
    encerrar_sessao(sessao, laudo_sessao, resposta)
    return {"ok": True}


@roteador.get("/auth/eu")
def eu(usuario: Usuario = Depends(usuario_atual)):
    return {"id": usuario.id, "email": usuario.email, "nome": usuario.nome}


# ==========================================================================
# Vistorias
# ==========================================================================

class EntradaVistoria(BaseModel):
    titulo: str = Field(min_length=1, max_length=300)
    endereco: str = ""
    notas: str = ""
    data_vistoria: str = ""


def _resumo_vistoria(sessao: Session, vistoria: Vistoria) -> dict:
    total_fotos = sessao.scalar(
        select(func.count(Foto.id)).join(Comodo).where(Comodo.vistoria_id == vistoria.id)
    ) or 0
    return {
        "id": vistoria.id,
        "titulo": vistoria.titulo,
        "endereco": vistoria.endereco,
        "notas": vistoria.notas,
        "data_vistoria": vistoria.data_vistoria,
        "arquivada": vistoria.arquivada,
        "criado_em": vistoria.criado_em.isoformat(),
        "comodos": len(vistoria.comodos),
        "fotos": total_fotos,
        "pendencias": servicos.resumo_pendencias(sessao, vistoria.id),
    }


@roteador.get("/vistorias")
def listar_vistorias(sessao: Session = Depends(obter_sessao),
                     usuario: Usuario = Depends(usuario_atual)):
    vistorias = sessao.scalars(
        select(Vistoria).order_by(Vistoria.criado_em.desc())
    ).all()
    return [_resumo_vistoria(sessao, vistoria) for vistoria in vistorias]


@roteador.post("/vistorias", status_code=status.HTTP_201_CREATED)
def criar_vistoria(dados: EntradaVistoria, sessao: Session = Depends(obter_sessao),
                   usuario: Usuario = Depends(usuario_atual)):
    vistoria = Vistoria(**dados.model_dump())
    sessao.add(vistoria)
    sessao.commit()
    return _resumo_vistoria(sessao, vistoria)


@roteador.get("/vistorias/{vistoria_id}")
def obter_vistoria(vistoria_id: str, sessao: Session = Depends(obter_sessao),
                   usuario: Usuario = Depends(usuario_atual)):
    vistoria = _achar(sessao, Vistoria, vistoria_id)
    detalhe = _resumo_vistoria(sessao, vistoria)
    detalhe["lista_comodos"] = [
        {
            "id": comodo.id,
            "nome": comodo.nome,
            "ordem": comodo.ordem,
            "estado": comodo.estado,
            "erro": comodo.erro,
            "fotos": len(comodo.fotos),
            "fotos_utilizaveis": comodo.fotos_utilizaveis,
            "cobertura_incompleta": comodo.cobertura_incompleta,
            "itens": sum(1 for item in comodo.itens if not item.removido),
            "pendencias_abertas": sum(
                1 for pendencia in sessao.scalars(
                    select(Pendencia).where(Pendencia.comodo_id == comodo.id,
                                            Pendencia.decisao == "")
                ).all()
            ),
        }
        for comodo in sorted(vistoria.comodos, key=lambda c: (c.ordem, c.nome))
    ]
    return detalhe


@roteador.patch("/vistorias/{vistoria_id}")
def editar_vistoria(vistoria_id: str, dados: EntradaVistoria,
                    sessao: Session = Depends(obter_sessao),
                    usuario: Usuario = Depends(usuario_atual)):
    vistoria = _achar(sessao, Vistoria, vistoria_id)
    for campo, valor in dados.model_dump().items():
        setattr(vistoria, campo, valor)
    sessao.commit()
    return _resumo_vistoria(sessao, vistoria)


@roteador.delete("/vistorias/{vistoria_id}")
def apagar_vistoria(vistoria_id: str, sessao: Session = Depends(obter_sessao),
                    usuario: Usuario = Depends(usuario_atual)):
    vistoria = _achar(sessao, Vistoria, vistoria_id)
    for comodo in vistoria.comodos:
        for foto in comodo.fotos:
            remover_foto(foto.caminho)
    sessao.delete(vistoria)
    sessao.commit()
    return {"ok": True}


# ==========================================================================
# Cômodos
# ==========================================================================

class EntradaComodo(BaseModel):
    nome: str = Field(min_length=1, max_length=200)


def _criar_comodo(sessao: Session, vistoria: Vistoria, nome: str) -> Comodo:
    nome = " ".join(nome.split())
    if not nome:
        raise _erro("O nome do cômodo não pode ficar em branco.")
    existente = sessao.scalar(
        select(Comodo).where(Comodo.vistoria_id == vistoria.id, Comodo.nome == nome)
    )
    if existente:
        return existente
    ordem = max((c.ordem for c in vistoria.comodos), default=-1) + 1
    comodo = Comodo(vistoria_id=vistoria.id, nome=nome, ordem=ordem)
    sessao.add(comodo)
    sessao.commit()
    return comodo


@roteador.post("/vistorias/{vistoria_id}/comodos", status_code=status.HTTP_201_CREATED)
def criar_comodo(vistoria_id: str, dados: EntradaComodo,
                 sessao: Session = Depends(obter_sessao),
                 usuario: Usuario = Depends(usuario_atual)):
    vistoria = _achar(sessao, Vistoria, vistoria_id)
    comodo = _criar_comodo(sessao, vistoria, dados.nome)
    return {"id": comodo.id, "nome": comodo.nome, "estado": comodo.estado}


@roteador.delete("/comodos/{comodo_id}")
def apagar_comodo(comodo_id: str, sessao: Session = Depends(obter_sessao),
                  usuario: Usuario = Depends(usuario_atual)):
    comodo = _achar(sessao, Comodo, comodo_id)
    for foto in comodo.fotos:
        remover_foto(foto.caminho)
    sessao.delete(comodo)
    sessao.commit()
    return {"ok": True}


# ==========================================================================
# Fotos
# ==========================================================================

def _foto_para_dict(foto: Foto) -> dict:
    return {
        "id": foto.id,
        "nome_original": foto.nome_original,
        "mime": foto.mime,
        "largura": foto.largura,
        "altura": foto.altura,
        "bytes": foto.bytes_tamanho,
        "ordem": foto.ordem,
        "escopo": foto.escopo,
        "relevancia": foto.relevancia,
        "ambiente_adjacente": foto.ambiente_adjacente,
        "reflexo": foto.reflexo,
        "motivo_escopo": foto.motivo_escopo,
    }


@roteador.get("/comodos/{comodo_id}/fotos")
def listar_fotos(comodo_id: str, sessao: Session = Depends(obter_sessao),
                 usuario: Usuario = Depends(usuario_atual)):
    comodo = _achar(sessao, Comodo, comodo_id)
    return [_foto_para_dict(foto) for foto in comodo.fotos]


@roteador.post("/comodos/{comodo_id}/fotos", status_code=status.HTTP_201_CREATED)
async def enviar_fotos(comodo_id: str, arquivos: list[UploadFile] = File(...),
                       sessao: Session = Depends(obter_sessao),
                       usuario: Usuario = Depends(usuario_atual)):
    """Upload de várias fotos. Um arquivo recusado não invalida os outros: a
    resposta traz o que entrou e o que foi recusado, com o motivo."""
    comodo = _achar(sessao, Comodo, comodo_id)
    aceitas, recusadas = [], []
    ordem = max((foto.ordem for foto in comodo.fotos), default=-1) + 1

    for arquivo in arquivos:
        conteudo = await arquivo.read()
        foto_id = novo_id()
        try:
            metadados = salvar_foto(comodo.id, foto_id, conteudo, arquivo.filename or "")
        except ArquivoRejeitado as erro:
            recusadas.append({"nome": arquivo.filename, "motivo": str(erro)})
            continue
        foto = Foto(id=foto_id, comodo_id=comodo.id,
                    nome_original=(arquivo.filename or "foto")[:300],
                    ordem=ordem, **metadados)
        sessao.add(foto)
        ordem += 1
        aceitas.append(foto)

    if aceitas:
        # Foto nova torna o laudo do cômodo desatualizado.
        if comodo.estado == EstadoComodo.CONCLUIDO:
            comodo.estado = EstadoComodo.PENDENTE
        sessao.commit()

    return {"aceitas": [_foto_para_dict(foto) for foto in aceitas],
            "recusadas": recusadas}


@roteador.delete("/fotos/{foto_id}")
def apagar_foto(foto_id: str, sessao: Session = Depends(obter_sessao),
                usuario: Usuario = Depends(usuario_atual)):
    """Remoção pedida pelo USUÁRIO. Escopo nunca apaga foto (regra 7)."""
    foto = _achar(sessao, Foto, foto_id)
    remover_foto(foto.caminho)
    sessao.delete(foto)
    sessao.commit()
    return {"ok": True}


@roteador.get("/fotos/{foto_id}/arquivo")
def baixar_foto(foto_id: str, sessao: Session = Depends(obter_sessao),
                usuario: Usuario = Depends(usuario_atual)):
    foto = _achar(sessao, Foto, foto_id)
    from app.storage import caminho_absoluto
    caminho = caminho_absoluto(foto.caminho)
    if not caminho.is_file():
        raise _erro("Arquivo não encontrado no armazenamento.", status.HTTP_404_NOT_FOUND)
    return StreamingResponse(io.BytesIO(caminho.read_bytes()), media_type=foto.mime)


@roteador.get("/fotos/{foto_id}/miniatura")
def baixar_miniatura(foto_id: str, lado: int = 480,
                     sessao: Session = Depends(obter_sessao),
                     usuario: Usuario = Depends(usuario_atual)):
    foto = _achar(sessao, Foto, foto_id)
    try:
        dados = miniatura(foto.caminho, max(64, min(lado, 1600)))
    except Exception:
        raise _erro("Não foi possível gerar a miniatura.", status.HTTP_404_NOT_FOUND)
    return Response(content=dados, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


@roteador.post("/vistorias/{vistoria_id}/zip", status_code=status.HTTP_201_CREATED)
async def enviar_zip(vistoria_id: str, arquivo: UploadFile = File(...),
                     sessao: Session = Depends(obter_sessao),
                     usuario: Usuario = Depends(usuario_atual)):
    """ZIP com uma pasta por cômodo — o mesmo formato que o CLI sempre usou."""
    vistoria = _achar(sessao, Vistoria, vistoria_id)
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX_ZIP:
        raise _erro(f"ZIP maior que o limite de {TAMANHO_MAX_ZIP // (1024 * 1024)} MB.")
    try:
        por_comodo = ler_zip_de_vistoria(conteudo)
    except ArquivoRejeitado as erro:
        raise _erro(str(erro))

    resumo, recusadas = [], []
    for nome_comodo, fotos in por_comodo.items():
        comodo = _criar_comodo(sessao, vistoria, nome_comodo)
        ordem = max((foto.ordem for foto in comodo.fotos), default=-1) + 1
        aceitas = 0
        for nome_arquivo, dados in fotos:
            foto_id = novo_id()
            try:
                metadados = salvar_foto(comodo.id, foto_id, dados, nome_arquivo)
            except ArquivoRejeitado as erro:
                recusadas.append({"nome": f"{nome_comodo}/{nome_arquivo}",
                                  "motivo": str(erro)})
                continue
            sessao.add(Foto(id=foto_id, comodo_id=comodo.id,
                            nome_original=nome_arquivo[:300], ordem=ordem, **metadados))
            ordem += 1
            aceitas += 1
        if comodo.estado == EstadoComodo.CONCLUIDO and aceitas:
            comodo.estado = EstadoComodo.PENDENTE
        resumo.append({"comodo": nome_comodo, "fotos": aceitas})
    sessao.commit()
    return {"comodos": resumo, "recusadas": recusadas}


# ==========================================================================
# Processamento
# ==========================================================================

class EntradaProcessar(BaseModel):
    comodos: list[str] | None = None
    usar_evidencias: bool = True
    reprocessar_concluidos: bool = False


@roteador.post("/vistorias/{vistoria_id}/processar", status_code=status.HTTP_202_ACCEPTED)
def processar(vistoria_id: str, dados: EntradaProcessar,
              sessao: Session = Depends(obter_sessao),
              usuario: Usuario = Depends(usuario_atual)):
    vistoria = _achar(sessao, Vistoria, vistoria_id)
    todos = sorted(vistoria.comodos, key=lambda c: (c.ordem, c.nome))
    alvo = [c for c in todos if not dados.comodos or c.nome in dados.comodos]
    if not dados.reprocessar_concluidos:
        # Regra 26: não repetir processamento já terminado sem necessidade.
        alvo = [c for c in alvo if c.estado != EstadoComodo.CONCLUIDO]
    alvo = [c for c in alvo if c.fotos]
    if not alvo:
        raise _erro("Nenhum cômodo com fotos para processar. "
                    "Marque 'reprocessar' se quiser refazer os já concluídos.")

    job = jobs_mod.criar_job(sessao, vistoria.id, "laudo",
                             [c.nome for c in alvo], dados.usar_evidencias)
    return _job_para_dict(job)


def _job_para_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "vistoria_id": job.vistoria_id,
        "tipo": job.tipo,
        "estado": job.estado,
        "total": job.total,
        "concluidos": job.concluidos,
        "mensagem": job.mensagem,
        "erro": job.erro,
        "usar_evidencias": job.usar_evidencias,
        "criado_em": job.criado_em.isoformat(),
    }


@roteador.get("/jobs/{job_id}")
def obter_job(job_id: str, sessao: Session = Depends(obter_sessao),
              usuario: Usuario = Depends(usuario_atual)):
    return _job_para_dict(_achar(sessao, Job, job_id))


@roteador.post("/jobs/{job_id}/cancelar")
def cancelar_job(job_id: str, sessao: Session = Depends(obter_sessao),
                 usuario: Usuario = Depends(usuario_atual)):
    job = _achar(sessao, Job, job_id)
    job.cancelamento_pedido = True
    sessao.commit()
    return _job_para_dict(job)


@roteador.get("/vistorias/{vistoria_id}/jobs")
def listar_jobs(vistoria_id: str, sessao: Session = Depends(obter_sessao),
                usuario: Usuario = Depends(usuario_atual)):
    _achar(sessao, Vistoria, vistoria_id)
    jobs = sessao.scalars(
        select(Job).where(Job.vistoria_id == vistoria_id)
        .order_by(Job.criado_em.desc()).limit(20)
    ).all()
    return [_job_para_dict(job) for job in jobs]


# ==========================================================================
# Laudo
# ==========================================================================

@roteador.get("/vistorias/{vistoria_id}/laudo")
def obter_laudo(vistoria_id: str, sessao: Session = Depends(obter_sessao),
                usuario: Usuario = Depends(usuario_atual)):
    vistoria = _achar(sessao, Vistoria, vistoria_id)
    comodos = []
    for comodo in sorted(vistoria.comodos, key=lambda c: (c.ordem, c.nome)):
        categorias = []
        for categoria in CATEGORIAS:
            itens = [
                {"id": item.id, "texto": item.texto, "certeza": item.certeza,
                 "motivo": item.motivo,
                 "evidencias": [e.id for e in item.evidencias]}
                for item in comodo.itens
                if item.categoria == categoria and not item.removido
            ]
            if itens:
                categorias.append({"categoria": categoria,
                                   "rotulo": ROTULOS_CATEGORIA[categoria],
                                   "itens": itens})
        comodos.append({
            "id": comodo.id, "nome": comodo.nome, "estado": comodo.estado,
            "cobertura_incompleta": comodo.cobertura_incompleta,
            "categorias": categorias,
        })
    return {"vistoria": vistoria.titulo, "comodos": comodos,
            "texto": servicos.texto_do_laudo(vistoria)}


class EntradaItem(BaseModel):
    texto: str = Field(min_length=1)


@roteador.patch("/itens/{item_id}")
def editar_item(item_id: str, dados: EntradaItem,
                sessao: Session = Depends(obter_sessao),
                usuario: Usuario = Depends(usuario_atual)):
    """Edição manual direta, com histórico (regra 41)."""
    from core.report_writer import normalizar_linha
    from app.models import HistoricoItem

    item = _achar(sessao, ItemLaudo, item_id)
    anterior = item.texto
    item.texto = normalizar_linha(dados.texto)
    sessao.add(HistoricoItem(item_id=item.id, texto_anterior=anterior,
                             texto_novo=item.texto, origem="humano",
                             usuario_id=usuario.id,
                             evidencia_ids=",".join(e.id for e in item.evidencias)))
    sessao.commit()
    return {"id": item.id, "texto": item.texto}


@roteador.get("/itens/{item_id}/historico")
def historico_item(item_id: str, sessao: Session = Depends(obter_sessao),
                   usuario: Usuario = Depends(usuario_atual)):
    item = _achar(sessao, ItemLaudo, item_id)
    return [
        {"quando": registro.criado_em.isoformat(), "origem": registro.origem,
         "texto_anterior": registro.texto_anterior, "texto_novo": registro.texto_novo,
         "pendencia_id": registro.pendencia_id,
         "evidencias": [e for e in registro.evidencia_ids.split(",") if e]}
        for registro in item.historico
    ]


# ==========================================================================
# Evidências e auditoria
# ==========================================================================

def _evidencia_para_dict(evidencia: Evidencia) -> dict:
    return {
        "id": evidencia.id,
        "foto_id": evidencia.foto_id,
        "item_id": evidencia.item_id,
        "categoria": evidencia.categoria,
        "rotulo": ROTULOS_CATEGORIA.get(evidencia.categoria, evidencia.categoria),
        "observacao": evidencia.observacao,
        "confianca_percepcao": evidencia.confianca_percepcao,
        "confianca_escopo": evidencia.confianca_escopo,
        "confianca_final": evidencia.confianca_final,
        "reflexo": evidencia.e_reflexo,
        "ambiente_adjacente": evidencia.e_ambiente_adjacente,
        "status": evidencia.status,
        "motivo_descarte": evidencia.motivo_descarte,
        "detalhe_descarte": evidencia.detalhe_descarte,
        "regiao": evidencia.regiao,
    }


@roteador.get("/comodos/{comodo_id}/evidencias")
def listar_evidencias(comodo_id: str, sessao: Session = Depends(obter_sessao),
                      usuario: Usuario = Depends(usuario_atual)):
    """Inclui as DESCARTADAS, com o motivo. É o ponto da regra 7: a foto e a
    evidência continuam disponíveis para auditoria mesmo sem virar texto."""
    comodo = _achar(sessao, Comodo, comodo_id)
    return [_evidencia_para_dict(evidencia) for evidencia in comodo.evidencias]


# ==========================================================================
# Pendências
# ==========================================================================

def _pendencia_para_dict(sessao: Session, pendencia: Pendencia) -> dict:
    comodo = sessao.get(Comodo, pendencia.comodo_id)
    item = sessao.get(ItemLaudo, pendencia.item_id) if pendencia.item_id else None
    evidencias = []
    if pendencia.evidencias_relacionadas:
        evidencias = sessao.scalars(
            select(Evidencia).where(Evidencia.id.in_(pendencia.evidencias_relacionadas))
        ).all()
    elif item is not None:
        evidencias = item.evidencias
    return {
        "id": pendencia.id,
        "comodo_id": pendencia.comodo_id,
        "comodo": comodo.nome if comodo else "",
        "categoria": pendencia.categoria,
        "rotulo": ROTULOS_CATEGORIA.get(pendencia.categoria, pendencia.categoria),
        "tipo": pendencia.tipo,
        "motivo": pendencia.motivo,
        "certeza": pendencia.certeza,
        "item_id": pendencia.item_id,
        "item_texto": item.texto if item else "",
        "texto_proposto": pendencia.texto_proposto,
        "decisao": pendencia.decisao,
        "correcao": pendencia.correcao,
        # É isto que a tela de auditoria desenha ao lado da pendência:
        # a miniatura da foto e a região, quando houver.
        "evidencias": [_evidencia_para_dict(e) for e in evidencias],
        "fotos": sorted({e.foto_id for e in evidencias}),
    }


@roteador.get("/vistorias/{vistoria_id}/pendencias")
def listar_pendencias(vistoria_id: str, abertas: bool = True,
                      sessao: Session = Depends(obter_sessao),
                      usuario: Usuario = Depends(usuario_atual)):
    _achar(sessao, Vistoria, vistoria_id)
    consulta = (
        select(Pendencia).join(Comodo, Pendencia.comodo_id == Comodo.id)
        .where(Comodo.vistoria_id == vistoria_id)
    )
    if abertas:
        consulta = consulta.where(Pendencia.decisao == "")
    # Conflito de escopo primeiro, depois a certeza mais baixa: é a ordem em
    # que o vistoriador ganha mais decidindo.
    pendencias = sorted(
        sessao.scalars(consulta).all(),
        key=lambda p: (p.tipo != "scope_conflict", p.certeza),
    )
    return [_pendencia_para_dict(sessao, pendencia) for pendencia in pendencias]


class EntradaDecisao(BaseModel):
    decisao: str
    correcao: str = ""
    regra: str = ""
    tipo_correcao: str = ""
    razao: str = ""


@roteador.post("/pendencias/{pendencia_id}/decisao")
def decidir(pendencia_id: str, dados: EntradaDecisao,
            sessao: Session = Depends(obter_sessao),
            usuario: Usuario = Depends(usuario_atual)):
    pendencia = _achar(sessao, Pendencia, pendencia_id)
    try:
        resultado = servicos.aplicar_decisao(
            sessao, pendencia, dados.decisao, dados.correcao, dados.regra,
            usuario.id, dados.tipo_correcao, dados.razao,
        )
    except ValueError as erro:
        raise _erro(str(erro))
    return resultado


# ==========================================================================
# Regras
# ==========================================================================

class EntradaRegra(BaseModel):
    texto: str = Field(min_length=5)


@roteador.get("/regras")
def listar_regras(sessao: Session = Depends(obter_sessao),
                  usuario: Usuario = Depends(usuario_atual)):
    regras = sessao.scalars(select(Regra).order_by(Regra.criado_em)).all()
    return [{"id": r.id, "texto": r.texto, "ativa": r.ativa, "origem": r.origem,
             "adotada_em": r.adotada_em.isoformat() if r.adotada_em else None}
            for r in regras]


@roteador.post("/regras", status_code=status.HTTP_201_CREATED)
def criar_regra(dados: EntradaRegra, sessao: Session = Depends(obter_sessao),
                usuario: Usuario = Depends(usuario_atual)):
    """Adoção explícita (regra 22): a regra só passa a valer porque alguém
    clicou, nunca porque o sistema 'aprendeu'."""
    regra = servicos.adotar_regra(sessao, dados.texto)
    return {"id": regra.id, "texto": regra.texto, "ativa": regra.ativa}


@roteador.post("/regras/{regra_id}/desativar")
def desativar_regra(regra_id: str, sessao: Session = Depends(obter_sessao),
                    usuario: Usuario = Depends(usuario_atual)):
    regra = _achar(sessao, Regra, regra_id)
    regra.ativa = False
    sessao.commit()
    return {"id": regra.id, "ativa": regra.ativa}


# ==========================================================================
# Exportação (regra 33: o .txt mantém o formato atual)
# ==========================================================================

def _nome_arquivo(titulo: str) -> str:
    seguro = "".join(c if c.isalnum() or c in " -_" else "_" for c in titulo).strip()
    return seguro or "vistoria"


@roteador.get("/vistorias/{vistoria_id}/exportar/laudo.txt")
def exportar_laudo(vistoria_id: str, sessao: Session = Depends(obter_sessao),
                   usuario: Usuario = Depends(usuario_atual)):
    vistoria = _achar(sessao, Vistoria, vistoria_id)
    texto = servicos.texto_do_laudo(vistoria)
    nome = f"{_nome_arquivo(vistoria.titulo)} - Laudo_Vistoria_Completo.txt"
    return Response(
        content=texto.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@roteador.get("/vistorias/{vistoria_id}/exportar/vistoria.zip")
def exportar_zip(vistoria_id: str, com_fotos: bool = True,
                 sessao: Session = Depends(obter_sessao),
                 usuario: Usuario = Depends(usuario_atual)):
    """ZIP no MESMO layout que o CLI espera: uma pasta por cômodo, com as
    fotos e o <cômodo>_vistoria.txt dentro, e o consolidado na raiz.

    Assim a exportação volta a entrar no fluxo antigo sem conversão."""
    from app.storage import caminho_absoluto

    vistoria = _achar(sessao, Vistoria, vistoria_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Laudo_Vistoria_Completo.txt", servicos.texto_do_laudo(vistoria))
        zf.writestr("Pendencias_Validacao.txt", _texto_pendencias(sessao, vistoria))
        for comodo in sorted(vistoria.comodos, key=lambda c: (c.ordem, c.nome)):
            if any(not item.removido for item in comodo.itens):
                zf.writestr(f"{comodo.nome}/{comodo.nome}_vistoria.txt",
                            servicos.texto_do_comodo(comodo))
            # O rastro de evidências, para auditoria fora do sistema.
            if comodo.evidencias:
                zf.writestr(
                    f"{comodo.nome}/_evidencias.json",
                    json.dumps([_evidencia_para_dict(e) for e in comodo.evidencias],
                               ensure_ascii=False, indent=2),
                )
            if not com_fotos:
                continue
            for foto in comodo.fotos:
                try:
                    caminho = caminho_absoluto(foto.caminho)
                except ArquivoRejeitado:
                    continue
                if caminho.is_file():
                    zf.writestr(f"{comodo.nome}/{foto.nome_original}", caminho.read_bytes())

    buffer.seek(0)
    nome = f"{_nome_arquivo(vistoria.titulo)}.zip"
    return StreamingResponse(
        buffer, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


def _texto_pendencias(sessao: Session, vistoria: Vistoria) -> str:
    """Pendências em aberto no formato legível de sempre."""
    linhas = [f"PENDÊNCIAS DE VALIDAÇÃO — {vistoria.titulo}", ""]
    consulta = (
        select(Pendencia).join(Comodo, Pendencia.comodo_id == Comodo.id)
        .where(Comodo.vistoria_id == vistoria.id, Pendencia.decisao == "")
    )
    pendencias = sessao.scalars(consulta).all()
    if not pendencias:
        linhas.append("Nenhuma pendência em aberto.")
        return "\n".join(linhas) + "\n"
    for numero, pendencia in enumerate(pendencias, start=1):
        comodo = sessao.get(Comodo, pendencia.comodo_id)
        item = sessao.get(ItemLaudo, pendencia.item_id) if pendencia.item_id else None
        linhas += [
            f"--- #{numero} ---",
            f"Cômodo: {comodo.nome if comodo else ''}",
            f"Categoria: {ROTULOS_CATEGORIA.get(pendencia.categoria, pendencia.categoria)}",
            f"Tipo: {pendencia.tipo}",
            f"Certeza: {pendencia.certeza}%",
            f"Motivo: {pendencia.motivo}",
            f"Item: {item.texto if item else pendencia.texto_proposto}",
            "",
        ]
    return "\n".join(linhas) + "\n"


# ==========================================================================
# Importação de vistoria antiga (regra 42)
# ==========================================================================

@roteador.post("/importar", status_code=status.HTTP_201_CREATED)
async def importar_vistoria_antiga(
    titulo: str = Form(...),
    notas: str = Form(""),
    arquivo: UploadFile = File(...),
    sessao: Session = Depends(obter_sessao),
    usuario: Usuario = Depends(usuario_atual),
):
    """Importa a estrutura antiga (pasta do imóvel -> cômodos -> fotos + .txt).

    Não inventa nada: o que o ZIP não traz, não é criado. Os itens importados
    entram SEM evidência e SEM pendência, porque o laudo antigo não tem esse
    rastro — dizer que têm seria fabricar procedência."""
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX_ZIP:
        raise _erro(f"ZIP maior que o limite de {TAMANHO_MAX_ZIP // (1024 * 1024)} MB.")

    try:
        arquivo_zip = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile:
        raise _erro("Arquivo ZIP inválido ou corrompido.")

    vistoria = Vistoria(titulo=titulo.strip() or "Vistoria importada", notas=notas)
    sessao.add(vistoria)
    sessao.commit()

    # 1. fotos
    try:
        por_comodo = ler_zip_de_vistoria(conteudo)
    except ArquivoRejeitado:
        por_comodo = {}
    importadas = 0
    for nome_comodo, fotos in por_comodo.items():
        comodo = _criar_comodo(sessao, vistoria, nome_comodo)
        ordem = 0
        for nome_arquivo, dados in fotos:
            foto_id = novo_id()
            try:
                metadados = salvar_foto(comodo.id, foto_id, dados, nome_arquivo)
            except ArquivoRejeitado:
                continue
            sessao.add(Foto(id=foto_id, comodo_id=comodo.id,
                            nome_original=nome_arquivo[:300], ordem=ordem, **metadados))
            ordem += 1
            importadas += 1
    sessao.commit()

    # 2. laudo já escrito, dos <cômodo>_vistoria.txt
    from core.report_writer import parsear_txt_comodo
    import tempfile
    from pathlib import Path

    comodos_com_laudo = 0
    for entrada in arquivo_zip.infolist():
        nome = entrada.filename.replace("\\", "/")
        if ".." in nome.split("/") or not nome.endswith("_vistoria.txt"):
            continue
        if entrada.file_size > 2 * 1024 * 1024:
            continue
        base = nome.rsplit("/", 1)[-1]
        nome_comodo = base[: -len("_vistoria.txt")]
        comodo = _criar_comodo(sessao, vistoria, nome_comodo)
        texto = arquivo_zip.read(entrada).decode("utf-8", errors="replace")
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / base
            caminho.write_text(texto, encoding="utf-8")
            dados = parsear_txt_comodo(str(caminho))
        ordem = 0
        for categoria in CATEGORIAS:
            for linha in (dados.get(categoria) or "").split("\n"):
                linha = linha.strip()
                if not linha or not linha.startswith("*"):
                    continue
                sessao.add(ItemLaudo(comodo_id=comodo.id, categoria=categoria,
                                     texto=linha, ordem=ordem, certeza=100,
                                     motivo="importado de laudo anterior"))
                ordem += 1
        if ordem:
            comodo.estado = EstadoComodo.CONCLUIDO
            comodos_com_laudo += 1
    sessao.commit()

    return {"vistoria": _resumo_vistoria(sessao, vistoria),
            "fotos_importadas": importadas,
            "comodos_com_laudo": comodos_com_laudo}
