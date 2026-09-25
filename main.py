"""
Ponto de entrada: percorre a pasta do imóvel (uma subpasta por cômodo),
processa cada cômodo com a API do Gemini e gera:
  - um .txt de laudo dentro de cada pasta de cômodo
  - um .txt consolidado com o imóvel inteiro, na raiz da pasta do imóvel

Uso:
    python main.py "C:\\caminho\\para\\o\\imovel"
"""

import argparse
import json
import os

from config import LIMIAR_CERTEZA, ROTULOS_CATEGORIA, USAR_MOTOR_DE_EVIDENCIAS
from gemini_client import criar_cliente
from core.pipeline import conflitos_para_pendencias, processar_comodo
from report_writer import parsear_txt_comodo, salvar_txt_comodo, salvar_relatorio_completo
from validacao import ler_pendencias, salvar_pendencias

# Onde o grafo de evidências de um cômodo fica gravado, ao lado do laudo.
# O .txt do laudo NÃO muda de formato (regra 33 do pedido); este arquivo é o
# rastro — foto -> evidência -> item — para auditoria e para a importação da
# vistoria no sistema web.
NOME_ARQUIVO_EVIDENCIAS = "_evidencias.json"


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
    # Os dois motores convivem de propósito, até o vistoriador rodar os dois
    # no mesmo imóvel e comparar — ver core/pipeline.py.
    motor = parser.add_mutually_exclusive_group()
    motor.add_argument(
        "--evidencias",
        action="store_true",
        help=(
            "Usa o motor de EVIDÊNCIAS: cada foto é primeiro classificada "
            "(é deste cômodo? é reflexo? mostra ambiente vizinho?) e só o que "
            "passa na validação de escopo vira texto do laudo. Evita que uma "
            "parede de outro cômodo, vista pela porta, entre como parede "
            "deste. Custa um prompt a mais por lote de 10 fotos."
        ),
    )
    motor.add_argument(
        "--classico",
        action="store_true",
        help="Força o motor antigo (1 chamada por cômodo, fotos direto para o laudo).",
    )
    motor.add_argument(
        "--evidencias-v1",
        action="store_true",
        help=(
            "Motor de evidências da primeira geração, mantido para comparação "
            "(sem taxonomia canônica, sem elementos de fronteira e sem "
            "checklist de cobertura)."
        ),
    )
    parser.add_argument(
        "--sem-conferencia",
        action="store_true",
        help=(
            "Não roda a conferência das fotos contra o laudo no fim (ver "
            "conferir.py). Só use se precisar economizar a chamada extra — "
            "é ela que pega item que ficou de fora do laudo."
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

    from core.pipeline import MOTOR_CLASSICO, MOTOR_V1, MOTOR_V2

    if args.classico:
        motor_escolhido = MOTOR_CLASSICO
    elif args.evidencias_v1:
        motor_escolhido = MOTOR_V1
    elif args.evidencias or USAR_MOTOR_DE_EVIDENCIAS:
        motor_escolhido = MOTOR_V2
    else:
        motor_escolhido = MOTOR_CLASSICO
    usar_evidencias = motor_escolhido != MOTOR_CLASSICO
    print("Motor: " + {
        MOTOR_CLASSICO: "clássico (1 chamada por cômodo)",
        MOTOR_V1: "evidências v1 (escopo por foto)",
        MOTOR_V2: "evidências v2 (escopo, fronteira, taxonomia e cobertura)",
    }[motor_escolhido], flush=True)

    cliente = criar_cliente()

    # Pendências já existentes de cômodos que NÃO forem reprocessados
    # continuam valendo — o laudo deles não muda.
    iniciais = ler_pendencias(args.pasta_imovel)
    processados, pendencias, falhas = set(), [], []
    caminho_pendencias = None
    for nome_comodo in nomes_comodo:
        pasta_comodo = os.path.join(args.pasta_imovel, nome_comodo)
        print(f"Lendo fotos de: {nome_comodo}...", flush=True)
        try:
            resultado = processar_comodo(
                cliente, pasta_comodo, nome_comodo, args.notas,
                usar_evidencias=usar_evidencias, motor=motor_escolhido,
                progresso=lambda texto: print(f"  {texto}", flush=True),
            )
        except Exception as erro:
            # Um cômodo problemático não deve derrubar o laudo inteiro dos
            # outros — registra a falha e segue para o próximo cômodo.
            print(f"  ERRO ao processar '{nome_comodo}': {erro}", flush=True)
            falhas.append(nome_comodo)
            continue
        dados, incertos = resultado.dados, resultado.incertos
        if not dados:
            print(f"  Nenhuma foto encontrada em {pasta_comodo}, pulando.", flush=True)
            continue
        caminho_txt = salvar_txt_comodo(pasta_comodo, nome_comodo, dados)
        print(f"  Salvo: {caminho_txt}", flush=True)
        if incertos:
            print(f"  {len(incertos)} item(ns) com certeza abaixo de {LIMIAR_CERTEZA}%", flush=True)

        # Rastro de evidências ao lado do laudo, quando o motor novo rodou.
        if resultado.evidencias:
            caminho_evidencias = os.path.join(pasta_comodo, NOME_ARQUIVO_EVIDENCIAS)
            with open(caminho_evidencias, "w", encoding="utf-8") as arquivo:
                json.dump(resultado.para_dict(), arquivo, ensure_ascii=False, indent=2)
            descartadas = len(resultado.evidencias) - len(resultado.evidencias_aceitas())
            print(f"  Evidências: {len(resultado.evidencias_aceitas())} aceita(s), "
                  f"{descartadas} descartada(s) — {caminho_evidencias}", flush=True)

        processados.add(nome_comodo)
        pendencias.extend(dict(item, comodo=nome_comodo) for item in incertos)
        # Conflito de escopo NÃO entra no laudo: vira pendência para o
        # vistoriador decidir olhando a foto (regras 18 e 19 do pedido).
        if resultado.conflitos:
            conflitos = conflitos_para_pendencias(nome_comodo, resultado.conflitos)
            pendencias.extend(conflitos)
            print(f"  {len(conflitos)} conflito(s) de escopo para você decidir", flush=True)
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

        # Conferência: com o texto pronto, o modelo olha as fotos de novo e
        # aponta o que ficou de fora ou não bate. Roda por padrão porque a
        # primeira leitura, sozinha, já deixou passar chuveiro, armário e
        # varal inteiros (R. Correia de Freitas, 22/09/2026). Custa cerca de
        # 1/4 da geração, graças aos mosaicos — ver conferir.py.
        if not args.sem_conferencia:
            # Import aqui dentro de propósito: conferir.py importa
            # listar_pastas_comodo deste módulo, e no topo os dois se
            # importariam em círculo.
            from conferir import conferir_imovel

            print(f"\nConferindo o laudo contra as fotos ({len(processados)} cômodo(s))...")
            pendencias.extend(
                conferir_imovel(
                    args.pasta_imovel,
                    [nome for nome in todos if nome in processados],
                    args.notas,
                )
            )

        anteriores = [p for p in iniciais if p.get("comodo") not in processados]
        caminho_pendencias = salvar_pendencias(args.pasta_imovel, anteriores + pendencias)
        _avisar_pendencias(anteriores + pendencias, caminho_pendencias, args.pasta_imovel)

    if falhas:
        comodos = " ".join(f'"{nome}"' for nome in falhas)
        print(f"\nCômodos que falharam: {', '.join(falhas)}")
        print(f'Para rodar só eles:  python main.py "{args.pasta_imovel}" --comodos {comodos}')


if __name__ == "__main__":
    main()
