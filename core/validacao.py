"""
Pendências de validação do laudo.

main.py separa os itens que o modelo avaliou com certeza abaixo de
config.LIMIAR_CERTEZA e grava a lista em Pendencias_Validacao.txt, na pasta
do imóvel. O vistoriador confere cada item nas fotos, preenche a DECISÃO e
roda validar.py, que:

- aplica as decisões nos .txt dos cômodos (OK / CORRIGIR / REMOVER);
- adota como regra geral o que ele escrever no campo REGRA. Essas regras vão
  para config.ARQUIVO_REGRAS_VALIDADAS e entram no prompt das próximas
  vistorias (ver style_guide._regras).

O arquivo de pendências descreve o imóvel do cliente: fica na pasta do
imóvel, nunca no repositório (que é público).
"""

import os
import unicodedata
from datetime import date

from core.config import ARQUIVO_REGRAS_VALIDADAS, LIMIAR_CERTEZA, ROTULOS_CATEGORIA
from core.report_writer import (
    TEXTO_NAO_SE_APLICA,
    TEXTO_SEM_OBSERVACOES,
    normalizar_linha,
    parsear_txt_comodo,
    salvar_txt_comodo,
    texto_vazio_da_categoria,
)
from core.style_guide import carregar_regras_validadas

NOME_ARQUIVO_PENDENCIAS = "Pendencias_Validacao.txt"
MARCADOR_ITEM = "--- #"
DECISOES_VALIDAS = ("OK", "CORRIGIR", "REMOVER")

_CATEGORIA_POR_ROTULO = {rotulo: categoria for categoria, rotulo in ROTULOS_CATEGORIA.items()}

# Campo no arquivo (maiúsculo, sem acento) -> chave no dicionário.
_CAMPOS = {
    "COMODO": "comodo",
    "CATEGORIA": "categoria",
    "CERTEZA": "certeza",
    "MOTIVO": "motivo",
    "ITEM": "texto",
    "TIPO": "tipo",
    "SITUACAO": "situacao",
    "DECISAO": "decisao",
    "CORRECAO": "correcao",
    "REGRA": "regra",
}

CABECALHO_REGRAS = """\
# Regras de redação adotadas pelo vistoriador a partir de pendências
# validadas (validar.py). Entram no prompt de TODA vistoria, junto com
# REGRAS_GERAIS de style_guide.py, e prevalecem sobre elas em caso de
# conflito.
#
# Este arquivo vai para o repositório, que é PÚBLICO: aqui só entra regra
# geral de redação — nunca endereço, nome de cliente ou fato de um imóvel.
# Pode editar à mão: uma regra por linha, começando com "- ".
"""


