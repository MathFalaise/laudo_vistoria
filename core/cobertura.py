"""
CHECKLIST DE COBERTURA — o antídoto para o que a V1 perdeu.

No benchmark de 107 fotos a V1 acertou mais fatos que o motor clássico e ainda
assim entregou um laudo pior em um ponto: **sumiram o porta-papel, os ganchos
e o porta-toalha do BWC**. A camada de evidências estava resumindo.

Este módulo faz a pergunta que faltava, depois da extração e antes da
redação:

    "Existe evidência suficiente para este tipo de item neste cômodo?"

O que ele NÃO faz (pedido, item 22)
-----------------------------------
Não inventa que o item existe. A saída é sempre uma DÚVIDA, nunca uma
afirmação: `POSSIVEL_ITEM_NAO_COBERTO`. Ela vira uma segunda olhada dirigida
(`core.pipeline`) ou uma pendência — nunca uma linha no laudo.

A diferença importa. "O banheiro não tem porta-papel" é uma afirmação sobre o
imóvel, e o sistema não tem como sabê-la. "Não achei evidência de porta-papel,
vá olhar" é uma tarefa, e essa o sistema pode emitir sem risco.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.taxonomia import _normalizar_composto, sem_acento


@dataclass(frozen=True)
class ItemEsperado:
    """Um tipo de coisa que costuma existir num certo tipo de cômodo."""

    chave: str
    rotulo: str
    marcas: tuple
    categoria: str
    # Instrução para a segunda olhada dirigida, quando faltar.
    onde_olhar: str


@dataclass
class Lacuna:
    """Possível item não coberto. É dúvida, não afirmação."""

    chave: str
    rotulo: str
    categoria: str
    onde_olhar: str


# --------------------------------------------------------------------------
# Tipos de cômodo, reconhecidos pelo nome da pasta.
# --------------------------------------------------------------------------

def tipo_de_comodo(nome: str) -> str:
    limpo = sem_acento(nome)
    if any(marca in limpo for marca in ("bwc", "banheiro", "lavabo", "suite social",
                                        "wc", "sanitario")):
        return "banheiro"
    if "cozinha" in limpo:
        return "cozinha"
    if any(marca in limpo for marca in ("area de servico", "lavanderia", "servico")):
        return "area_de_servico"
    if any(marca in limpo for marca in ("quarto", "dormitorio", "suite")):
        return "quarto"
    if any(marca in limpo for marca in ("sala", "estar", "jantar", "living")):
        return "sala"
    if any(marca in limpo for marca in ("varanda", "sacada", "terraco")):
        return "varanda"
    if any(marca in limpo for marca in ("corredor", "hall", "circulacao")):
        return "corredor"
    if any(marca in limpo for marca in ("garagem", "vaga")):
        return "garagem"
    return "generico"


# --------------------------------------------------------------------------
# O que se espera em cada tipo. Os itens pequenos vêm primeiro de propósito:
# são os que somem.
# --------------------------------------------------------------------------

_ACESSORIOS_DE_PAREDE = (
    "Revise estas fotos procurando EXCLUSIVAMENTE pequenos acessórios "
    "fixados nas paredes e no box: porta-papel, porta-toalha, toalheiro em "
    "argola, ganchos e cabides, saboneteira, porta-shampoo, prateleira de "
    "canto. Liste cada um separadamente."
)
_ESQUADRIAS = (
    "Revise estas fotos procurando EXCLUSIVAMENTE esquadrias e seus "
    "componentes: peitoril, soleira, batente, vistas, trilho, fecho."
)
_ELETRICOS = (
    "Revise estas fotos procurando EXCLUSIVAMENTE componentes elétricos, "
    "identificando os TIPOS presentes (tomada, interruptor, placa cega, "
    "saída de dados/TV, quadro de disjuntores, ponto de iluminação)."
)
_CLIMATIZACAO = (
    "Revise estas fotos procurando EXCLUSIVAMENTE equipamentos fixos de "
    "climatização e ventilação: ar-condicionado, ventilador de teto, "
    "exaustor, e a infraestrutura deles na parede."
)

_COMUNS = (
    ItemEsperado("piso", "piso", ("piso", "porcelanato", "ceramica", "laminado",
                                  "vinilico", "carpete", "taco"), "piso",
                 "Revise estas fotos olhando EXCLUSIVAMENTE o piso e a junção com a parede."),
    ItemEsperado("teto", "teto", ("teto", "laje", "forro", "gesso", "sanca"), "teto",
                 "Revise estas fotos olhando EXCLUSIVAMENTE o teto."),
    ItemEsperado("parede", "paredes", ("parede", "azulejo", "revestimento",
                                       "pintura", "textura", "pastilha"), "paredes",
                 "Revise estas fotos olhando EXCLUSIVAMENTE as paredes e o acabamento delas."),
    ItemEsperado("porta", "porta", ("porta", "batente", "soleira", "vistas"), "porta",
                 _ESQUADRIAS),
    ItemEsperado("iluminacao", "ponto de iluminação",
                 ("luminaria", "plafon", "spot", "lampada", "iluminacao", "pendente"),
                 "eletrico", _ELETRICOS),
    ItemEsperado("tomada", "tomadas e interruptores",
                 ("tomada", "interruptor", "placa"), "eletrico", _ELETRICOS),
)

_ESPERADO_POR_TIPO = {
    "banheiro": _COMUNS + (
        ItemEsperado("bacia", "bacia sanitária", ("bacia", "vaso sanitario", "sanitaria"),
                     "mobilia", "Revise procurando EXCLUSIVAMENTE a bacia sanitária e o acionamento da descarga."),
        ItemEsperado("bancada", "bancada e cuba", ("bancada", "cuba", "pia", "lavatorio"),
                     "mobilia", "Revise procurando EXCLUSIVAMENTE a bancada, a cuba, a torneira e o sifão."),
        ItemEsperado("chuveiro", "chuveiro", ("chuveiro", "ducha"), "mobilia",
                     "Revise procurando EXCLUSIVAMENTE o chuveiro e os registros."),
        ItemEsperado("box", "box", ("box",), "mobilia",
                     "Revise procurando EXCLUSIVAMENTE o box e os componentes dele."),
        ItemEsperado("espelho", "espelho", ("espelho",), "mobilia",
                     "Revise procurando EXCLUSIVAMENTE espelho e armário com espelho."),
        ItemEsperado("portapapel", "porta-papel higiênico",
                     ("portapapel", "papeleira"), "mobilia", _ACESSORIOS_DE_PAREDE),
        ItemEsperado("portatoalha", "porta-toalha ou toalheiro",
                     ("portatoalha", "toalheiro"), "mobilia", _ACESSORIOS_DE_PAREDE),
        ItemEsperado("ganchos", "ganchos e cabideiros",
                     ("gancho", "cabideiro", "cabide"), "mobilia", _ACESSORIOS_DE_PAREDE),
        ItemEsperado("saboneteira", "saboneteira",
                     ("saboneteira", "portashampoo", "sabonete"), "mobilia",
                     _ACESSORIOS_DE_PAREDE),
        ItemEsperado("janela", "janela", ("janela", "basculante", "maximar", "peitoril"),
                     "janela", _ESQUADRIAS),
    ),
    "quarto": _COMUNS + (
        ItemEsperado("janela", "janela", ("janela", "esquadria", "peitoril",
                                          "portajanela"), "janela", _ESQUADRIAS),
        ItemEsperado("climatizacao", "ar-condicionado ou ventilador",
                     ("arcondicionado", "split", "ventilador"), "eletrico",
                     _CLIMATIZACAO),
        ItemEsperado("armario", "armário ou guarda-roupa",
                     ("armario", "guardaroupa", "closet"), "mobilia",
                     "Revise procurando EXCLUSIVAMENTE armários, guarda-roupas e as peças deles."),
        ItemEsperado("rodape", "rodapé", ("rodape",), "piso",
                     "Revise a junção entre a parede e o piso: há rodapé? De que material e cor?"),
    ),
    "cozinha": _COMUNS + (
        ItemEsperado("janela", "janela", ("janela", "esquadria", "peitoril"), "janela",
                     _ESQUADRIAS),
        ItemEsperado("bancada", "bancada e cuba", ("bancada", "cuba", "pia"), "mobilia",
                     "Revise procurando EXCLUSIVAMENTE bancada, cuba, torneira e sifão."),
        ItemEsperado("armario", "armários", ("armario", "gabinete", "aereo"), "mobilia",
                     "Revise procurando EXCLUSIVAMENTE armários, gabinetes e nichos."),
    ),
    "area_de_servico": _COMUNS + (
        ItemEsperado("tanque", "tanque", ("tanque",), "mobilia",
                     "Revise procurando EXCLUSIVAMENTE tanque, torneira e registros."),
        ItemEsperado("quadro", "quadro de disjuntores", ("quadro", "disjuntor"),
                     "eletrico", _ELETRICOS),
        ItemEsperado("janela", "janela", ("janela", "esquadria", "peitoril"), "janela",
                     _ESQUADRIAS),
    ),
    "sala": _COMUNS + (
        ItemEsperado("janela", "janela", ("janela", "esquadria", "peitoril",
                                          "portajanela"), "janela", _ESQUADRIAS),
        ItemEsperado("climatizacao", "ar-condicionado ou ventilador",
                     ("arcondicionado", "split", "ventilador"), "eletrico",
                     _CLIMATIZACAO),
        ItemEsperado("rodape", "rodapé", ("rodape",), "piso",
                     "Revise a junção entre a parede e o piso: há rodapé? De que material e cor?"),
    ),
    "varanda": (
        ItemEsperado("piso", "piso", ("piso", "porcelanato", "ceramica"), "piso",
                     "Revise olhando EXCLUSIVAMENTE o piso e o ralo."),
        ItemEsperado("parede", "paredes", ("parede", "textura", "revestimento",
                                           "mureta"), "paredes",
                     "Revise olhando EXCLUSIVAMENTE as paredes, a mureta e o acabamento do topo dela."),
        ItemEsperado("iluminacao", "ponto de iluminação",
                     ("luminaria", "plafon", "spot", "lampada"), "eletrico", _ELETRICOS),
    ),
    "corredor": _COMUNS,
    "garagem": _COMUNS,
    "generico": _COMUNS,
}


def itens_esperados(nome_comodo: str) -> tuple:
    return _ESPERADO_POR_TIPO.get(tipo_de_comodo(nome_comodo), _COMUNS)


def encontrar_lacunas(nome_comodo: str, evidencias: list) -> list:
    """Tipos esperados para os quais NÃO há evidência.

    Recebe as evidências ACEITAS (e só elas): se a única menção ao chuveiro
    veio de um reflexo descartado, o chuveiro segue não coberto — e é isso
    que se quer, porque a segunda olhada pode achar o de verdade."""
    texto = " | ".join(_normalizar_composto(e.observacao) for e in evidencias)
    lacunas = []
    for esperado in itens_esperados(nome_comodo):
        if any(marca in texto for marca in esperado.marcas):
            continue
        lacunas.append(Lacuna(chave=esperado.chave, rotulo=esperado.rotulo,
                              categoria=esperado.categoria,
                              onde_olhar=esperado.onde_olhar))
    return lacunas


def instrucoes_de_segunda_olhada(lacunas: list) -> list:
    """Agrupa as lacunas nas instruções dirigidas, sem repetir.

    Várias lacunas compartilham a mesma instrução (porta-papel, ganchos e
    toalheiro caem todos em "procure acessórios de parede"). Mandar a mesma
    frase três vezes gastaria três chamadas para a mesma busca."""
    vistas, instrucoes = set(), []
    for lacuna in lacunas:
        if lacuna.onde_olhar in vistas:
            continue
        vistas.add(lacuna.onde_olhar)
        alvos = [outra.rotulo for outra in lacunas if outra.onde_olhar == lacuna.onde_olhar]
        instrucoes.append({
            "instrucao": lacuna.onde_olhar,
            "procurando": alvos,
            "categorias": sorted({
                outra.categoria for outra in lacunas
                if outra.onde_olhar == lacuna.onde_olhar
            }),
        })
    return instrucoes
