"""
TAXONOMIA — a camada determinística que corrige, por código, os erros que o
benchmark de 107 fotos expôs na V1.

Três perguntas são respondidas AQUI, e não no prompt:

1. **Isto é elemento de fronteira?** Soleira, batente, vistas, peitoril e
   esquadria ficam entre dois ambientes por definição. A V1 as descartou como
   "ambiente adjacente" — perdeu a soleira do BWC e a janela inteira do Quarto
   Suíte. Elemento de fronteira PERTENCE ao cômodo; o que se vê do outro lado
   da abertura, não.

2. **Em que categoria isto entra?** O modelo propõe, o código normaliza.
   Soleira vai para Porta mesmo dividindo dois pisos; peitoril vai para
   Janela; box vai para Mobília mesmo tendo folhas de correr. A V1 mandou o
   box para Porta e a soleira para Piso porque acreditou na categoria que o
   modelo escolheu.

3. **Isto é contradição de verdade?** "Cerâmica branca" e "rejunte cinza" não
   são versões concorrentes da mesma parede — são atributos diferentes. A V1
   abriu um conflito falso com isso. Só há contradição quando o MESMO atributo
   recebe valores incompatíveis.

Regra de ouro deste módulo (pedido, item 44): prompt orienta o modelo, código
protege o sistema. Nada aqui depende de o modelo ter obedecido a alguma
instrução.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum

from core.config import CATEGORIAS


def sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto).lower())
    return texto.encode("ascii", "ignore").decode()


def _palavras(texto: str) -> set:
    return set(re.findall(r"[a-z]+", sem_acento(texto)))


# ==========================================================================
# ESCOPO — onde a coisa está em relação ao cômodo alvo
# ==========================================================================

class Escopo(str, Enum):
    """Taxonomia de pertencimento (pedido, item 7).

    Substitui o booleano da V1. A diferença que importa é FRONTEIRA existir:
    sem ela, tudo que fica entre dois ambientes era empurrado para ADJACENTE,
    e o laudo perdia porta, janela, soleira e peitoril."""

    INTERIOR = "room_interior"       # dentro do cômodo
    FRONTEIRA = "room_boundary"      # estrutura DO cômodo, na divisa
    ADJACENTE = "adjacent_room"      # outro ambiente, visto daqui
    EXTERIOR = "outside"             # rua, quintal, vizinho
    REFLEXO = "reflection"           # imagem em espelho ou vidro
    AMBIGUO = "ambiguous"            # não deu para decidir


# Os dois únicos escopos que podem virar texto do laudo. AMBIGUO não entra:
# vira pendência, que é o lado seguro (item 45).
ESCOPOS_QUE_ALIMENTAM_O_LAUDO = (Escopo.INTERIOR, Escopo.FRONTEIRA)

_ESCOPO_POR_TEXTO = {
    "room_interior": Escopo.INTERIOR, "interior": Escopo.INTERIOR,
    "room_boundary": Escopo.FRONTEIRA, "boundary": Escopo.FRONTEIRA,
    "fronteira": Escopo.FRONTEIRA,
    "adjacent_room": Escopo.ADJACENTE, "adjacent": Escopo.ADJACENTE,
    "adjacente": Escopo.ADJACENTE,
    "outside": Escopo.EXTERIOR, "exterior": Escopo.EXTERIOR,
    "reflection": Escopo.REFLEXO, "reflexo": Escopo.REFLEXO,
    "ambiguous": Escopo.AMBIGUO, "ambiguo": Escopo.AMBIGUO,
}


def escopo_de_texto(valor, padrao: Escopo = Escopo.AMBIGUO) -> Escopo:
    """Lê o escopo que o modelo devolveu.

    Valor desconhecido cai em AMBIGUO, não em INTERIOR: quando o sistema não
    entendeu a resposta, a saída segura é pedir conferência humana."""
    return _ESCOPO_POR_TEXTO.get(sem_acento(valor).strip(), padrao)


# ==========================================================================
# ELEMENTOS DE FRONTEIRA (pedido, itens 8 a 11)
# ==========================================================================

# Estrutura que pertence ao cômodo mesmo estando na divisa com outro ambiente.
# Estar entre dois pisos, dar para a varanda ou mostrar o exterior NÃO tira
# a peça do cômodo.
TERMOS_DE_FRONTEIRA = {
    # conjunto da porta
    # "vista" no SINGULAR fica de fora de proposito: no laudo a guarnicao e
    # sempre "vistas", e o singular quase sempre e panorama ("vista da rua").
    "porta", "portas", "folha", "batente", "batentes", "vistas",
    "guarnicao", "guarnicoes", "alizar", "alizares", "soleira", "soleiras",
    "marco", "umbral",
    # conjunto da janela
    "janela", "janelas", "esquadria", "esquadrias", "caixilho", "caixilhos",
    "peitoril", "peitoris", "trilho", "trilhos", "veneziana", "basculante",
    "maximar", "persiana", "bandeira", "vidro", "vidros",
    # aberturas mistas
    "portajanela", "balcao", "portabalcao",
}

# "porta-janela" e afins perdem o hífen em _palavras(); estes cobrem a forma
# composta escrita separada.
_EXPRESSOES_DE_FRONTEIRA = (
    "porta janela", "porta-janela", "porta balcao", "porta-balcao",
    "porta de correr", "janela porta", "janela-porta", "janelaporta",
    "portajanela",
)


def e_elemento_de_fronteira(texto: str) -> bool:
    """A observação descreve uma estrutura de divisa do cômodo?

    Usado para IMPEDIR que o modelo rebaixe uma porta ou um peitoril a
    "ambiente adjacente" só porque a peça mostra o outro lado."""
    limpo = sem_acento(texto)
    if any(expressao in limpo for expressao in _EXPRESSOES_DE_FRONTEIRA):
        return True
    return bool(_palavras(texto) & TERMOS_DE_FRONTEIRA)


# O que está DO OUTRO LADO da abertura continua fora do escopo (item 10):
# a esquadria é do quarto, a vista da rua não é.
_TERMOS_DE_CENARIO = {
    "paisagem", "vizinho", "vizinha", "rua", "calcada", "ceu", "predio",
    "predios", "telhado", "telhados", "jardim", "gramado", "quintal",
    "arvore", "arvores", "piscina", "horizonte", "cidade",
}


def e_cenario_alem_da_abertura(texto: str) -> bool:
    """Descreve o que se vê ATRAVÉS da janela/porta, em vez da peça em si.

    Presença não basta para decidir: "telhado do vizinho visto pela janela"
    tem os dois vocabulários. O que decide é QUEM VEM PRIMEIRO, que na prática
    é o sujeito da frase:

    - "Telhado do vizinho e jardim vistos pela janela" -> cenário;
    - "Janela de correr em alumínio com vista para o jardim" -> a janela.

    Sem nenhum termo de cenário, não é cenário."""
    limpo = sem_acento(texto)
    palavras = _palavras(texto)
    if not (palavras & _TERMOS_DE_CENARIO):
        return False
    if not e_elemento_de_fronteira(texto):
        return True

    def primeira_posicao(vocabulario) -> int:
        posicoes = [
            achado.start()
            for termo in vocabulario
            for achado in re.finditer(r"\b" + re.escape(termo) + r"\b", limpo)
        ]
        return min(posicoes) if posicoes else len(limpo) + 1

    return primeira_posicao(_TERMOS_DE_CENARIO) < primeira_posicao(TERMOS_DE_FRONTEIRA)


# ==========================================================================
# CATEGORIA CANÔNICA (pedido, itens 24 e 25)
#
# O modelo propõe; isto decide. Os pares abaixo saíram de erros reais do
# benchmark, não de teoria.
# ==========================================================================

_TERMOS_POR_CATEGORIA = {
    "porta": (
        # A soleira é do conjunto da porta. Dividir dois pisos não a torna
        # piso (item 9) — foi o erro que tirou a soleira do BWC do laudo.
        "soleira", "soleiras", "batente", "batentes", "vista", "vistas",
        "guarnicao", "guarnicoes", "alizar", "alizares", "porta", "portas",
        "macaneta", "fechadura", "dobradica", "dobradicas", "trinco",
        "roseta", "espelho de fechadura", "chapa testa", "marco", "umbral",
    ),
    "janela": (
        # Peitoril é estrutura da janela (item 11). Porta-janela é janela
        # (item 10), mesmo dando para a varanda.
        "janela", "janelas", "peitoril", "peitoris", "esquadria", "esquadrias",
        "caixilho", "caixilhos", "basculante", "maximar", "veneziana",
        "persiana", "portajanela", "porta janela", "janela porta", "bandeira",
        "fecho", "trilho de janela",
    ),
    "piso": ("piso", "pisos", "rodape", "rodapes", "ralo", "soleira de ralo"),
    "teto": ("teto", "laje", "forro", "gesso", "rodateto", "sanca", "beiral"),
    "paredes": ("parede", "paredes", "azulejo", "azulejos", "revestimento",
                "rejunte", "textura", "pastilha", "pastilhas", "faixa decorativa"),
    "eletrico": (
        "tomada", "tomadas", "interruptor", "interruptores", "placa", "placas",
        "disjuntor", "disjuntores", "quadro", "luminaria", "plafon", "spot",
        "lampada", "ponto de luz", "iluminacao", "campainha", "interfone",
        "arcondicionado", "ar condicionado", "split", "ventilador", "exaustor",
        "antena", "rj", "internet", "coaxial", "fibra",
    ),
    "mobilia": (
        # Box é mobília mesmo tendo folhas e trilho (item 25) — a V1 mandou
        # para Porta. Os acessórios pequenos vêm aqui de propósito: foram o
        # que mais se perdeu no benchmark.
        "box", "bancada", "cuba", "pia", "gabinete", "armario", "armarios",
        "guardaroupa", "criadomudo", "criados", "gaveteiro", "prateleira",
        "nicho", "espelho", "bacia", "sanitaria", "vaso", "caixa acoplada",
        "assento", "tampa", "chuveiro", "ducha", "registro", "registros",
        "torneira", "sifao", "engate", "banheira", "tanque", "portapapel",
        "papeleira", "portatoalha", "toalheiro", "gancho", "ganchos",
        "cabideiro", "saboneteira", "portashampoo", "varal", "fogao",
        "geladeira", "refrigerador", "microondas", "coifa", "depurador",
        "cooktop", "forno", "painel", "mesa", "cadeira", "cama", "aquecedor",
    ),
}

# Categoria explícita vinda do modelo -> chave interna.
_APELIDOS_DE_CATEGORIA = {
    "parede": "paredes", "paredes": "paredes", "walls": "paredes",
    "piso": "piso", "pisos": "piso", "floor": "piso",
    "teto": "teto", "ceiling": "teto",
    "porta": "porta", "portas": "porta", "door": "porta",
    "janela": "janela", "janelas": "janela", "window": "janela",
    "eletrico": "eletrico", "eletricos": "eletrico",
    "componentes eletricos": "eletrico", "electrical": "eletrico",
    "mobilia": "mobilia", "mobiliario": "mobilia", "furniture": "mobilia",
    "obs": "obs", "observacoes": "obs", "observacao": "obs",
}

# Termos que mandam na categoria mesmo contra o que o modelo propôs. São os
# casos em que ele erra de forma sistemática — todos vistos no benchmark.
_TERMOS_DECISIVOS = {
    "soleira": "porta", "soleiras": "porta",
    "batente": "porta", "batentes": "porta",
    "vistas": "porta", "guarnicao": "porta", "alizar": "porta",
    "peitoril": "janela", "peitoris": "janela",
    "portajanela": "janela", "janelaporta": "janela",
    "esquadria": "janela", "caixilho": "janela",
    "box": "mobilia",
    "rodape": "piso", "rodapes": "piso",
    "portapapel": "mobilia", "papeleira": "mobilia",
    "portatoalha": "mobilia", "toalheiro": "mobilia",
    "gancho": "mobilia", "ganchos": "mobilia", "cabideiro": "mobilia",
    "saboneteira": "mobilia", "portashampoo": "mobilia",
    "bacia": "mobilia", "chuveiro": "mobilia", "ducha": "mobilia",
}


def _normalizar_composto(texto: str) -> str:
    """"porta-papel" e "porta papel" viram "portapapel", para casar com os
    dicionários sem precisar de uma entrada por grafia."""
    limpo = sem_acento(texto)
    for composto in ("janela porta", "janela-porta",
                     "porta papel", "porta-papel", "porta toalha", "porta-toalha",
                     "porta shampoo", "porta-shampoo", "porta janela",
                     "porta-janela", "guarda roupa", "guarda-roupa",
                     "criado mudo", "criado-mudo", "ar condicionado",
                     "ar-condicionado", "maxim ar", "maxim-ar", "rodo teto",
                     "roda-teto", "porta balcao", "porta-balcao"):
        limpo = limpo.replace(composto, composto.replace(" ", "").replace("-", ""))
    return limpo


def categoria_canonica(categoria_proposta: str, observacao: str = "") -> str:
    """A categoria em que o item REALMENTE entra.

    Ordem de decisão, da mais forte para a mais fraca:

    1. termo decisivo na observação (soleira, peitoril, box, rodapé...);
    2. categoria que o modelo propôs, se for uma das oito;
    3. palpite por vocabulário;
    4. "obs", que é o balde de quem não se encaixa.

    Devolve sempre uma das oito categorias de `config.CATEGORIAS`."""
    limpo = _normalizar_composto(observacao)
    palavras = set(re.findall(r"[a-z]+", limpo))

    for termo, categoria in _TERMOS_DECISIVOS.items():
        if termo in palavras or termo in limpo:
            return categoria

    proposta = _APELIDOS_DE_CATEGORIA.get(sem_acento(categoria_proposta).strip())
    if proposta in CATEGORIAS:
        return proposta

    for categoria, termos in _TERMOS_POR_CATEGORIA.items():
        if any(termo in palavras or termo in limpo for termo in termos):
            return categoria

    return "obs"


# ==========================================================================
# RODAPÉ (pedido, itens 26 e 27)
# ==========================================================================

class EstadoRodape(str, Enum):
    """Três estados, porque dois não bastam.

    No BWC do benchmark o azulejo desce até o piso: NÃO há rodapé. Os dois
    motores escreveram "com rodapé em cerâmica branca" porque "há uma junção
    entre parede e piso" foi lido como "há rodapé". E quando a junção não
    aparece em foto nenhuma, o sistema não pode afirmar nem uma coisa nem
    outra (item 26)."""

    PRESENTE = "baseboard_present"
    AUSENTE = "baseboard_absent"
    NAO_VISIVEL = "baseboard_not_visible"


_SEM_RODAPE = (
    "sem rodape", "nao ha rodape", "nao possui rodape", "nao existe rodape",
    "revestimento ate o piso", "azulejo ate o piso", "ceramica ate o piso",
    "desce ate o piso", "vai ate o piso", "chega ate o piso",
    "parede revestida ate o piso",
)


def estado_do_rodape(observacoes: list) -> EstadoRodape:
    """Lê o estado do rodapé a partir das evidências de piso e parede.

    Conservador de propósito: a ausência só é AFIRMADA quando alguma evidência
    diz que não há rodapé ou que o revestimento desce até o piso. Não ver
    rodapé não é o mesmo que não haver."""
    texto = " | ".join(_normalizar_composto(o) for o in observacoes)
    if any(marca in texto for marca in _SEM_RODAPE):
        return EstadoRodape.AUSENTE
    if "rodape" in texto:
        return EstadoRodape.PRESENTE
    return EstadoRodape.NAO_VISIVEL


# ==========================================================================
# ATRIBUTOS E CONTRADIÇÃO (pedido, itens 28 a 30)
# ==========================================================================

# Atributos que podem entrar em conflito. A chave é o NOME do atributo: só há
# contradição quando o mesmo nome recebe valores incompatíveis.
#
# `rejunte_cor` existe separado de `cor` exatamente por causa do falso
# conflito da V1 entre "cerâmica branca" e "rejunte cinza".
ATRIBUTOS_CONHECIDOS = (
    "material", "cor", "acabamento", "rejunte_material", "rejunte_cor",
    "tipo", "estado", "defeito", "quantidade",
)

# Valores que dizem a mesma coisa. Sem isto, "branco" e "branca" brigariam.
_SINONIMOS_DE_VALOR = {
    "branca": "branco", "preta": "preto", "amarela": "amarelo",
    "vermelha": "vermelho", "roxa": "roxo", "dourada": "dourado",
    "amadeirada": "amadeirado", "clara": "claro", "escura": "escuro",
    "ceramica": "ceramico", "ceramicos": "ceramico", "ceramicas": "ceramico",
    "madeiras": "madeira", "metalica": "metalico", "metalicas": "metalico",
    "cromada": "cromado", "cromadas": "cromado",
    "acrilica": "acrilico", "plastica": "plastico",
}


def normalizar_valor(valor: str) -> str:
    limpo = " ".join(sem_acento(valor).split())
    return _SINONIMOS_DE_VALOR.get(limpo, limpo)


def atributos_conflitantes(a: dict, b: dict) -> list:
    """Nomes de atributo em que as duas evidências se contradizem.

    Só compara chave com a MESMA chave. Atributo ausente num dos lados não é
    conflito — é informação que uma foto trouxe e a outra não (item 30: o
    conflito fica restrito ao atributo, não invalida a evidência inteira)."""
    conflitos = []
    for chave in set(a) & set(b):
        if chave not in ATRIBUTOS_CONHECIDOS:
            continue
        valor_a, valor_b = normalizar_valor(a[chave]), normalizar_valor(b[chave])
        if not valor_a or not valor_b:
            continue
        if valor_a == valor_b:
            continue
        # "branco" x "branco gelo": um é refinamento do outro, não conflito.
        if valor_a in valor_b or valor_b in valor_a:
            continue
        conflitos.append(chave)
    return sorted(conflitos)


# ==========================================================================
# COMPONENTES ELÉTRICOS (pedido, itens 15 a 19)
# ==========================================================================

# Tipos que a redação PRECISA nomear. A contagem é interna; o que não pode
# faltar no texto é o tipo presente.
TIPOS_ELETRICOS = {
    "tomada": ("tomada", "tomadas"),
    "interruptor": ("interruptor", "interruptores"),
    "placa cega": ("cega", "cegas"),
    "ponto de iluminação": ("luminaria", "plafon", "spot", "lampada",
                            "iluminacao", "ponto de luz", "pendente", "arandela"),
    "saída de dados": ("rj", "internet", "rede", "coaxial", "antena", "fibra",
                       "tv", "telefone"),
    "quadro de disjuntores": ("disjuntor", "disjuntores", "quadro"),
    "ar-condicionado": ("arcondicionado", "split", "climatizacao"),
    "ventilador": ("ventilador",),
    "campainha": ("campainha",),
    "interfone": ("interfone",),
}


def tipos_eletricos_presentes(observacoes: list) -> list:
    """Quais TIPOS de componente elétrico as evidências mostram.

    É o que a redação tem que preservar. A quantidade fica guardada, mas não
    é obrigada a aparecer no texto (item 16) — "sete placas" é pior laudo que
    "placas em PVC na cor branca, sendo tomadas, interruptores e placa cega",
    e ainda por cima costuma estar errada."""
    texto = " | ".join(_normalizar_composto(o) for o in observacoes)
    presentes = []
    for rotulo, marcas in TIPOS_ELETRICOS.items():
        if any(marca in texto for marca in marcas):
            presentes.append(rotulo)
    return presentes


# "uma tomada estilo três pinos" descreve UMA INSTÂNCIA, não o total do
# cômodo (item 18). O mesmo vale para "tomada dupla": dupla é configuração
# da peça, não quantidade de placas.
_CONFIGURACOES = ("dupla", "duplo", "tripla", "triplo", "simples", "quadrupla",
                  "modulo", "modulos", "conjunto", "pinos", "saida", "saidas")


def e_configuracao_e_nao_quantidade(texto: str) -> bool:
    """A expressão descreve a CONFIGURAÇÃO da peça, não quantas peças há."""
    return any(marca in _normalizar_composto(texto) for marca in _CONFIGURACOES)
