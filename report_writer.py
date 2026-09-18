"""
Grava os resultados de cada cômodo em arquivo .txt (um por cômodo, salvo
dentro da própria pasta de fotos) e monta um relatório único consolidado
com o imóvel inteiro.
"""

import os

from config import CATEGORIAS, ROTULOS_CATEGORIA

# Texto literal que INSTRUCAO_CATEGORIA manda o modelo responder quando uma
# categoria não existe naquele cômodo (ver style_guide.REGRAS_GERAIS). Uma
# categoria "não se aplica" não entra no .txt final — nem o rótulo nem o
# texto — em vez de deixar um bloco vazio no meio do laudo.
TEXTO_NAO_SE_APLICA = "Não se aplica."

# Equivalente de TEXTO_NAO_SE_APLICA para a categoria "obs" — esse aparece
# no laudo (confirma que o vistoriador olhou e não achou nada).
TEXTO_SEM_OBSERVACOES = "Sem observações."


def texto_vazio_da_categoria(categoria: str) -> str:
    """Texto que representa "nada a relatar" numa categoria."""
    return TEXTO_SEM_OBSERVACOES if categoria == "obs" else TEXTO_NAO_SE_APLICA


def normalizar_linha(texto: str) -> str:
    """Deixa uma linha de item no formato do laudo: começando com "*",
    exceto os textos literais de categoria vazia, que vão sem asterisco."""
    texto = " ".join(texto.split())
    sem_asterisco = texto.lstrip("*").strip()
    if sem_asterisco in (TEXTO_NAO_SE_APLICA, TEXTO_SEM_OBSERVACOES):
        return sem_asterisco
    return f"*{sem_asterisco}" if sem_asterisco else ""


def montar_texto_comodo(nome_comodo: str, dados: dict) -> str:
    linhas = [f"{nome_comodo.upper()}", ""]
    teve_categoria = False
    for categoria in CATEGORIAS:
        rotulo = ROTULOS_CATEGORIA[categoria]
        texto = dados.get(categoria, "").strip()
        if not texto or texto == TEXTO_NAO_SE_APLICA:
            continue
        linhas.append(f"{rotulo}:")
        linhas.append(texto)
        linhas.append("")
        teve_categoria = True
    if not teve_categoria:
        linhas.append("Nenhuma categoria aplicável neste cômodo.")
    return "\n".join(linhas).strip() + "\n"


def parsear_txt_comodo(caminho_txt: str) -> dict:
    """Lê um <comodo>_vistoria.txt já salvo (formato gerado por
    montar_texto_comodo) e devolve {categoria: texto}, no mesmo formato de
    `dados` que analisar_comodo produz. Usado pelo revisar.py para
    reprocessar um laudo já escrito sem precisar reanalisar as fotos.

    Como montar_texto_comodo agora omite categorias "Não se aplica.", elas
    voltam como string vazia aqui — sem problema, salvar_relatorio_completo/
    salvar_txt_comodo tratam string vazia do mesmo jeito."""
    rotulo_para_categoria = {rotulo: categoria for categoria, rotulo in ROTULOS_CATEGORIA.items()}

    with open(caminho_txt, "r", encoding="utf-8") as arquivo:
        linhas = arquivo.read().strip("\n").split("\n")

    dados = {}
    categoria_atual = None
    buffer = []

    def _fechar_categoria_atual():
        if categoria_atual is not None:
            dados[categoria_atual] = "\n".join(buffer).strip()

    for linha in linhas[1:]:  # linhas[0] é o nome do cômodo em maiúsculas
        rotulo_candidato = linha[:-1] if linha.endswith(":") else None
        if rotulo_candidato in rotulo_para_categoria:
            _fechar_categoria_atual()
            categoria_atual = rotulo_para_categoria[rotulo_candidato]
            buffer = []
        elif linha.strip():
            buffer.append(linha)
    _fechar_categoria_atual()

    return dados


def salvar_txt_comodo(pasta_comodo: str, nome_comodo: str, dados: dict) -> str:
    """Salva o laudo do cômodo como .txt dentro da própria pasta de fotos."""
    texto = montar_texto_comodo(nome_comodo, dados)
    caminho_saida = os.path.join(pasta_comodo, f"{nome_comodo}_vistoria.txt")
    with open(caminho_saida, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto)
    return caminho_saida


def salvar_relatorio_completo(pasta_imovel: str, resultados: dict) -> str:
    """Junta todos os cômodos processados num único .txt na raiz do imóvel."""
    partes = [montar_texto_comodo(nome, dados) for nome, dados in resultados.items()]
    texto_final = "\n\n".join(partes)

    caminho_saida = os.path.join(pasta_imovel, "Laudo_Vistoria_Completo.txt")
    with open(caminho_saida, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto_final)
    return caminho_saida
