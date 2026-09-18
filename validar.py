"""
Aplica as decisões do vistoriador sobre os itens de baixa certeza.

Fluxo: main.py gera o laudo e o Pendencias_Validacao.txt (na pasta do
imóvel) -> o vistoriador confere os itens nas fotos e preenche DECISÃO /
CORREÇÃO / REGRA -> este script aplica as decisões nos .txt dos cômodos,
reconstrói o laudo consolidado e adota as regras gerais novas para as
próximas vistorias (ver validacao.py).

Uso:
    python validar.py "C:\\caminho\\para\\o\\imovel"
"""

import argparse
import os

from config import ROTULOS_CATEGORIA
from main import listar_pastas_comodo
from report_writer import parsear_txt_comodo, salvar_relatorio_completo
from validacao import NOME_ARQUIVO_PENDENCIAS, aplicar_pendencias


def main():
    parser = argparse.ArgumentParser(
        description="Aplica no laudo as decisões preenchidas no arquivo de pendências de validação."
    )
    parser.add_argument("pasta_imovel", help="Caminho da pasta do imóvel (a mesma usada em main.py)")
    args = parser.parse_args()

    if not os.path.isfile(os.path.join(args.pasta_imovel, NOME_ARQUIVO_PENDENCIAS)):
        print(f"Não encontrei {NOME_ARQUIVO_PENDENCIAS} nessa pasta — rode main.py primeiro.")
        return

    resumo = aplicar_pendencias(args.pasta_imovel)

    if resumo["comodos_alterados"]:
        resultados = {}
        for nome_comodo in listar_pastas_comodo(args.pasta_imovel):
            caminho_txt = os.path.join(args.pasta_imovel, nome_comodo, f"{nome_comodo}_vistoria.txt")
            if os.path.isfile(caminho_txt):
                resultados[nome_comodo] = parsear_txt_comodo(caminho_txt)
        caminho_completo = salvar_relatorio_completo(args.pasta_imovel, resultados)
        print(f"Laudo atualizado ({', '.join(resumo['comodos_alterados'])}): {caminho_completo}")

    print(f"Decisões aplicadas: {len(resumo['aplicadas'])}")
    for regra in resumo["regras"]:
        print(f"  Regra adotada para as próximas vistorias: {regra}")

    restantes = resumo["restantes"]
    if not restantes:
        print("Nenhuma pendência em aberto — laudo liberado.")
        return

    print(f"\nAinda em aberto: {len(restantes)} item(ns)")
    for pendencia in restantes:
        rotulo = ROTULOS_CATEGORIA.get(pendencia.get("categoria", ""), pendencia.get("categoria", ""))
        situacao = pendencia.get("situacao") or "sem DECISÃO preenchida"
        print(f"  - {pendencia.get('comodo', '')} / {rotulo}: {situacao}")
    print(f"Veja em: {os.path.join(args.pasta_imovel, NOME_ARQUIVO_PENDENCIAS)}")


if __name__ == "__main__":
    main()