def _sem_acento_maiusculo(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return texto.strip().upper()


def _cabecalho(pasta_imovel: str) -> str:
    return (
        "PENDÊNCIAS DE VALIDAÇÃO DO LAUDO\n"
        f"Imóvel: {os.path.basename(os.path.normpath(pasta_imovel))}\n"
        "\n"
        f"Itens que a IA descreveu com certeza abaixo de {LIMIAR_CERTEZA}%. Eles JÁ\n"
        "ESTÃO NO LAUDO — confira cada um nas fotos antes de entregar.\n"
        "\n"
        'Pendência com "Tipo: falta" é o contrário: a conferência (conferir.py)\n'
        'achou nas fotos um item que NÃO está no laudo, e a linha "Item" é a\n'
        "proposta de texto. Nessas, OK = aceito, pode acrescentar ao laudo;\n"
        "REMOVER = descarte a proposta; CORRIGIR = acrescente, mas com o texto\n"
        "que eu escrevi em CORREÇÃO.\n"
        "\n"
        "Como preencher (uma linha por campo):\n"
        "  DECISÃO:  OK        o item está certo, fica como está\n"
        "            CORRIGIR  escreva o texto certo em CORREÇÃO\n"
        "            REMOVER   o item sai do laudo\n"
        "  Se a pendência tiver mais de uma linha \"Item:\" (ex.: um item\n"
        "  repetido escrito com \"Mais um/uma\"), a CORREÇÃO substitui TODAS\n"
        "  elas por uma linha só — ex.: \"Duas portas em madeira ...\".\n"
        "  REGRA:    opcional. Só preencha se o erro vale para QUALQUER imóvel\n"
        "            (ex.: Nunca citar roseta se ela não aparecer na foto).\n"
        "            Fato deste imóvel (ex.: a cozinha não tem porta) NÃO é\n"
        "            regra geral — resolva só com CORRIGIR/REMOVER.\n"
        "            A regra vai para um arquivo público: nunca escreva nela\n"
        "            endereço, nome de cliente ou detalhe deste imóvel.\n"
        "\n"
        f'Depois de preencher, rode:  python validar.py "{pasta_imovel}"\n'
        "Itens sem DECISÃO continuam aqui para a próxima vez.\n"
    )


def _bloco(numero: int, pendencia: dict) -> str:
    categoria = pendencia.get("categoria", "")
    linhas = [
        f"{MARCADOR_ITEM}{numero} ---",
        f"Cômodo: {pendencia.get('comodo', '')}",
        f"Categoria: {ROTULOS_CATEGORIA.get(categoria, categoria)}",
        f"Certeza: {pendencia.get('certeza', '')}%",
        f"Motivo: {pendencia.get('motivo', '')}",
    ]
    # Pendência de várias linhas (ex.: "Mais um/uma" + a linha anterior):
    # uma linha "Item:" para cada uma.
    if pendencia.get("tipo"):
        linhas.append(f"Tipo: {pendencia['tipo']}")
    linhas += [f"Item: {linha}" for linha in pendencia.get("texto", "").split("\n")]
    if pendencia.get("situacao"):
        linhas.append(f"Situação: {pendencia['situacao']}")
    linhas += [
        f"DECISÃO: {pendencia.get('decisao', '')}".rstrip(),
        f"CORREÇÃO: {pendencia.get('correcao', '')}".rstrip(),
        f"REGRA: {pendencia.get('regra', '')}".rstrip(),
    ]
    return "\n".join(linhas)


def salvar_pendencias(pasta_imovel: str, pendencias: list) -> str:
    """Grava (ou sobrescreve) o arquivo de pendências na pasta do imóvel.
    Sem pendências, o arquivo diz isso — assim uma lista antiga não fica
    parecendo atual depois de uma nova rodada."""
    caminho = os.path.join(pasta_imovel, NOME_ARQUIVO_PENDENCIAS)
    partes = [_cabecalho(pasta_imovel)]
    if pendencias:
        partes += [_bloco(numero, p) for numero, p in enumerate(pendencias, start=1)]
    else:
        partes.append("Nenhuma pendência em aberto.")
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n\n".join(partes) + "\n")
    return caminho


def ler_pendencias(pasta_imovel: str) -> list:
    """Lê o arquivo de pendências. Tolerante a acento e maiúscula/minúscula
    nos nomes dos campos e na DECISÃO ("corrigir", "Remover", etc.)."""
    caminho = os.path.join(pasta_imovel, NOME_ARQUIVO_PENDENCIAS)
    if not os.path.isfile(caminho):
        return []

    pendencias, atual = [], None
    with open(caminho, "r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.rstrip("\n")
            if linha.startswith(MARCADOR_ITEM):
                atual = {}
                pendencias.append(atual)
                continue
            if atual is None or ":" not in linha:
                continue
            chave, valor = linha.split(":", 1)
            campo = _CAMPOS.get(_sem_acento_maiusculo(chave))
            if campo == "texto" and atual.get("texto"):
                # Pendência com várias linhas "Item:".
                atual["texto"] += "\n" + valor.strip()
            elif campo:
                atual[campo] = valor.strip()

    for pendencia in pendencias:
        rotulo = pendencia.get("categoria", "")
        pendencia["categoria"] = _CATEGORIA_POR_ROTULO.get(rotulo, rotulo)
        pendencia["certeza"] = pendencia.get("certeza", "").rstrip("%").strip()
        pendencia["decisao"] = _sem_acento_maiusculo(pendencia.get("decisao", ""))
    return pendencias


def aplicar_no_texto(texto_categoria: str, categoria: str, pendencia: dict) -> tuple:
    """Aplica a decisão de uma pendência no texto de uma categoria.
    Uma pendência pode ter várias linhas: CORRIGIR troca todas por uma
    linha só (no lugar da primeira), REMOVER tira todas.
    Devolve (novo_texto, erro); erro é None quando deu certo."""
    vazio = texto_vazio_da_categoria(categoria)
    # report_writer omite "Não se aplica." do .txt: categoria ausente
    # equivale a ter só a linha de categoria vazia.
    linhas = [linha for linha in texto_categoria.split("\n") if linha.strip()] or [vazio]

    itens = [item for item in pendencia.get("texto", "").split("\n") if item.strip()]

    # Pendência de item FALTANDO (vem da conferência do conferir.py): a
    # linha em "Item:" é uma proposta que ainda NÃO está no laudo, então
    # não adianta procurá-la no texto. OK aceita a proposta, CORRIGIR
    # aceita com o texto do vistoriador, REMOVER descarta.
    if pendencia.get("tipo") == "falta":
        if pendencia["decisao"] == "REMOVER":
            return texto_categoria, None
        novas = itens
        if pendencia["decisao"] == "CORRIGIR":
            novas = [normalizar_linha(linha)
                     for linha in pendencia.get("correcao", "").split("\n") if linha.strip()]
            if not novas:
                return texto_categoria, "DECISÃO é CORRIGIR, mas CORREÇÃO está vazia"
        reais = [linha for linha in linhas
                 if linha not in (TEXTO_NAO_SE_APLICA, TEXTO_SEM_OBSERVACOES)]
        reais += [linha for linha in novas if linha not in reais]
        return "\n".join(reais) if reais else vazio, None

    if not itens or any(item not in linhas for item in itens):
        return texto_categoria, (
            "item não encontrado no laudo (o texto pode ter mudado, ex.: pelo "
            "revisar.py) — ajuste direto no .txt do cômodo e apague esta pendência"
        )

    if pendencia["decisao"] == "CORRIGIR":
        nova = normalizar_linha(pendencia.get("correcao", ""))
        if not nova:
            return texto_categoria, "DECISÃO é CORRIGIR, mas CORREÇÃO está vazia"
        primeira = linhas.index(itens[0])
        linhas[primeira] = nova
        for item in itens[1:]:
            linhas.remove(item)
    elif pendencia["decisao"] == "REMOVER":
        for item in itens:
            linhas.remove(item)

    reais = [linha for linha in linhas if linha not in (TEXTO_NAO_SE_APLICA, TEXTO_SEM_OBSERVACOES)]
    novo_texto = "\n".join(reais) if reais else vazio
    return novo_texto, None


def adotar_regras(regras: list) -> list:
    """Acrescenta as regras novas ao arquivo de regras validadas, sem
    repetir as que já existem. Devolve as que foram de fato adicionadas."""
    existentes = {regra.casefold() for regra in carregar_regras_validadas()}
    novas = []
    for regra in regras:
        regra = " ".join(regra.split())
        if regra and regra.casefold() not in existentes:
            novas.append(regra)
            existentes.add(regra.casefold())
    if not novas:
        return []

    arquivo_novo = not os.path.isfile(ARQUIVO_REGRAS_VALIDADAS)
    with open(ARQUIVO_REGRAS_VALIDADAS, "a", encoding="utf-8") as arquivo:
        if arquivo_novo:
            arquivo.write(CABECALHO_REGRAS)
        arquivo.write(f"\n# adotadas em {date.today():%d/%m/%Y}\n")
        for regra in novas:
            arquivo.write(f"- {regra}\n")
    return novas


def aplicar_pendencias(pasta_imovel: str) -> dict:
    """Aplica nos .txt dos cômodos as decisões preenchidas no arquivo de
    pendências, adota as regras novas e regrava o arquivo só com o que
    ficou em aberto. Não reconstrói o laudo consolidado — isso é com o
    validar.py, que sabe listar as pastas de cômodo.

    Devolve {"aplicadas", "restantes", "regras", "comodos_alterados"}."""
    aplicadas, restantes, regras = [], [], []
    dados_por_comodo, alterados = {}, set()

    for pendencia in ler_pendencias(pasta_imovel):
        pendencia.pop("situacao", None)
        decisao = pendencia["decisao"]
        if not decisao:
            restantes.append(pendencia)
            continue
        if decisao not in DECISOES_VALIDAS:
            pendencia["situacao"] = f'DECISÃO "{decisao}" não reconhecida — use OK, CORRIGIR ou REMOVER'
            restantes.append(pendencia)
            continue

        comodo, categoria = pendencia.get("comodo", ""), pendencia.get("categoria", "")
        caminho_txt = os.path.join(pasta_imovel, comodo, f"{comodo}_vistoria.txt")
        if categoria not in ROTULOS_CATEGORIA or not os.path.isfile(caminho_txt):
            pendencia["situacao"] = "cômodo ou categoria não encontrados — confira se o nome não foi alterado"
            restantes.append(pendencia)
            continue

        if comodo not in dados_por_comodo:
            dados_por_comodo[comodo] = parsear_txt_comodo(caminho_txt)
        dados = dados_por_comodo[comodo]

        novo_texto, erro = aplicar_no_texto(dados.get(categoria, ""), categoria, pendencia)
        if erro:
            pendencia["situacao"] = erro
            restantes.append(pendencia)
            continue

        if novo_texto != dados.get(categoria, ""):
            dados[categoria] = novo_texto
            alterados.add(comodo)
        aplicadas.append(pendencia)
        if pendencia.get("regra"):
            regras.append(pendencia["regra"])

    for comodo in alterados:
        salvar_txt_comodo(os.path.join(pasta_imovel, comodo), comodo, dados_por_comodo[comodo])

    adotadas = adotar_regras(regras)
    salvar_pendencias(pasta_imovel, restantes)
    return {
        "aplicadas": aplicadas,
        "restantes": restantes,
        "regras": adotadas,
        "comodos_alterados": sorted(alterados),
    }
