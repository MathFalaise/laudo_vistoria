"""
Ponto de entrada: percorre a pasta do imóvel (uma subpasta por cômodo),
processa cada cômodo com a API do Gemini e gera:
  - um .txt de laudo dentro de cada pasta de cômodo
  - um .txt consolidado com o imóvel inteiro, na raiz da pasta do imóvel

Uso:
    python main.py "C:\\caminho\\para\\o\\imovel"
"""

import argparse
import os

from gemini_client import criar_cliente
from room_processor import processar_comodo
from report_writer import salvar_txt_comodo, salvar_relatorio_completo


def listar_pastas_comodo(pasta_imovel: str) -> list:
    return sorted(
        nome
        for nome in os.listdir(pasta_imovel)
        if os.path.isdir(os.path.join(pasta_imovel, nome))
    )


def main():
    parser = argparse.ArgumentParser(
        description="Gera automaticamente o laudo de vistoria de um imóvel a partir das fotos organizadas por cômodo."
    )
    parser.add_argument("pasta_imovel", help="Caminho da pasta do imóvel (contendo uma subpasta por cômodo)")
    parser.add_argument(
        "--notas",
        default="",
        help=(
            "Informações confirmadas sobre este imóvel (ex.: cor exata de "
            "tinta de parede/teto) para o modelo usar em vez de advinhar "
            "pela foto. Aplicada a todos os cômodos desta execução."
        ),
    )
    args = parser.parse_args()

    cliente = criar_cliente()
    nomes_comodo = listar_pastas_comodo(args.pasta_imovel)

    if not nomes_comodo:
        print("Nenhuma subpasta de cômodo encontrada dentro da pasta informada.")
        return

    resultados = {}
    falhas = []
    for nome_comodo in nomes_comodo:
        pasta_comodo = os.path.join(args.pasta_imovel, nome_comodo)
        try:
            dados = processar_comodo(cliente, pasta_comodo, nome_comodo, args.notas)
        except Exception as erro:
            # Um cômodo problemático não deve derrubar o laudo inteiro dos
            # outros — registra a falha e segue para o próximo cômodo.
            print(f"  ERRO ao processar '{nome_comodo}': {erro}")
            falhas.append(nome_comodo)
            continue
        if not dados:
            continue
        caminho_txt = salvar_txt_comodo(pasta_comodo, nome_comodo, dados)
        print(f"  Salvo: {caminho_txt}")
        resultados[nome_comodo] = dados

    if resultados:
        caminho_completo = salvar_relatorio_completo(args.pasta_imovel, resultados)
        print(f"\nLaudo completo salvo em: {caminho_completo}")

    if falhas:
        print(f"\nCômodos que falharam e precisam ser rodados de novo: {', '.join(falhas)}")


if __name__ == "__main__":
    main()
