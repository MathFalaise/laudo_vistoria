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

from config import LIMIAR_CERTEZA, ROTULOS_CATEGORIA
from gemini_client import criar_cliente
from room_processor import processar_comodo
from report_writer import parsear_txt_comodo, salvar_txt_comodo, salvar_relatorio_completo
from validacao import ler_pendencias, salvar_pendencias


def listar_pastas_comodo(pasta_imovel: str) -> list:
    return sorted(
        nome
        for nome in os.listdir(pasta_imovel)
        if os.path.isdir(os.path.join(pasta_imovel, nome))
    )


def _avisar_pendencias(pendencias: list, caminho_pendencias: str, pasta_imovel: str) -> None:
    if not pendencias:
        print(f"\nNenhum item abaixo de {LIMIAR_CERTEZA}% de certeza.")
        return
    print(
        f"\nATENÇÃO: {len(pendencias)} item(ns) com certeza abaixo de "
        f"{LIMIAR_CERTEZA}% — já estão no laudo, confira antes de entregar:"
    )
    for pendencia in pendencias:
        rotulo = ROTULOS_CATEGORIA.get(pendencia["categoria"], pendencia["categoria"])
        print(f"  - {pendencia['comodo']} / {rotulo} ({pendencia['certeza']}%): {pendencia['motivo']}")
    print(f"Preencha as decisões em: {caminho_pendencias}")
    print(f'Depois rode:  python validar.py "{pasta_imovel}"')


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
    parser.add_argument(
        "--comodos",
        nargs="+",
        metavar="NOME",
        help=(
            "Processa só estes cômodos (nomes exatos das subpastas), ex.: "
            '--comodos "Quarto 01" "Sala". Os demais mantêm o laudo e as '
            "pendências que já têm."
        ),
    )
    args = parser.parse_args()

    todos = listar_pastas_comodo(args.pasta_imovel)
    if not todos:
        print("Nenhuma subpasta de cômodo encontrada dentro da pasta informada.")
        return
    nomes_comodo = todos
    if args.comodos:
        desconhecidos = [nome for nome in args.comodos if nome not in todos]
        if desconhecidos:
            print(f"Cômodo(s) não encontrado(s): {', '.join(desconhecidos)}")
            print(f"Cômodos desta pasta: {', '.join(todos)}")
            return
        nomes_comodo = [nome for nome in todos if nome in args.comodos]

    cliente = criar_cliente()

    # Pendências já existentes de cômodos que NÃO forem reprocessados
    # continuam valendo — o laudo deles não muda.
    iniciais = ler_pendencias(args.pasta_imovel)
    processados, pendencias, falhas = set(), [], []
    caminho_pendencias = None
    for nome_comodo in nomes_comodo:
        pasta_comodo = os.path.join(args.pasta_imovel, nome_comodo)
        try:
            dados, incertos = processar_comodo(cliente, pasta_comodo, nome_comodo, args.notas)
        except Exception as erro:
            # Um cômodo problemático não deve derrubar o laudo inteiro dos
            # outros — registra a falha e segue para o próximo cômodo.
            print(f"  ERRO ao processar '{nome_comodo}': {erro}", flush=True)
            falhas.append(nome_comodo)
            continue
        if not dados:
            continue
        caminho_txt = salvar_txt_comodo(pasta_comodo, nome_comodo, dados)
        print(f"  Salvo: {caminho_txt}", flush=True)
        if incertos:
            print(f"  {len(incertos)} item(ns) com certeza abaixo de {LIMIAR_CERTEZA}%", flush=True)
        processados.add(nome_comodo)
        pendencias.extend(dict(item, comodo=nome_comodo) for item in incertos)
        # Grava a cada cômodo, não só no fim: se o processo cair ou for
        # interrompido no meio, as pendências já feitas não se perdem.
        anteriores = [p for p in iniciais if p.get("comodo") not in processados]
        caminho_pendencias = salvar_pendencias(args.pasta_imovel, anteriores + pendencias)

    if processados:
        # O consolidado sai de TODOS os cômodos com laudo no disco — inclusive
        # os que não foram reprocessados agora (--comodos, ou que falharam).
        resultados = {}
        for nome_comodo in todos:
            caminho_txt = os.path.join(args.pasta_imovel, nome_comodo, f"{nome_comodo}_vistoria.txt")
            if os.path.isfile(caminho_txt):
                resultados[nome_comodo] = parsear_txt_comodo(caminho_txt)
        caminho_completo = salvar_relatorio_completo(args.pasta_imovel, resultados)
        print(f"\nLaudo completo salvo em: {caminho_completo}")

        anteriores = [p for p in iniciais if p.get("comodo") not in processados]
        _avisar_pendencias(anteriores + pendencias, caminho_pendencias, args.pasta_imovel)

    if falhas:
        comodos = " ".join(f'"{nome}"' for nome in falhas)
        print(f"\nCômodos que falharam: {', '.join(falhas)}")
        print(f'Para rodar só eles:  python main.py "{args.pasta_imovel}" --comodos {comodos}')


if __name__ == "__main__":
    main()
