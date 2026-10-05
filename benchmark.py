"""
BENCHMARK A/B — roda dois motores nas MESMAS fotos e mostra a diferença.

Existe porque "o motor novo parece melhor" não é conclusão: no teste real de
24/09/2026 a V1 acertou mais fatos que o clássico e ainda assim entregou um
laudo pior, porque perdeu itens pequenos. Sem medir os dois lados, a troca
seria feita no escuro.

Uso:
    python benchmark.py "C:\\caminho\\do\\imovel" --motores classico evidencias_v2
    python benchmark.py "C:\\caminho" --comodos "Cozinha" --salvar-em resultados/

O que ele registra, por cômodo e por categoria (pedido, item 41):
    added    linha que só o motor B tem
    removed  linha que só o motor A tem
    changed  linha equivalente, escrita de forma diferente
    conflict pendência que um gerou e o outro não

Nada aqui altera laudo nem pendência do imóvel: o benchmark escreve só no
diretório de saída.
"""

import argparse
import difflib
import json
import os
import re
import unicodedata
from datetime import datetime

from core.config import CATEGORIAS, ROTULOS_CATEGORIA
from core.gemini_client import criar_cliente
from core.pipeline import MOTOR_CLASSICO, MOTOR_V1, MOTOR_V2, MOTORES, processar_comodo
from main import listar_pastas_comodo

# Duas linhas "iguais o bastante" para serem consideradas o mesmo item escrito
# de outro jeito, em vez de um item novo e um item perdido.
LIMIAR_SEMELHANCA = 0.62


def _chave(linha: str) -> str:
    texto = unicodedata.normalize("NFKD", linha.lower())
    texto = texto.encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z]+", texto))


def _parear(linhas_a: list, linhas_b: list) -> dict:
    """Casa as linhas dos dois laudos pela semelhança do texto.

    Sem isso, "Uma porta em madeira na cor marrom" e "Uma porta em madeira na
    cor escura" apareceriam como um item removido mais um item novo, quando
    são a mesma porta descrita de outro jeito."""
    restantes = list(enumerate(linhas_b))
    iguais, mudadas, removidas = [], [], []

    for linha_a in linhas_a:
        chave_a = _chave(linha_a)
        melhor, melhor_nota = None, 0.0
        for posicao, (indice, linha_b) in enumerate(restantes):
            nota = difflib.SequenceMatcher(None, chave_a, _chave(linha_b)).ratio()
            if nota > melhor_nota:
                melhor, melhor_nota = posicao, nota
        if melhor is None or melhor_nota < LIMIAR_SEMELHANCA:
            removidas.append(linha_a)
            continue
        _, linha_b = restantes.pop(melhor)
        if _chave(linha_a) == _chave(linha_b):
            iguais.append(linha_a)
        else:
            mudadas.append({"a": linha_a, "b": linha_b, "semelhanca": round(melhor_nota, 2)})

    return {
        "iguais": iguais,
        "mudadas": mudadas,
        "removidas": removidas,
        "acrescentadas": [linha for _, linha in restantes],
    }


def comparar_comodo(resultado_a, resultado_b) -> dict:
    """Diferença entre dois processamentos do MESMO cômodo."""
    por_categoria = {}
    for categoria in CATEGORIAS:
        linhas_a = [l for l in (resultado_a.dados.get(categoria) or "").split("\n")
                    if l.strip().startswith("*")]
        linhas_b = [l for l in (resultado_b.dados.get(categoria) or "").split("\n")
                    if l.strip().startswith("*")]
        if not linhas_a and not linhas_b:
            continue
        diferenca = _parear(linhas_a, linhas_b)
        if diferenca["mudadas"] or diferenca["removidas"] or diferenca["acrescentadas"]:
            por_categoria[ROTULOS_CATEGORIA[categoria]] = diferenca

    return {
        "categorias": por_categoria,
        "itens_a": sum(1 for c in CATEGORIAS
                       for l in (resultado_a.dados.get(c) or "").split("\n")
                       if l.strip().startswith("*")),
        "itens_b": sum(1 for c in CATEGORIAS
                       for l in (resultado_b.dados.get(c) or "").split("\n")
                       if l.strip().startswith("*")),
        "pendencias_a": len(resultado_a.incertos) + len(resultado_a.conflitos),
        "pendencias_b": len(resultado_b.incertos) + len(resultado_b.conflitos),
        "evidencias_a": len(resultado_a.evidencias),
        "evidencias_b": len(resultado_b.evidencias),
        "fronteiras_recuperadas_b": sum(
            1 for e in resultado_b.evidencias if e.escopo_original is not None
        ),
    }


