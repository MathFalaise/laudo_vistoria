"""
EVIDÊNCIAS E ESCOPO — V2.

Responde, para cada coisa vista numa foto, a pergunta que o motor original não
fazia: "isso pertence mesmo ao cômodo que estou analisando?"

    FOTO -> ANÁLISE DA FOTO -> EVIDÊNCIAS -> VALIDAÇÃO DE ESCOPO
         -> TAXONOMIA CANÔNICA -> COBERTURA -> CONSOLIDAÇÃO -> LAUDO
         -> CONFERÊNCIA -> VALIDAÇÃO HUMANA

O que a V1 provou e o que ela errou
-----------------------------------
A V1 acertou o princípio: separar "o que vi" de "isso é daqui" impede que a
parede do corredor, vista pela porta da cozinha, vire parede da cozinha. No
benchmark de 107 fotos ela pegou um ar-condicionado inteiro que o motor
clássico perdeu, corrigiu a bacia sanitária e o tipo da porta, e descartou o
reflexo que teria criado um terceiro criado-mudo.

E errou de dois jeitos, os dois corrigidos aqui:

1. **Foi conservadora demais com a FRONTEIRA.** Soleira, peitoril e
   porta-janela ficam entre dois ambientes por natureza; a V1 leu isso como
   "ambiente adjacente" e o laudo perdeu a soleira do BWC e a categoria
   Janela inteira do Quarto Suíte. Agora existe `Escopo.FRONTEIRA`, e o
   CÓDIGO promove elemento de fronteira que o modelo tenha rebaixado
   (`core.taxonomia.e_elemento_de_fronteira`).

2. **Resumiu demais.** Porta-papel, ganchos e porta-toalha sumiram na
   consolidação. A V2 pede inventário EXAUSTIVO, guarda instância por
   instância, e a cobertura (`core.cobertura`) reclama do que faltar.

Divisão de trabalho (pedido, item 44)
-------------------------------------
O MODELO só é consultado sobre o que exige olho. Ele PROPÕE.
O CÓDIGO decide o que disso vira texto — e nada aqui depende de o modelo ter
obedecido a alguma instrução do prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from core.config import CATEGORIAS
from core.taxonomia import (
    ESCOPOS_QUE_ALIMENTAM_O_LAUDO,
    Escopo,
    atributos_conflitantes,
    categoria_canonica,
    e_cenario_alem_da_abertura,
    e_elemento_de_fronteira,
    escopo_de_texto,
    normalizar_valor,
)

# --------------------------------------------------------------------------
# Limiares. Ficam SÓ no código, nunca no prompt — mesma razão do
# config.LIMIAR_CERTEZA: se o modelo souber o corte, responde logo acima dele.
# --------------------------------------------------------------------------

# Abaixo disto, "isso pertence a este cômodo" não sustenta uma afirmação de
# laudo. Não se aplica a elemento de fronteira promovido pelo código: ali o
# pertencimento foi decidido estruturalmente, não por nota do modelo.
PISO_CONFIANCA_ESCOPO = 70

# Abaixo disto, nem como observação duvidosa vale a pena — é ruído de leitura.
PISO_CONFIANCA_PERCEPCAO = 50

# Corroboração entre FOTOS diferentes melhora a percepção, nunca o escopo.
BONUS_CORROBORACAO = 5
MAX_BONUS_CORROBORACAO = 10

# Evidência que veio de foto marcada como parcialmente do cômodo.
PENALIDADE_FOTO_PARCIAL = 10

# Evidência envolvida em contradição de atributo não resolvida.
PENALIDADE_CONTRADICAO = 25


class EscopoFoto(str, Enum):
    """Classificação da FOTO (a da evidência é `Escopo`, mais fina).

    A foto nunca é apagada por causa disto — o que muda é se ela pode
    alimentar o laudo."""

    VALIDA = "valid"
    PARCIAL = "partial"
    FORA_DE_ESCOPO = "out_of_scope"


class StatusEvidencia(str, Enum):
    ACEITA = "aceita"
    DESCARTADA = "descartada"
    EM_CONFLITO = "em_conflito"


class MotivoDescarte(str, Enum):
    """Por que uma evidência não pôde virar texto. Vai para o banco e para a
    tela de auditoria — o vistoriador precisa poder discordar do motivo."""

    FOTO_FORA_DE_ESCOPO = "foto_fora_de_escopo"
    AMBIENTE_ADJACENTE = "ambiente_adjacente"
    EXTERIOR = "exterior"
    REFLEXO = "reflexo"
    AMBIGUO = "ambiguo"
    ESCOPO_INSUFICIENTE = "escopo_insuficiente"
    PERCEPCAO_INSUFICIENTE = "percepcao_insuficiente"
    OBSERVACAO_VAZIA = "observacao_vazia"
    CONTRADICAO = "contradicao"


class TipoConflito(str, Enum):
    """Tipos de pendência que esta camada sabe gerar (pedido, item 38)."""

    ESCOPO = "scope_conflict"
    ATRIBUTO = "attribute_conflict"
    CATEGORIA = "category_conflict"
    CONTAGEM = "count_uncertain"
    COBERTURA = "possible_uncovered_item"


@dataclass(frozen=True)
class Regiao:
    """Região aproximada na foto, em fração do lado (0.0 a 1.0).

    Se o modelo não souber onde está, o campo fica None — região errada é pior
    que região nenhuma, porque a tela de auditoria desenharia um retângulo em
    cima da coisa errada (pedido, item 35)."""

    x: float
    y: float
    largura: float
    altura: float

    @classmethod
    def de_dict(cls, dados) -> "Regiao | None":
        if not isinstance(dados, dict):
            return None
        try:
            x, y, largura, altura = (
                float(dados[chave]) for chave in ("x", "y", "largura", "altura")
            )
        except (KeyError, TypeError, ValueError):
            return None
        if largura <= 0 or altura <= 0:
            return None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return None
        return cls(x=x, y=y, largura=min(largura, 1.0 - x), altura=min(altura, 1.0 - y))

    def para_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "largura": self.largura, "altura": self.altura}


@dataclass
class AnaliseFoto:
    """O que o modelo concluiu SOBRE A FOTO (não sobre o conteúdo dela)."""

    foto_id: str
    comodo_alvo: str
    escopo: EscopoFoto
    relevancia: int = 0
    ambiente_adjacente: bool = False
    reflexo: bool = False
    motivo: str = ""

    @property
    def utilizavel(self) -> bool:
        return self.escopo in (EscopoFoto.VALIDA, EscopoFoto.PARCIAL)


@dataclass
class Evidencia:
    """Uma coisa vista numa foto, ainda NÃO escrita no laudo.

    Duas confianças separadas (pedido, item 6), porque são perguntas
    diferentes: uma parede de corredor pode estar nitidíssima na foto da
    cozinha — percepção 99, escopo 10.

    `atributos` guarda material/cor/acabamento/rejunte separadamente, para a
    detecção de contradição comparar chave com chave e o redator não perder
    "dobradiça dourada" virando "dobradiça metálica" (itens 28 a 33)."""

    id: str
    foto_id: str
    categoria: str
    observacao: str
    escopo: Escopo = Escopo.AMBIGUO
    confianca_percepcao: int = 0
    confianca_escopo: int = 0
    atributos: dict = field(default_factory=dict)
    # Instância dentro do cômodo: "placa 1", "placa 2"... Guardada mesmo
    # quando a quantidade NÃO vai para o texto (itens 14 e 17).
    instancia: int = 1
    regiao: Regiao | None = None

    # Preenchidos pela validação determinística.
    status: StatusEvidencia = StatusEvidencia.ACEITA
    motivo_descarte: MotivoDescarte | None = None
    detalhe_descarte: str = ""
    confianca_final: int = 0
    corroborada_por: list = field(default_factory=list)
    escopo_original: Escopo | None = None      # antes da promoção de fronteira
    categoria_proposta: str = ""               # antes da normalização canônica
    atributos_em_conflito: list = field(default_factory=list)

    @property
    def aceita(self) -> bool:
        return self.status is StatusEvidencia.ACEITA

    # --- compatibilidade com a leitura booleana da V1 ---------------------
    @property
    def e_reflexo(self) -> bool:
        return self.escopo is Escopo.REFLEXO

    @property
    def e_ambiente_adjacente(self) -> bool:
        return self.escopo in (Escopo.ADJACENTE, Escopo.EXTERIOR)

    @property
    def e_fronteira(self) -> bool:
        return self.escopo is Escopo.FRONTEIRA

    def para_dict(self) -> dict:
        return {
            "id": self.id,
            "foto_id": self.foto_id,
            "categoria": self.categoria,
            "categoria_proposta": self.categoria_proposta,
            "observacao": self.observacao,
            "escopo": self.escopo.value,
            "escopo_original": self.escopo_original.value if self.escopo_original else None,
            "atributos": dict(self.atributos),
            "instancia": self.instancia,
            "confianca_percepcao": self.confianca_percepcao,
            "confianca_escopo": self.confianca_escopo,
            "confianca_final": self.confianca_final,
            "e_reflexo": self.e_reflexo,
            "e_ambiente_adjacente": self.e_ambiente_adjacente,
            "e_fronteira": self.e_fronteira,
            "regiao": self.regiao.para_dict() if self.regiao else None,
            "status": self.status.value,
            "motivo_descarte": self.motivo_descarte.value if self.motivo_descarte else None,
            "detalhe_descarte": self.detalhe_descarte,
            "corroborada_por": list(self.corroborada_por),
            "atributos_em_conflito": list(self.atributos_em_conflito),
        }


@dataclass
class ConflitoEscopo:
    """Divergência que o CÓDIGO detectou e NÃO pode resolver sozinho.

    Vira pendência para o vistoriador decidir olhando a foto (itens 38 e 39)."""

    categoria: str
    resumo: str
    evidencias: list
    fotos: list
    tipo: TipoConflito = TipoConflito.ESCOPO


@dataclass
class ResultadoEscopo:
    aceitas: list
    descartadas: list
    conflitos: list
    cobertura_incompleta: bool
    fotos_utilizaveis: int
    fotos_totais: int
    promovidas_para_fronteira: int = 0

    def por_categoria(self) -> dict:
        agrupado = {categoria: [] for categoria in CATEGORIAS}
        for evidencia in self.aceitas:
            agrupado[evidencia.categoria].append(evidencia)
        return agrupado


# ==========================================================================
# Validação de escopo — o coração determinístico
# ==========================================================================

def validar_escopo(evidencias: list, analises: dict, nome_comodo: str) -> ResultadoEscopo:
    """Decide quais evidências podem virar texto do laudo deste cômodo.

    `analises` é {foto_id: AnaliseFoto}. Nenhuma evidência é apagada: as que
    não passam voltam em `descartadas`, com o motivo, para a auditoria.

    A ordem das travas importa:

    1. categoria canônica (o código decide, o modelo só propôs);
    2. PROMOÇÃO DE FRONTEIRA — antes de qualquer descarte, para não perder
       soleira, peitoril e porta-janela;
    3. reflexo, que é fato categórico e não questão de grau;
    4. ambiente adjacente / exterior / ambíguo;
    5. só então os limiares numéricos."""
    aceitas, descartadas, conflitos = [], [], []
    promovidas = 0

    def descartar(evidencia, motivo, detalhe="", conflito=None):
        evidencia.status = StatusEvidencia.DESCARTADA
        evidencia.motivo_descarte = motivo
        evidencia.detalhe_descarte = detalhe
        evidencia.confianca_final = 0
        descartadas.append(evidencia)
        if conflito is not None:
            conflitos.append(conflito)

    for evidencia in evidencias:
        if not evidencia.observacao.strip():
            descartar(evidencia, MotivoDescarte.OBSERVACAO_VAZIA)
            continue

        # 1. A categoria final é decidida por código. O modelo mandar "piso"
        #    numa soleira não faz a soleira virar piso (itens 24 e 25).
        evidencia.categoria_proposta = evidencia.categoria
        evidencia.categoria = categoria_canonica(evidencia.categoria, evidencia.observacao)

        analise = analises.get(evidencia.foto_id)
        if analise is None or not analise.utilizavel:
            descartar(evidencia, MotivoDescarte.FOTO_FORA_DE_ESCOPO,
                      (analise.motivo if analise else
                       "a foto não passou pela análise de escopo"))
            continue

        # 2. PROMOÇÃO DE FRONTEIRA (itens 8 a 11, 61).
        #
        #    Porta, soleira, peitoril e esquadria ficam entre dois ambientes
        #    por natureza. O modelo tende a lê-las como "ambiente adjacente"
        #    justamente porque mostram o outro lado — e foi assim que a V1
        #    perdeu a soleira do BWC e a janela inteira do Quarto Suíte.
        #
        #    A peça é do cômodo; o CENÁRIO visível através dela não é. Por
        #    isso a promoção não vale quando a observação descreve a
        #    paisagem, e nunca vale para reflexo (uma porta vista no espelho
        #    continua sendo reflexo).
        if (evidencia.escopo in (Escopo.ADJACENTE, Escopo.EXTERIOR, Escopo.AMBIGUO)
                and e_elemento_de_fronteira(evidencia.observacao)
                and not e_cenario_alem_da_abertura(evidencia.observacao)):
            evidencia.escopo_original = evidencia.escopo
            evidencia.escopo = Escopo.FRONTEIRA
            promovidas += 1

        # 3. Reflexo: categórico. 100% de certeza de que é um reflexo não
        #    transforma o reflexo em móvel do cômodo.
        if evidencia.escopo is Escopo.REFLEXO:
            descartar(evidencia, MotivoDescarte.REFLEXO,
                      "o modelo identificou a imagem como reflexo em espelho ou vidro")
            continue

        if evidencia.escopo in (Escopo.ADJACENTE, Escopo.EXTERIOR):
            motivo = (MotivoDescarte.AMBIENTE_ADJACENTE
                      if evidencia.escopo is Escopo.ADJACENTE else MotivoDescarte.EXTERIOR)
            onde = ("um ambiente vizinho" if evidencia.escopo is Escopo.ADJACENTE
                    else "a área externa")
            descartar(
                evidencia, motivo,
                f"o modelo atribuiu esta região a {onde}, não a {nome_comodo}",
                ConflitoEscopo(
                    categoria=evidencia.categoria,
                    resumo=(f"{evidencia.observacao} — a foto mostra isso, mas a região "
                            f"foi classificada como {onde}, e não como parte de "
                            f"{nome_comodo}."),
                    evidencias=[evidencia.id], fotos=[evidencia.foto_id],
                    tipo=TipoConflito.ESCOPO,
                ),
            )
            continue

        if evidencia.escopo is Escopo.AMBIGUO:
            descartar(
                evidencia, MotivoDescarte.AMBIGUO,
                f"o modelo não conseguiu decidir se isto pertence a {nome_comodo}",
                ConflitoEscopo(
                    categoria=evidencia.categoria,
                    resumo=(f"{evidencia.observacao} — aparece na foto, mas não deu para "
                            f"decidir se faz parte de {nome_comodo}."),
                    evidencias=[evidencia.id], fotos=[evidencia.foto_id],
                    tipo=TipoConflito.ESCOPO,
                ),
            )
            continue

        if evidencia.confianca_percepcao < PISO_CONFIANCA_PERCEPCAO:
            descartar(evidencia, MotivoDescarte.PERCEPCAO_INSUFICIENTE,
                      f"o modelo não viu isso com clareza suficiente "
                      f"({evidencia.confianca_percepcao}%)")
            continue

        # 5. O piso de confiança de escopo vale para o julgamento do MODELO.
        #    Elemento promovido pelo código já teve o pertencimento decidido
        #    estruturalmente — cobrar dele a nota do modelo seria descartar
        #    de novo o que acabou de ser recuperado.
        if (evidencia.escopo_original is None
                and evidencia.confianca_escopo < PISO_CONFIANCA_ESCOPO):
            descartar(
                evidencia, MotivoDescarte.ESCOPO_INSUFICIENTE,
                f"não dá para afirmar que isto pertence a {nome_comodo} "
                f"({evidencia.confianca_escopo}%)",
                ConflitoEscopo(
                    categoria=evidencia.categoria,
                    resumo=(f"{evidencia.observacao} — aparece na foto, mas sem certeza "
                            f"suficiente de que faz parte de {nome_comodo}."),
                    evidencias=[evidencia.id], fotos=[evidencia.foto_id],
                    tipo=TipoConflito.ESCOPO,
                ),
            )
            continue

        base = min(evidencia.confianca_percepcao, evidencia.confianca_escopo)
        if evidencia.escopo_original is not None:
            # A promoção resolveu o pertencimento; a percepção continua mandando.
            base = evidencia.confianca_percepcao
        if analise.escopo is EscopoFoto.PARCIAL:
            base -= PENALIDADE_FOTO_PARCIAL
        evidencia.confianca_final = max(0, min(100, base))
        evidencia.status = StatusEvidencia.ACEITA
        aceitas.append(evidencia)

    _aplicar_corroboracao(aceitas)
    conflitos.extend(_detectar_contradicoes_de_atributo(aceitas))

    utilizaveis = sum(1 for analise in analises.values() if analise.utilizavel)
    return ResultadoEscopo(
        aceitas=aceitas,
        descartadas=descartadas,
        conflitos=conflitos,
        cobertura_incompleta=(
            any(a.escopo is EscopoFoto.PARCIAL for a in analises.values())
            or utilizaveis == 0
        ),
        fotos_utilizaveis=utilizaveis,
        fotos_totais=len(analises),
        promovidas_para_fronteira=promovidas,
    )


def _aplicar_corroboracao(aceitas: list) -> None:
    """Ver a mesma coisa em FOTOS DIFERENTES melhora a PERCEPÇÃO — e só ela.

    Esta assimetria é o ponto do item 31, e vale reler devagar:

    - ver três vezes responde melhor "o que é isso?";
    - ver três vezes NÃO responde "isso é deste cômodo?". Cinco fotos de uma
      parede de ambiente adjacente continuam sendo cinco fotos de uma parede
      de ambiente adjacente.

    Por isso o bônus entra na percepção e o escopo nunca é promovido aqui.
    Só conta foto diferente: três evidências da mesma foto não são três
    confirmações, são a mesma observação picotada."""
    for categoria in CATEGORIAS:
        do_grupo = [e for e in aceitas if e.categoria == categoria]
        for evidencia in do_grupo:
            if not evidencia.atributos:
                continue
            apoios = [
                outra.id for outra in do_grupo
                if outra is not evidencia
                and outra.foto_id != evidencia.foto_id
                and _mesma_coisa(evidencia, outra)
            ]
            if not apoios:
                continue
            evidencia.corroborada_por = apoios
            bonus = min(MAX_BONUS_CORROBORACAO, BONUS_CORROBORACAO * len(apoios))
            percepcao = min(100, evidencia.confianca_percepcao + bonus)
            teto = (100 if evidencia.escopo_original is not None
                    else evidencia.confianca_escopo)
            desconto = min(evidencia.confianca_percepcao, teto) - evidencia.confianca_final
            evidencia.confianca_final = max(
                0, min(100, min(percepcao, teto) - max(0, desconto))
            )


def _mesma_coisa(a: Evidencia, b: Evidencia) -> bool:
    """Duas evidências descrevem o mesmo tipo de coisa?

    Compara os atributos estruturados, não o texto solto: é o que permite
    dizer "as duas falam da mesma parede" sem confundir a cor do revestimento
    com a cor do rejunte."""
    comuns = set(a.atributos) & set(b.atributos)
    if not comuns:
        return False
    iguais = sum(
        1 for chave in comuns
        if normalizar_valor(a.atributos[chave]) == normalizar_valor(b.atributos[chave])
    )
    return iguais >= max(1, len(comuns) // 2)


def _detectar_contradicoes_de_atributo(aceitas: list) -> list:
    """Acha atributos com valores incompatíveis entre evidências da mesma
    categoria.

    Duas mudanças em relação à V1, as duas pedidas (itens 28 a 30):

    1. compara ATRIBUTO com atributo. "Cerâmica branca" e "rejunte cinza" não
       são versões concorrentes da mesma parede — são campos diferentes. A V1
       abriu um conflito falso com exatamente isso;
    2. o conflito fica RESTRITO ao atributo. Se duas fotos discordam só das
       dobradiças, a porta continua valendo; a V1 rebaixava a evidência
       inteira.

    Não é votação (item 59): o código só PERCEBE o desacordo, rebaixa os dois
    lados e entrega a decisão ao vistoriador. A foto isolada pode ser
    justamente a certa."""
    conflitos = []
    for categoria in CATEGORIAS:
        do_grupo = [e for e in aceitas if e.categoria == categoria and e.atributos]
        for i, uma in enumerate(do_grupo):
            for outra in do_grupo[i + 1:]:
                if uma.foto_id == outra.foto_id:
                    continue
                if not _mesma_coisa(uma, outra):
                    continue
                divergentes = atributos_conflitantes(uma.atributos, outra.atributos)
                if not divergentes:
                    continue
                for evidencia in (uma, outra):
                    evidencia.status = StatusEvidencia.EM_CONFLITO
                    evidencia.atributos_em_conflito = sorted(
                        set(evidencia.atributos_em_conflito) | set(divergentes)
                    )
                    evidencia.confianca_final = max(
                        0, evidencia.confianca_final - PENALIDADE_CONTRADICAO)
                detalhes = "; ".join(
                    f"{chave}: {uma.atributos[chave]} x {outra.atributos[chave]}"
                    for chave in divergentes
                )
                conflitos.append(ConflitoEscopo(
                    categoria=categoria,
                    resumo=(f"as fotos não concordam sobre {', '.join(divergentes)} "
                            f"deste item ({detalhes}). Os demais atributos continuam "
                            "valendo — confira qual versão é a do cômodo."),
                    evidencias=[uma.id, outra.id],
                    fotos=sorted({uma.foto_id, outra.foto_id}),
                    tipo=TipoConflito.ATRIBUTO,
                ))
    return conflitos


# ==========================================================================
# Construção a partir da resposta do modelo
# ==========================================================================

_ESCOPO_FOTO_POR_TEXTO = {
    "valid": EscopoFoto.VALIDA, "valida": EscopoFoto.VALIDA,
    "partial": EscopoFoto.PARCIAL, "parcial": EscopoFoto.PARCIAL,
    "out_of_scope": EscopoFoto.FORA_DE_ESCOPO,
    "fora_de_escopo": EscopoFoto.FORA_DE_ESCOPO,
}


def _inteiro(valor, padrao: int = 0) -> int:
    try:
        return max(0, min(100, int(valor)))
    except (TypeError, ValueError):
        return padrao


def analise_de_dict(dados: dict, foto_id: str, nome_comodo: str) -> AnaliseFoto:
    """Converte o JSON do modelo numa AnaliseFoto.

    Escopo desconhecido cai em FORA_DE_ESCOPO: quando o sistema não entendeu a
    resposta, a saída segura é não usar a foto (item 45)."""
    from core.taxonomia import sem_acento

    escopo = _ESCOPO_FOTO_POR_TEXTO.get(
        sem_acento(dados.get("escopo", "")).strip(), EscopoFoto.FORA_DE_ESCOPO
    )
    return AnaliseFoto(
        foto_id=foto_id,
        comodo_alvo=nome_comodo,
        escopo=escopo,
        relevancia=_inteiro(dados.get("relevancia")),
        ambiente_adjacente=bool(dados.get("ambiente_adjacente")),
        reflexo=bool(dados.get("reflexo")),
        motivo=" ".join(str(dados.get("motivo", "")).split()),
    )


def evidencia_de_dict(dados: dict, evidencia_id: str, foto_id: str) -> Evidencia:
    """Constrói a evidência a partir do JSON do modelo.

    Aceita tanto o campo `escopo` da V2 quanto os booleanos `reflexo` /
    `ambiente_adjacente` da V1 — um laudo antigo reimportado não pode quebrar
    a leitura."""
    escopo = dados.get("escopo")
    if escopo:
        escopo_final = escopo_de_texto(escopo)
    elif dados.get("reflexo"):
        escopo_final = Escopo.REFLEXO
    elif dados.get("ambiente_adjacente"):
        escopo_final = Escopo.ADJACENTE
    else:
        escopo_final = Escopo.INTERIOR

    atributos = dados.get("atributos")
    if not isinstance(atributos, dict):
        atributos = {}
    atributos = {
        str(chave): " ".join(str(valor).split())
        for chave, valor in atributos.items()
        if str(valor).strip()
    }

    try:
        instancia = max(1, int(dados.get("instancia", 1)))
    except (TypeError, ValueError):
        instancia = 1

    return Evidencia(
        id=evidencia_id,
        foto_id=foto_id,
        categoria=str(dados.get("categoria", "")).strip(),
        observacao=" ".join(str(dados.get("observacao", "")).split()),
        escopo=escopo_final,
        confianca_percepcao=_inteiro(dados.get("confianca_percepcao")),
        confianca_escopo=_inteiro(dados.get("confianca_escopo")),
        atributos=atributos,
        instancia=instancia,
        regiao=Regiao.de_dict(dados.get("regiao")),
    )
