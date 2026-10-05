"""
BENCHMARK A/B — roda dois motores nas MESMAS fotos e mostra a diferença.

Existe porque "o motor novo parece melhor" não é conclusão: no teste real de
24/09/2026 a V1 acertou mais fatos que o clássico e ainda assim entregou um
laudo pior, porque perdeu itens pequenos. Sem medir os dois lados, a troca
seria feita no escuro.

Uso:
    python benchmark.py "C:\\caminho\\do\\imovel" --motores classico evidencias_v2
    python benchmark.py "C:\\caminho" --comodos "Cozinha" --salvar-em resultados/
    python benchmark.py "C:\\caminho" --provedores gemini glm glm+claude

`--provedores` compara PROVEDORES no motor V2 (o único com validação visual):
cada configuração é "analista" ou "analista+validador", e todas recebem as
MESMAS fotos. Mede, por configuração: evidências (aceitas, descartadas),
conflitos, pendências, itens do laudo, tempo, chamadas, tokens, custo,
reanálises e decisões do validador; e compara o laudo de cada uma com o da
primeira, linha a linha. Custa uma passagem completa por configuração.

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
import time
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


# ==========================================================================
# Provedores: Gemini x GLM x GLM+Claude (desde 05/10/2026)
# ==========================================================================

def configuracao(texto: str) -> tuple:
    """"glm+claude" -> ("glm", "claude"); "gemini" -> ("gemini", None)."""
    from core.providers import PROVEDORES

    partes = [parte.strip().lower() for parte in texto.split("+")]
    if len(partes) > 2 or any(parte not in PROVEDORES for parte in partes):
        raise argparse.ArgumentTypeError(
            f"configuração inválida: {texto!r} (use analista ou analista+validador, "
            f"com provedores de {PROVEDORES})")
    return partes[0], (partes[1] if len(partes) == 2 else None)


def _linhas_do_laudo(resultado) -> int:
    return sum(1 for c in CATEGORIAS for l in (resultado.dados.get(c) or "").split("\n")
               if l.strip().startswith("*"))


def medir(resultado, segundos: float) -> dict:
    """Números de UMA passagem — nada de avaliação subjetiva."""
    from core import telemetria

    chamadas = resultado.chamadas
    custos = [c.get("custo_usd") for c in chamadas]
    validacao = resultado.validacao or {}
    return {
        "segundos": round(segundos, 1),
        "evidencias": len(resultado.evidencias),
        "aceitas": len(resultado.evidencias_aceitas()),
        "descartadas": len(resultado.evidencias) - len(resultado.evidencias_aceitas()),
        "conflitos": len(resultado.conflitos),
        "pendencias": len(resultado.incertos) + len(resultado.conflitos),
        "itens_do_laudo": _linhas_do_laudo(resultado),
        "chamadas": len(chamadas),
        "chamadas_com_falha": sum(1 for c in chamadas if not c["sucesso"]),
        "tokens_entrada": sum(c.get("tokens_entrada") or 0 for c in chamadas),
        "tokens_saida": sum(c.get("tokens_saida") or 0 for c in chamadas),
        "custo_usd": (None if any(c is None for c in custos) else round(sum(custos), 6)),
        "reanalises": validacao.get("chamadas_reanalise", 0),
        "validacao": validacao or None,
        "por_modelo": telemetria.resumir(chamadas),
    }


def _somar(totais: dict, medida: dict) -> None:
    for chave in ("segundos", "evidencias", "aceitas", "descartadas", "conflitos", "pendencias",
                  "itens_do_laudo", "chamadas", "chamadas_com_falha", "tokens_entrada",
                  "tokens_saida", "reanalises"):
        totais[chave] = round(totais.get(chave, 0) + medida[chave], 1)
    if "custo_usd" not in totais:
        totais["custo_usd"] = 0.0
    if totais["custo_usd"] is not None:
        totais["custo_usd"] = (None if medida["custo_usd"] is None
                               else round(totais["custo_usd"] + medida["custo_usd"], 6))


def rodar_provedores(pasta_imovel: str, nomes_comodo: list, configuracoes: list,
                     notas: str = "", fabrica=None) -> dict:
    """Processa cada cômodo com cada configuração, no motor V2.

    `fabrica(nome) -> Provedor` existe para os testes; o padrão cria o
    provedor real pelo ambiente (chaves e modelos do .env)."""
    from core.providers import criar_provedor

    fabrica = fabrica or criar_provedor
    rotulos = ["+".join(p for p in par if p) for par in configuracoes]
    provedores = {rotulo: (fabrica(visao), fabrica(validador) if validador else None)
                  for rotulo, (visao, validador) in zip(rotulos, configuracoes)}
    por_comodo, totais = {}, {rotulo: {} for rotulo in rotulos}

    for nome in nomes_comodo:
        pasta_comodo = os.path.join(pasta_imovel, nome)
        resultados, medidas = {}, {}
        for rotulo in rotulos:
            analista, validador = provedores[rotulo]
            print(f"  [{rotulo}] {nome}...", flush=True)
            inicio = time.monotonic()
            try:
                resultado = processar_comodo(
                    analista, pasta_comodo, nome, notas, motor=MOTOR_V2, validador=validador,
                    progresso=lambda t: print(f"      {t}", flush=True),
                )
            except Exception as erro:
                print(f"      ERRO: {erro.__class__.__name__}: {erro}", flush=True)
                medidas[rotulo] = {"erro": erro.__class__.__name__}
                continue
            resultados[rotulo] = resultado
            medidas[rotulo] = medir(resultado, time.monotonic() - inicio)
            _somar(totais[rotulo], medidas[rotulo])

        base = rotulos[0]
        por_comodo[nome] = {
            "medidas": medidas,
            "comparacao_com_" + base: {
                rotulo: comparar_comodo(resultados[base], resultados[rotulo])
                for rotulo in rotulos[1:] if base in resultados and rotulo in resultados
            },
            "laudo": {rotulo: {c: r.dados.get(c, "") for c in CATEGORIAS}
                      for rotulo, r in resultados.items()},
        }

    return {
        "imovel": os.path.basename(os.path.normpath(pasta_imovel)),
        "quando": datetime.now().isoformat(timespec="seconds"),
        "motor": MOTOR_V2,
        "configuracoes": rotulos,
        "totais": totais,
        "comodos": por_comodo,
    }


def imprimir_provedores(relatorio: dict) -> None:
    rotulos = relatorio["configuracoes"]
    print(f"\n{'=' * 72}")
    print(f"BENCHMARK DE PROVEDORES (motor {relatorio['motor']}): {' x '.join(rotulos)}")
    print(f"Imóvel: {relatorio['imovel']}")
    print("=" * 72)
    colunas = ("itens_do_laudo", "aceitas", "descartadas", "pendencias", "chamadas",
               "reanalises", "segundos", "custo_usd")
    print(f"{'configuração':<22}" + "".join(f"{c:>15}" for c in colunas))
    for rotulo in rotulos:
        totais = relatorio["totais"].get(rotulo) or {}
        valores = []
        for coluna in colunas:
            valor = totais.get(coluna)
            valores.append("?" if valor is None else (f"{valor:.4f}" if coluna == "custo_usd" else str(valor)))
        print(f"{rotulo:<22}" + "".join(f"{v:>15}" for v in valores))
    base = rotulos[0]
    for nome, dados in relatorio["comodos"].items():
        for rotulo, comparacao in dados.get("comparacao_com_" + base, {}).items():
            mudancas = sum(len(d["removidas"]) + len(d["acrescentadas"]) + len(d["mudadas"])
                           for d in comparacao["categorias"].values())
            print(f"  {nome}: {rotulo} x {base} — {mudancas} linha(s) diferente(s) no laudo")
    print("Custo '?' = há chamada de modelo sem preço registrado "
          "(core/config.PRECOS_POR_MILHAO ou LAUDO_PRECOS_MODELOS).")
    print("Nenhuma configuração é 'certa' por contagem: confira as diferenças nas fotos.")
    print("=" * 72)


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
    parser.add_argument("--provedores", nargs="+", type=configuracao, metavar="CONFIG",
                        help=("compara provedores no motor V2, ex.: gemini glm glm+claude "
                              "(analista ou analista+validador); ignora --motores"))
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

    if args.provedores:
        if len(args.provedores) < 2:
            parser.error("--provedores precisa de pelo menos duas configurações")
        relatorio = rodar_provedores(args.pasta_imovel, nomes, args.provedores, args.notas)
        imprimir_provedores(relatorio)
        if args.salvar_em:
            os.makedirs(args.salvar_em, exist_ok=True)
            caminho = os.path.join(args.salvar_em, "benchmark-provedores-"
                                   f"{'-x-'.join(relatorio['configuracoes'])}-"
                                   f"{datetime.now():%Y%m%d-%H%M%S}.json")
            with open(caminho, "w", encoding="utf-8") as arquivo:
                json.dump(relatorio, arquivo, ensure_ascii=False, indent=2)
            print(f"\nRelatório salvo em: {caminho}")
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