def rodar(pasta_imovel: str, nomes_comodo: list, motores: list,
          notas: str = "") -> dict:
    """Processa cada cômodo com cada motor e devolve o relatório."""
    cliente = criar_cliente()
    por_comodo = {}

    for nome in nomes_comodo:
        pasta_comodo = os.path.join(pasta_imovel, nome)
        resultados = {}
        for motor in motores:
            print(f"  [{motor}] {nome}...", flush=True)
            try:
                resultados[motor] = processar_comodo(
                    cliente, pasta_comodo, nome, notas, motor=motor,
                    progresso=lambda t: print(f"      {t}", flush=True),
                )
            except Exception as erro:
                print(f"      ERRO: {erro.__class__.__name__}: {erro}", flush=True)
                resultados[motor] = None

        if any(r is None for r in resultados.values()):
            por_comodo[nome] = {"erro": "algum motor falhou neste cômodo"}
            continue

        a, b = motores[0], motores[1]
        por_comodo[nome] = {
            "comparacao": comparar_comodo(resultados[a], resultados[b]),
            "laudo": {
                motor: {c: resultados[motor].dados.get(c, "") for c in CATEGORIAS}
                for motor in motores
            },
            "pendencias": {
                motor: (
                    [{"categoria": p.get("categoria"), "certeza": p.get("certeza"),
                      "motivo": p.get("motivo"), "texto": p.get("texto")}
                     for p in resultados[motor].incertos]
                    + [{"categoria": c.categoria, "tipo": c.tipo.value,
                        "motivo": c.resumo} for c in resultados[motor].conflitos]
                )
                for motor in motores
            },
        }

    return {
        "imovel": os.path.basename(os.path.normpath(pasta_imovel)),
        "quando": datetime.now().isoformat(timespec="seconds"),
        "motores": motores,
        "comodos": por_comodo,
    }


def imprimir(relatorio: dict) -> None:
    a, b = relatorio["motores"]
    print(f"\n{'=' * 72}")
    print(f"BENCHMARK  {a}  x  {b}")
    print(f"Imóvel: {relatorio['imovel']}")
    print("=" * 72)

    total = {"removidas": 0, "acrescentadas": 0, "mudadas": 0}
    for nome, dados in relatorio["comodos"].items():
        if "erro" in dados:
            print(f"\n## {nome}: {dados['erro']}")
            continue
        comparacao = dados["comparacao"]
        print(f"\n## {nome}")
        print(f"   itens: {comparacao['itens_a']} ({a})  ->  "
              f"{comparacao['itens_b']} ({b})")
        print(f"   pendências: {comparacao['pendencias_a']}  ->  "
              f"{comparacao['pendencias_b']}")
        if comparacao["evidencias_b"]:
            print(f"   evidências ({b}): {comparacao['evidencias_b']}"
                  f"  |  recuperadas como estrutura do cômodo: "
                  f"{comparacao['fronteiras_recuperadas_b']}")

        for rotulo, diferenca in comparacao["categorias"].items():
            print(f"\n   {rotulo}:")
            for linha in diferenca["removidas"]:
                total["removidas"] += 1
                print(f"     - só em {a}: {linha}")
            for linha in diferenca["acrescentadas"]:
                total["acrescentadas"] += 1
                print(f"     + só em {b}: {linha}")
            for mudanca in diferenca["mudadas"]:
                total["mudadas"] += 1
                print(f"     ~ {a}: {mudanca['a']}")
                print(f"       {b}: {mudanca['b']}")

    print(f"\n{'=' * 72}")
    print(f"TOTAL — só em {a}: {total['removidas']}  |  "
          f"só em {b}: {total['acrescentadas']}  |  "
          f"reescritas: {total['mudadas']}")
    print("Nenhum dos dois é 'certo' por contagem: confira cada divergência "
          "nas fotos.")
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(
        description="Roda dois motores nas mesmas fotos e compara os laudos."
    )
    parser.add_argument("pasta_imovel")
    parser.add_argument("--motores", nargs=2, default=[MOTOR_CLASSICO, MOTOR_V2],
                        choices=MOTORES,
                        help=f"dois motores para comparar (padrão: {MOTOR_CLASSICO} {MOTOR_V2})")
    parser.add_argument("--comodos", nargs="+", help="só estes cômodos")
    parser.add_argument("--notas", default="", help="as mesmas notas nos dois motores")
    parser.add_argument("--salvar-em", default="",
                        help="diretório onde gravar o relatório .json")
    args = parser.parse_args()

    todos = listar_pastas_comodo(args.pasta_imovel)
    nomes = [n for n in todos if not args.comodos or n in args.comodos]
    if not nomes:
        print("Nenhum cômodo para processar.")
        return

    print(f"Comparando {args.motores[0]} x {args.motores[1]} em {len(nomes)} cômodo(s).")
    print("As fotos são as mesmas nos dois — o custo é de duas passagens.\n")

    relatorio = rodar(args.pasta_imovel, nomes, args.motores, args.notas)
    imprimir(relatorio)

    if args.salvar_em:
        os.makedirs(args.salvar_em, exist_ok=True)
        caminho = os.path.join(
            args.salvar_em,
            f"benchmark-{args.motores[0]}-x-{args.motores[1]}-"
            f"{datetime.now():%Y%m%d-%H%M%S}.json",
        )
        with open(caminho, "w", encoding="utf-8") as arquivo:
            json.dump(relatorio, arquivo, ensure_ascii=False, indent=2)
        print(f"\nRelatório salvo em: {caminho}")


if __name__ == "__main__":
    main()
