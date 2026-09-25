"""
Ponte entre o motor (core/) e o banco.

Este módulo NÃO tem regra de laudo. Toda decisão sobre o que o laudo diz mora
em core/ e é a mesma do CLI (regra 30 do pedido); aqui só se traduz entre o
formato do motor ({categoria: texto}) e o grafo persistido
(Foto -> Evidencia -> ItemLaudo -> Pendencia).

Se você se pegar escrevendo aqui uma regra de redação, ela está no lugar
errado — o CLI não vai enxergá-la, e os dois vão divergir.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DIRETORIO_FOTOS
from app.models import (Comodo, CorrecaoHumana, EstadoComodo, Evidencia,
                        HistoricoItem, ItemLaudo, Pendencia, Regra,
                        TipoPendencia, Vistoria, agora)
from core.config import CATEGORIAS, LIMIAR_CERTEZA, ROTULOS_CATEGORIA
from core.pipeline import PREFIXO_CONFLITO, processar_comodo
from core.report_writer import (TEXTO_NAO_SE_APLICA, TEXTO_SEM_OBSERVACOES,
                                montar_texto_comodo, normalizar_linha,
                                texto_vazio_da_categoria)
from core.style_guide import carregar_regras_validadas, definir_regras_extras

DECISOES_VALIDAS = ("OK", "CORRIGIR", "REMOVER")


# --------------------------------------------------------------------------
# Regras (regra 23: em produção elas vivem no banco)
# --------------------------------------------------------------------------

def semear_regras(sessao: Session) -> int:
    """Traz o regras_validadas.txt para o banco na primeira subida.

    Elas entram JÁ ATIVAS: foram adotadas pelo vistoriador em vistorias reais,
    e desativá-las na migração seria perder trabalho validado. Regra nova,
    criada dentro do sistema, nasce inativa."""
    if sessao.scalar(select(Regra).limit(1)) is not None:
        return 0
    criadas = 0
    for texto in carregar_regras_validadas():
        sessao.add(Regra(texto=texto, ativa=True, origem="regras_validadas.txt",
                         adotada_em=agora()))
        criadas += 1
    sessao.commit()
    return criadas


def regras_ativas(sessao: Session) -> list:
    return list(sessao.scalars(
        select(Regra.texto).where(Regra.ativa.is_(True)).order_by(Regra.criado_em)
    ).all())


def aplicar_regras_no_motor(sessao: Session) -> None:
    """Empurra as regras do banco para o style_guide antes de qualquer chamada
    ao Gemini. Chamado no início de cada job — não na subida do servidor, para
    que adotar uma regra valha já no próximo processamento."""
    definir_regras_extras(regras_ativas(sessao))


def adotar_regra(sessao: Session, texto: str, vistoria_id: str | None = None) -> Regra | None:
    """Adoção EXPLÍCITA (regras 22 e 23). Nada aqui é automático: esta função
    só é chamada quando o vistoriador preenche o campo de regra e confirma."""
    texto = " ".join(str(texto).split())
    if not texto:
        return None
    existente = sessao.scalar(select(Regra).where(Regra.texto == texto))
    if existente:
        if not existente.ativa:
            existente.ativa = True
            existente.adotada_em = agora()
            sessao.commit()
        return existente
    regra = Regra(texto=texto, ativa=True, origem="pendencia",
                  vistoria_id=vistoria_id, adotada_em=agora())
    sessao.add(regra)
    sessao.commit()
    return regra


# --------------------------------------------------------------------------
# Laudo: do banco para o texto e de volta
# --------------------------------------------------------------------------

def dados_do_comodo(comodo: Comodo) -> dict:
    """{categoria: texto} no formato que o report_writer espera.

    Categoria sem item vira o texto vazio certo — "Sem observações." no OBS,
    "Não se aplica." no resto —, exatamente como no motor antigo."""
    dados = {}
    for categoria in CATEGORIAS:
        linhas = [
            item.texto for item in comodo.itens
            if item.categoria == categoria and not item.removido
        ]
        dados[categoria] = "\n".join(linhas) if linhas else texto_vazio_da_categoria(categoria)
    return dados


def texto_do_comodo(comodo: Comodo) -> str:
    return montar_texto_comodo(comodo.nome, dados_do_comodo(comodo))


def texto_do_laudo(vistoria: Vistoria) -> str:
    """O consolidado, no MESMO formato do arquivo que o CLI grava (regra 33):
    texto puro, com os cômodos separados por linha em branco dupla. Nada de
    Markdown."""
    partes = [
        texto_do_comodo(comodo)
        for comodo in sorted(vistoria.comodos, key=lambda c: (c.ordem, c.nome))
        if any(not item.removido for item in comodo.itens)
    ]
    return "\n\n".join(partes)


def _gravar_itens(sessao: Session, comodo: Comodo, dados: dict) -> dict:
    """Substitui os itens do cômodo pelos do processamento.

    Devolve {(categoria, texto): ItemLaudo} para as pendências e as evidências
    conseguirem apontar para o item certo por ID."""
    for item in list(comodo.itens):
        sessao.delete(item)
    sessao.flush()

    por_texto = {}
    ordem = 0
    for categoria in CATEGORIAS:
        texto = (dados.get(categoria) or "").strip()
        if not texto or texto in (TEXTO_NAO_SE_APLICA, TEXTO_SEM_OBSERVACOES):
            continue
        for linha in texto.split("\n"):
            linha = linha.strip()
            if not linha:
                continue
            item = ItemLaudo(comodo_id=comodo.id, categoria=categoria,
                             texto=linha, ordem=ordem)
            sessao.add(item)
            sessao.flush()
            sessao.add(HistoricoItem(item_id=item.id, texto_anterior="",
                                     texto_novo=linha, origem="ia"))
            por_texto[(categoria, linha)] = item
            ordem += 1
    return por_texto


def _gravar_evidencias(sessao: Session, comodo: Comodo, resultado, por_texto: dict) -> dict:
    """Grava as evidências e liga cada uma ao item que ela sustenta.

    Devolve {id do motor: id no banco}. Esse mapa é obrigatório: o motor gera
    ids próprios ("<foto>#3") e o banco gera UUIDs, e os conflitos de escopo
    referenciam os ids do motor. Sem traduzir, a tela de auditoria abriria a
    pendência sem a foto — que é justamente o que ela precisa mostrar.

    A ligação é por palavra: o modelo escreve o item a partir das observações,
    e não devolve "este item veio das evidências X e Y". Casar por substantivo
    é aproximado — e assumidamente aproximado. A tela mostra "evidências
    relacionadas", não "prova"; o que é exato é o vínculo Evidencia -> Foto,
    que é o que importa para auditar escopo."""
    for item in list(comodo.evidencias):
        sessao.delete(item)
    sessao.flush()

    itens_por_categoria = {}
    for (categoria, _), item in por_texto.items():
        itens_por_categoria.setdefault(categoria, []).append(item)

    ids_do_motor = {}
    for evidencia in resultado.evidencias:
        regiao = evidencia.regiao
        alvo = None
        if evidencia.aceita:
            candidatos = itens_por_categoria.get(evidencia.categoria, [])
            alvo = _melhor_item(evidencia.observacao, candidatos)
        linha = Evidencia(
            comodo_id=comodo.id,
            foto_id=evidencia.foto_id,
            item_id=alvo.id if alvo else None,
            categoria=evidencia.categoria,
            observacao=evidencia.observacao,
            confianca_percepcao=evidencia.confianca_percepcao,
            confianca_escopo=evidencia.confianca_escopo,
            confianca_final=evidencia.confianca_final,
            e_reflexo=evidencia.e_reflexo,
            e_ambiente_adjacente=evidencia.e_ambiente_adjacente,
            status=evidencia.status.value,
            motivo_descarte=(evidencia.motivo_descarte.value
                             if evidencia.motivo_descarte else ""),
            detalhe_descarte=evidencia.detalhe_descarte,
            regiao_x=regiao.x if regiao else None,
            regiao_y=regiao.y if regiao else None,
            regiao_largura=regiao.largura if regiao else None,
            regiao_altura=regiao.altura if regiao else None,
        )
        sessao.add(linha)
        sessao.flush()
        ids_do_motor[evidencia.id] = linha.id
    return ids_do_motor


_PALAVRAS_IGNORADAS = {
    "um", "uma", "uns", "umas", "o", "a", "os", "as", "de", "da", "do", "das",
    "dos", "em", "na", "no", "nas", "nos", "com", "e", "cor", "na", "bom",
    "estado", "regular", "tipo", "para",
}


def _melhor_item(observacao: str, candidatos: list):
    """O item cujo texto mais se parece com a observação. Sem candidato
    razoável, devolve None em vez de escolher o primeiro — um vínculo errado
    seria pior que nenhum na hora de auditar."""
    import re
    import unicodedata

    def palavras(texto: str) -> set:
        texto = unicodedata.normalize("NFKD", texto.lower())
        texto = texto.encode("ascii", "ignore").decode()
        return {p for p in re.findall(r"[a-z]{3,}", texto) if p not in _PALAVRAS_IGNORADAS}

    da_evidencia = palavras(observacao)
    if not da_evidencia:
        return None
    melhor, melhor_nota = None, 0
    for item in candidatos:
        comuns = len(da_evidencia & palavras(item.texto))
        if comuns > melhor_nota:
            melhor, melhor_nota = item, comuns
    return melhor if melhor_nota >= 2 else None


def _gravar_pendencias(sessao: Session, comodo: Comodo, resultado,
                       por_texto: dict, ids_do_motor: dict) -> int:
    """Pendências do processamento, já apontando para o ItemLaudo por ID.

    É a diferença prática da regra 17: no arquivo .txt a pendência era achada
    procurando o texto exato dentro do laudo, e sumia assim que alguém
    reescrevia a linha. Aqui ela sobrevive à reescrita."""
    for pendencia in sessao.scalars(
        select(Pendencia).where(Pendencia.comodo_id == comodo.id,
                                Pendencia.decisao == "")
    ).all():
        sessao.delete(pendencia)
    sessao.flush()

    criadas = 0
    for incerto in resultado.incertos:
        categoria = incerto.get("categoria", "obs")
        texto = incerto.get("texto", "")
        item = por_texto.get((categoria, texto))
        tipo = incerto.get("tipo") or (
            TipoPendencia.FALTA if incerto.get("tipo") == "falta"
            else TipoPendencia.CERTEZA
        )
        if "Mais um" in (incerto.get("motivo") or ""):
            tipo = TipoPendencia.REPETIDO
        sessao.add(Pendencia(
            comodo_id=comodo.id,
            item_id=item.id if item else None,
            categoria=categoria,
            tipo=tipo,
            motivo=incerto.get("motivo", ""),
            certeza=int(incerto.get("certeza") or 0),
            texto_proposto=texto,
        ))
        criadas += 1

    for conflito in resultado.conflitos:
        sessao.add(Pendencia(
            comodo_id=comodo.id,
            categoria=conflito.categoria,
            tipo=TipoPendencia.CONFLITO_ESCOPO,
            motivo=f"{PREFIXO_CONFLITO}. {conflito.resumo}",
            certeza=0,
            texto_proposto="",
            # Traduz os ids do motor para os do banco: é o que faz a tela de
            # auditoria conseguir abrir a foto da evidência.
            evidencia_ids=",".join(
                ids_do_motor[eid] for eid in conflito.evidencias if eid in ids_do_motor
            ),
        ))
        criadas += 1
    return criadas


def processar_comodo_persistindo(
    sessao: Session,
    comodo: Comodo,
    cliente,
    usar_evidencias: bool = True,
    progresso=None,
) -> Comodo:
    """Roda um cômodo pelo motor e grava o grafo inteiro.

    O estado do cômodo é gravado a cada etapa: se o servidor cair no meio, a
    subida seguinte sabe exatamente onde parou (regra 26)."""
    comodo.estado = EstadoComodo.PROCESSANDO
    comodo.erro = ""
    sessao.commit()

    try:
        caminhos = [str(DIRETORIO_FOTOS / foto.caminho) for foto in comodo.fotos]
        ids = [foto.id for foto in comodo.fotos]
        resultado = processar_comodo(
            cliente,
            nome_comodo=comodo.nome,
            notas_extras=comodo.vistoria.notas or "",
            usar_evidencias=usar_evidencias,
            ids_fotos=ids,
            progresso=progresso,
            caminhos=caminhos,
        )
    except Exception as erro:
        # Regra 26/isolamento por cômodo: a falha de um não derruba os outros.
        comodo.estado = EstadoComodo.FALHOU
        comodo.erro = f"{erro.__class__.__name__}: {erro}"
        sessao.commit()
        raise

    por_texto = _gravar_itens(sessao, comodo, resultado.dados)
    ids_do_motor = _gravar_evidencias(sessao, comodo, resultado, por_texto)
    _gravar_pendencias(sessao, comodo, resultado, por_texto, ids_do_motor)

    # A classificação de escopo volta para a Foto: a tela de auditoria mostra
    # por que aquela foto não contou.
    por_id = {foto.id: foto for foto in comodo.fotos}
    for foto_id, analise in resultado.analises.items():
        foto = por_id.get(foto_id)
        if foto is None:
            continue
        foto.escopo = analise.escopo.value
        foto.relevancia = analise.relevancia
        foto.ambiente_adjacente = analise.ambiente_adjacente
        foto.reflexo = analise.reflexo
        foto.motivo_escopo = analise.motivo

    comodo.estado = EstadoComodo.CONCLUIDO
    comodo.processado_em = agora()
    comodo.fotos_utilizaveis = resultado.fotos_utilizaveis
    comodo.cobertura_incompleta = resultado.cobertura_incompleta
    sessao.commit()
    return comodo


# --------------------------------------------------------------------------
# Decisão humana
# --------------------------------------------------------------------------

def aplicar_decisao(
    sessao: Session,
    pendencia: Pendencia,
    decisao: str,
    correcao: str = "",
    regra: str = "",
    usuario_id: str | None = None,
    tipo_correcao: str = "",
    razao: str = "",
) -> dict:
    """Aplica OK / CORRIGIR / REMOVER.

    Mesma semântica do CLI, inclusive a das pendências de proposta (conferência
    e conflito de escopo), em que o "item" ainda NÃO está no laudo: OK aceita,
    CORRIGIR aceita com o texto do vistoriador, REMOVER descarta.

    Nada aqui é automático (regra 38): esta função só roda quando uma pessoa
    clicou."""
    decisao = (decisao or "").strip().upper()
    if decisao not in DECISOES_VALIDAS:
        raise ValueError(f'Decisão "{decisao}" não reconhecida — use OK, CORRIGIR ou REMOVER.')

    correcao = normalizar_linha(correcao) if correcao.strip() else ""
    comodo = sessao.get(Comodo, pendencia.comodo_id)
    e_proposta = pendencia.tipo in (TipoPendencia.FALTA, TipoPendencia.CONFLITO_ESCOPO)
    resultado = {"item_id": None, "acao": ""}

    if decisao == "CORRIGIR" and not correcao:
        raise ValueError("A decisão é CORRIGIR, mas o texto da correção está vazio.")

    if e_proposta:
        if decisao == "REMOVER":
            resultado["acao"] = "proposta descartada"
        else:
            texto = correcao or normalizar_linha(pendencia.texto_proposto)
            if not texto:
                raise ValueError(
                    "Esta pendência não traz um texto pronto para o laudo — "
                    "use CORRIGIR e escreva a linha, ou REMOVER para descartar."
                )
            ordem = max((item.ordem for item in comodo.itens), default=-1) + 1
            item = ItemLaudo(comodo_id=comodo.id, categoria=pendencia.categoria,
                             texto=texto, ordem=ordem, certeza=100)
            sessao.add(item)
            sessao.flush()
            sessao.add(HistoricoItem(
                item_id=item.id, texto_anterior="", texto_novo=texto,
                origem="humano", pendencia_id=pendencia.id, usuario_id=usuario_id,
                evidencia_ids=pendencia.evidencia_ids,
            ))
            resultado.update(item_id=item.id, acao="item acrescentado")
    else:
        item = sessao.get(ItemLaudo, pendencia.item_id) if pendencia.item_id else None
        if item is None:
            raise ValueError(
                "O item desta pendência não existe mais no laudo — "
                "provavelmente o cômodo foi reprocessado."
            )
        anterior = item.texto
        if decisao == "CORRIGIR":
            item.texto = correcao
            resultado["acao"] = "item corrigido"
        elif decisao == "REMOVER":
            item.removido = True
            resultado["acao"] = "item removido"
        else:
            resultado["acao"] = "item mantido"
        if decisao != "OK":
            sessao.add(HistoricoItem(
                item_id=item.id, texto_anterior=anterior,
                texto_novo="" if decisao == "REMOVER" else item.texto,
                origem="humano", pendencia_id=pendencia.id, usuario_id=usuario_id,
                evidencia_ids=",".join(e.id for e in item.evidencias),
            ))
        resultado["item_id"] = item.id

    pendencia.decisao = decisao
    pendencia.correcao = correcao
    pendencia.regra_sugerida = regra or ""
    pendencia.resolvida_em = agora()
    pendencia.resolvida_por_id = usuario_id

    # Regra 21: coleta estruturada. Regra 22, logo depois: isto não treina
    # nada — é dado guardado para análise futura.
    if tipo_correcao or razao:
        sessao.add(CorrecaoHumana(
            vistoria_id=comodo.vistoria_id,
            pendencia_id=pendencia.id,
            item_id=resultado["item_id"],
            tipo=tipo_correcao or _tipo_por_pendencia(pendencia),
            acao={"OK": "ACEITA", "CORRIGIR": "CORRIGIDA", "REMOVER": "IGNORADA"}[decisao],
            razao=razao,
            usuario_id=usuario_id,
        ))

    regra_adotada = None
    if regra.strip():
        regra_adotada = adotar_regra(sessao, regra, comodo.vistoria_id)
    sessao.commit()

    resultado["regra_adotada"] = regra_adotada.texto if regra_adotada else None
    return resultado


def _tipo_por_pendencia(pendencia: Pendencia) -> str:
    if pendencia.tipo == TipoPendencia.CONFLITO_ESCOPO:
        return "AMBIENTE_ADJACENTE"
    if pendencia.tipo == TipoPendencia.REPETIDO:
        return "QUANTIDADE"
    if pendencia.tipo == TipoPendencia.FALTA:
        return "ITEM_FALTANDO"
    return "CERTEZA"


def resumo_pendencias(sessao: Session, vistoria_id: str) -> dict:
    abertas = sessao.scalars(
        select(Pendencia)
        .join(Comodo, Pendencia.comodo_id == Comodo.id)
        .where(Comodo.vistoria_id == vistoria_id, Pendencia.decisao == "")
    ).all()
    por_tipo: dict = {}
    for pendencia in abertas:
        por_tipo[pendencia.tipo] = por_tipo.get(pendencia.tipo, 0) + 1
    return {"abertas": len(abertas), "por_tipo": por_tipo,
            "limiar_certeza": LIMIAR_CERTEZA}


def rotulo(categoria: str) -> str:
    return ROTULOS_CATEGORIA.get(categoria, categoria)
