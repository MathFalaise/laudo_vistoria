"""
Revisa um laudo JÁ GERADO (pelos .txt salvos por main.py), padronizando
terminologia e formatação conforme as regras atuais de style_guide.py —
SEM reanalisar as fotos. Útil quando o style_guide muda depois de já ter
rodado o laudo: em vez de gastar cota de API reprocessando imagens, esse
script faz UMA chamada de texto puro pro imóvel inteiro.

Uso:
    python revisar.py "C:\\caminho\\para\\o\\imovel"
"""

import argparse
import os

from gemini_client import criar_cliente, revisar_laudo
from main import listar_pastas_comodo
from report_writer import parsear_txt_comodo, salvar_txt_comodo, salvar_relatorio_completo
from validacao import NOME_ARQUIVO_PENDENCIAS, ler_pendencias


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Revisa o texto de um laudo já gerado (sem reanalisar fotos), "
            "padronizando terminologia conforme as regras atuais de style_guide.py."
        )
    )
    parser.add_argument("pasta_imovel", help="Caminho da pasta do imóvel (a mesma usada em main.py)")
    parser.add_argument(
        "--notas",
        default="",
        help="Informações confirmadas sobre este imóvel, repassadas à revisão (ver main.py --notas).",
    )
    parser.add_argument(
        "--ignorar-pendencias",
        action="store_true",
        help="Revisa mesmo com pendências de validação em aberto (elas deixam de bater com o laudo).",
    )
    args = parser.parse_args()

    # A revisão reescreve o texto dos itens; pendências em aberto apontam
    # para o texto antigo e o validar.py deixaria de encontrá-las.
    abertas = ler_pendencias(args.pasta_imovel)
    if abertas and not args.ignorar_pendencias:
        print(
            f"Há {len(abertas)} pendência(s) de validação em aberto em "
            f"{NOME_ARQUIVO_PENDENCIAS}. Rode validar.py antes do revisar.py — a "
            "revisão muda o texto dos itens e as pendências deixariam de bater. "
            "Para revisar mesmo assim, use --ignorar-pendencias."
        )
        return

    cliente = criar_cliente()
    nomes_comodo = listar_pastas_comodo(args.pasta_imovel)

    resultados = {}
    for nome_comodo in nomes_comodo:
        pasta_comodo = os.path.join(args.pasta_imovel, nome_comodo)
        caminho_txt = os.path.join(pasta_comodo, f"{nome_comodo}_vistoria.txt")
        if not os.path.isfile(caminho_txt):
            print(f"Pulando '{nome_comodo}': não encontrei {caminho_txt}")
            continue
        resultados[nome_comodo] = parsear_txt_comodo(caminho_txt)

    if not resultados:
        print("Nenhum <cômodo>_vistoria.txt encontrado — rode main.py primeiro.")
        return

    print(f"Revisando {len(resultados)} cômodo(s) (1 chamada de texto puro, sem fotos)...")
    revisado = revisar_laudo(cliente, resultados, args.notas)

    for nome_comodo, dados in revisado.items():
        pasta_comodo = os.path.join(args.pasta_imovel, nome_comodo)
        caminho_txt = salvar_txt_comodo(pasta_comodo, nome_comodo, dados)
        print(f"  Atualizado: {caminho_txt}")

    caminho_completo = salvar_relatorio_completo(args.pasta_imovel, revisado)
    print(f"\nLaudo completo atualizado: {caminho_completo}")


if __name__ == "__main__":
    main()
