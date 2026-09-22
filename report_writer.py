"""
Grava os resultados de cada cômodo em arquivo .txt (um por cômodo, salvo
dentro da própria pasta de fotos) e monta um relatório único consolidado
com o imóvel inteiro.
"""

import os
import re
import unicodedata

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


# Linha no formato proibido "*Mais um/uma/dois..." — item repetido tem que
# virar uma linha só com a quantidade total (ver "ITENS REPETIDOS" em
# style_guide.REGRAS_GERAIS).
_MAIS_UM = re.compile(
    r"^\*\s*mais\s+(um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|\d+)\b",
    re.IGNORECASE,
)


def linha_com_mais_um(linha: str) -> bool:
    return bool(_MAIS_UM.match(linha))


# Linha que começa com quantidade + o item: "*Um armário...", "*Três placas...",
# "*Mais um armário...". O grupo 2 é o item.
_QUANTIDADE_E_ITEM = re.compile(
    r"^\*\s*(?:mais\s+)?(?:um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove"
    r"|dez|onze|doze|\d+)\s+(\S+)",
    re.IGNORECASE,
)


def _item_no_singular(palavra: str) -> str:
    """"Armários" -> "armario", "placas" -> "placa", "painéis" -> "painel".
    Aproximado, mas suficiente para comparar o item de duas linhas."""
    palavra = unicodedata.normalize("NFKD", palavra.strip(",.;:").lower())
    palavra = palavra.encode("ascii", "ignore").decode()
    for plural, singular in (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el")):
        if palavra.endswith(plural):
            return palavra[: -len(plural)] + singular
    return palavra[:-1] if palavra.endswith("s") else palavra


def grupos_de_itens_repetidos(linhas: list) -> list:
    """Índices de linhas que descrevem o MESMO tipo de item em linhas
    separadas — "*Um armário inferior..." e "*Um armário superior...",
    "*Duas placas..." e "*Uma placa..." — em grupos de 2 ou mais. Pela regra
    ITENS REPETIDOS, cada grupo devia ser uma linha só. Linhas que não
    começam com quantidade ("*Paredes em...", "*Piso em...") ficam de fora."""
    por_item = {}
    for indice, linha in enumerate(linhas):
        encontrado = _QUANTIDADE_E_ITEM.match(linha)
        if encontrado:
            por_item.setdefault(_item_no_singular(encontrado.group(1)), []).append(indice)
    return [indices for indices in por_item.values() if len(indices) > 1]


# "testado e em funcionamento" (e suas flexões), com a vírgula que o
# antecede. Ver a regra TESTES em style_guide.REGRAS_GERAIS.
_FRASE_TESTE = re.compile(
    r"\s*,?\s*testad[oa]s?\s+e\s+em\s+funcionamento\s*,?", re.IGNORECASE
)

# Categorias em que NADA é testado: parede, piso, teto, porta e janela não
# passam por teste elétrico nem hidráulico.
_CATEGORIAS_SEM_TESTE = ("paredes", "piso", "teto", "porta", "janela", "obs")

# Em Mobília, só a peça elétrica ou hidráulica é testada; armário, bancada,
# espelho, box e acessório, não.
# "tanque", "bancada", "cuba" e "pia" ficaram DE FORA de propósito: elas só
# recebem água, quem é testado é a torneira/registro que está na mesma linha
# (regra do vistoriador, 22/09/2026).
_ITENS_TESTAVEIS = (
    "torneira", "misturador", "chuveiro", "ducha", "registro", "descarga",
    "caixa acoplada", "válvula", "aquecedor", "bidê", "filtro",
    "interfone", "campainha", "ventilador", "exaustor", "depurador",
    "cooktop", "coifa", "forno", "aquecimento",
)


def limpar_testes_indevidos(categoria: str, texto: str) -> str:
    """Tira "testado e em funcionamento" de onde a regra TESTES não permite.

    O modelo, ao receber nas notas que todos os testes foram feitos, tende a
    espalhar a frase por tudo — houve laudo com "paredes testadas e em
    funcionamento" e "espelho testado e em funcionamento". A regra no prompt
    sozinha não segurou, então a limpeza é feita também aqui, no texto
    pronto: determinística e de graça."""
    linhas = []
    for linha in texto.split("\n"):
        testavel = categoria not in _CATEGORIAS_SEM_TESTE and (
            categoria != "mobilia"
            or any(item in linha.lower() for item in _ITENS_TESTAVEIS)
        )
        if not testavel and _FRASE_TESTE.search(linha):
            linha = normalizar_linha(_FRASE_TESTE.sub(", ", linha).replace(" ,", ","))
            linha = re.sub(r",\s*(,\s*)+", ", ", linha)
            linha = re.sub(r",\s*\.", ".", linha).replace(", ,", ",")
            # "..., em bom estado, testado e em funcionamento, em bom estado."
            # deixa o estado repetido depois que a frase sai.
            linha = re.sub(
                r",\s*em (bom|regular|ótimo|péssimo) estado\s*(?=,\s*em \1 estado\b)",
                "",
                linha,
                flags=re.IGNORECASE,
            )
        linhas.append(linha)
    return "\n".join(linhas)


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
