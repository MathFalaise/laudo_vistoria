"""
CONFERÊNCIA do laudo: com o texto de cada cômodo já escrito, olha as fotos
de novo e aponta o que divergir — item que aparece na foto e ficou de fora,
afirmação que a foto não sustenta, material/cor/quantidade errados.

É o passo que pega o que a primeira leitura deixa passar. Numa auditoria
manual da R. Correia de Freitas (22/09/2026) apareceram, entre outros, um
chuveiro, um armário aéreo inteiro, um varal de teto e um teto descrito como
forro de PVC que na foto é laje pintada — tudo em laudo que já tinha passado
pelo sistema de certeza.

Barato de propósito: as fotos vão em MOSAICO (várias por imagem), porque o
Gemini cobra por imagem e não por pixel. Com
config.FOTOS_POR_MOSAICO_CONFERENCIA = 4, a conferência custa cerca de 1/4
de uma vistoria nova.

O que ela encontra NÃO entra sozinho no laudo: vira pendência em
Pendencias_Validacao.txt, com o texto sugerido pronto. O vistoriador aceita
com OK (ou CORRIGIR, com o texto dele) e o validar.py aplica.

Uso:
    python conferir.py "C:\\caminho\\para\\o\\imovel"
    python conferir.py "C:\\caminho" --comodos "Cozinha" "Sala"
"""

import argparse
import os

from config import FOTOS_POR_MOSAICO_CONFERENCIA
from gemini_client import conferir_comodo, criar_cliente
from image_utils import mosaicos_comodo
from main import listar_pastas_comodo
from report_writer import parsear_txt_comodo
from validacao import ler_pendencias, salvar_pendencias


def conferir_imovel(pasta_imovel: str, nomes_comodo: list, notas_extras: str = "") -> list:
    """Confere os cômodos pedidos e devolve as pendências encontradas."""
    cliente = criar_cliente()
    encontradas = []

    for nome_comodo in nomes_comodo:
        pasta_comodo = os.path.join(pasta_imovel, nome_comodo)
        caminho_txt = os.path.join(pasta_comodo, f"{nome_comodo}_vistoria.txt")
        if not os.path.isfile(caminho_txt):
            print(f"Pulando '{nome_comodo}': não encontrei {caminho_txt}", flush=True)
            continue

        dados = parsear_txt_comodo(caminho_txt)
        mosaicos, quantidade = mosaicos_comodo(pasta_comodo, FOTOS_POR_MOSAICO_CONFERENCIA)
        if not mosaicos:
            print(f"Pulando '{nome_comodo}': sem fotos.", flush=True)
            continue

        print(f"Conferindo {nome_comodo} ({quantidade} fotos em {len(mosaicos)} folha(s))...", flush=True)
        try:
            encontradas.extend(
                conferir_comodo(cliente, mosaicos, nome_comodo, dados, quantidade, notas_extras)
            )
        except Exception as erro:
            # Um cômodo que falha não pode derrubar a conferência inteira.
            print(f"  ERRO ao conferir '{nome_comodo}': {erro.__class__.__name__}: {erro}", flush=True)

    return encontradas


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Confere o laudo já escrito contra as fotos e registra as divergências "
            "como pendências de validação."
        )
    )
    parser.add_argument("pasta_imovel", help="Caminho da pasta do imóvel (a mesma usada em main.py)")
    parser.add_argument("--comodos", nargs="+", help="Confere só estes cômodos (nome exato da pasta)")
    parser.add_argument("--notas", default="", help="As mesmas notas usadas na geração do laudo")
    args = parser.parse_args()

    todos = listar_pastas_comodo(args.pasta_imovel)
    nomes = todos
    if args.comodos:
        desconhecidos = [nome for nome in args.comodos if nome not in todos]
        if desconhecidos:
            print("Não encontrei a(s) pasta(s): " + ", ".join(desconhecidos))
            print("Cômodos desta pasta: " + ", ".join(todos))
            return
        nomes = args.comodos

    novas = conferir_imovel(args.pasta_imovel, nomes, args.notas)
    if not novas:
        print("\nConferência sem divergências.")
        return

    caminho = salvar_pendencias(args.pasta_imovel, ler_pendencias(args.pasta_imovel) + novas)
    faltando = sum(1 for pendencia in novas if pendencia.get("tipo") == "falta")
    print(
        f"\n{len(novas)} divergência(s) — {faltando} item(ns) que a foto mostra e o laudo "
        f"não tem.\nConfira e decida em: {caminho}"
    )
    print(f'Depois rode:  python validar.py "{args.pasta_imovel}"')


if __name__ == "__main__":
    main()
