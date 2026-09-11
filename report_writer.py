"""
Grava os resultados de cada cômodo em arquivo .txt (um por cômodo, salvo
dentro da própria pasta de fotos) e monta um relatório único consolidado
com o imóvel inteiro.
"""

import os

from config import CATEGORIAS, ROTULOS_CATEGORIA


def montar_texto_comodo(nome_comodo: str, dados: dict) -> str:
    linhas = [f"{nome_comodo.upper()}", ""]
    for categoria in CATEGORIAS:
        rotulo = ROTULOS_CATEGORIA[categoria]
        texto = dados.get(categoria, "").strip()
        linhas.append(f"{rotulo}:")
        linhas.append(texto if texto else "Não se aplica.")
        linhas.append("")
    return "\n".join(linhas).strip() + "\n"


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
