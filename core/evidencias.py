"""
EVIDÊNCIAS E ESCOPO — a camada que responde, para cada coisa vista numa foto,
a pergunta que o motor antigo não fazia:

    "isso pertence mesmo ao cômodo que estou analisando?"

Por que existe
--------------
A arquitetura antiga era, conceitualmente, FOTO -> LAUDO: tudo o que aparecia
numa foto guardada na pasta "Cozinha" virava afirmação sobre a cozinha. Só que
a foto da cozinha enquadra a porta, e pela porta se vê o corredor; o espelho
do banheiro reflete o quarto; a última foto do quarto pega meia parede da
sala. O modelo então descrevia como "parede da cozinha" uma parede que é do
corredor — e o laudo, que é documento assinado, saía com um falso positivo.

Isso NÃO se resolve escrevendo mais parágrafos no prompt (já se tentou). O
pertencimento ao cômodo tem que ser uma VARIÁVEL do sistema, com estado,
validação determinística e rastro — não uma esperança depositada no texto do
prompt. É o que este módulo faz:

    FOTO -> ANÁLISE DA FOTO -> EVIDÊNCIAS -> VALIDAÇÃO DE ESCOPO
         -> CONSOLIDAÇÃO -> LAUDO -> CONFERÊNCIA -> VALIDAÇÃO HUMANA

Divisão de trabalho (regra 37/38 do pedido: prompt orienta, código protege)
--------------------------------------------------------------------------
O MODELO só é consultado sobre o que exige olho: o que aparece na foto, se a
foto é do cômodo, se aquilo é reflexo, quanta certeza ele tem. Ele PROPÕE.

O CÓDIGO decide o que disso pode virar texto do laudo. Nenhuma regra deste
módulo depende de o modelo ter obedecido a alguma instrução: evidência de
reflexo é descartada aqui, não "pedida para não usar"; evidência de ambiente
adjacente vira pendência aqui; item sem evidência não é escrito.

O que NÃO se faz aqui
---------------------
Nada é apagado. Foto fora de escopo continua no disco e no banco, com o motivo
registrado — a auditoria precisa poder discordar. Evidência descartada também
fica: ela só perde o direito de alimentar a redação.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum

from core.config import CATEGORIAS

# --------------------------------------------------------------------------
# Limiares. Ficam SÓ no código, nunca no prompt — mesma razão do
# config.LIMIAR_CERTEZA: se o modelo souber o corte, responde logo acima dele.
# --------------------------------------------------------------------------

# Abaixo disto, "isso pertence a este cômodo" não sustenta uma afirmação de
# laudo. Alto de propósito: a regra 16 do pedido diz que falso positivo é pior
# que falso negativo, e atribuir ao cômodo errado é o falso positivo mais caro
# que este sistema produz.
PISO_CONFIANCA_ESCOPO = 70

# Abaixo disto, nem como observação duvidosa vale a pena — é ruído de leitura.
PISO_CONFIANCA_PERCEPCAO = 50

# Uma evidência que aparece em MAIS DE UMA foto é mais forte que a mesma
# evidência vista uma vez só. O bônus é pequeno e limitado (ver
# _aplicar_corroboracao): corroboração não cria pertencimento.
BONUS_CORROBORACAO = 5
MAX_BONUS_CORROBORACAO = 10

# Foto que o modelo classificou como PARCIAL (mostra o cômodo, mas também
# ambiente vizinho ou região ambígua) sustenta evidência, com desconto.
PENALIDADE_FOTO_PARCIAL = 10

# Evidência envolvida em contradição não resolvida entre fotos.
PENALIDADE_CONTRADICAO = 25


class EscopoFoto(str, Enum):
    """Classificação de uma foto em relação ao cômodo que está sendo escrito.

    A foto NUNCA é apagada por causa disto (regra 7 do pedido) — o que muda é
    se ela pode ser usada como evidência."""

    VALIDA = "valid"                  # é do cômodo, pode alimentar o laudo
    PARCIAL = "partial"               # é do cômodo, mas tem vizinho/ambiguidade
    FORA_DE_ESCOPO = "out_of_scope"   # não alimenta o laudo deste cômodo


class StatusEvidencia(str, Enum):
    ACEITA = "aceita"                 # entra na redação
    DESCARTADA = "descartada"         # não entra; motivo registrado
    EM_CONFLITO = "em_conflito"       # não entra sozinha; vira pendência


class MotivoDescarte(str, Enum):
    """Por que uma evidência não pôde virar texto. Vai para o banco e para a
    tela de auditoria — o vistoriador precisa poder discordar do motivo."""

    FOTO_FORA_DE_ESCOPO = "foto_fora_de_escopo"
    AMBIENTE_ADJACENTE = "ambiente_adjacente"
    REFLEXO = "reflexo"
    ESCOPO_INSUFICIENTE = "escopo_insuficiente"
    PERCEPCAO_INSUFICIENTE = "percepcao_insuficiente"
    CATEGORIA_INVALIDA = "categoria_invalida"
    OBSERVACAO_VAZIA = "observacao_vazia"
    CONTRADICAO = "contradicao"


@dataclass(frozen=True)
class Regiao:
    """Região aproximada da foto, em fração do lado (0.0 a 1.0).

    Regra 9 do pedido: se o modelo não souber onde está, NÃO inventa — o campo
    fica None. Uma região errada é pior que região nenhuma, porque a tela de
    auditoria desenharia um retângulo em cima da coisa errada."""

    x: float
    y: float
    largura: float
    altura: float

    @classmethod
    def de_dict(cls, dados) -> "Regiao | None":
        if not isinstance(dados, dict):
            return None
        try:
            valores = [float(dados[chave]) for chave in ("x", "y", "largura", "altura")]
        except (KeyError, TypeError, ValueError):
            return None
        # Uma região degenerada (largura ou altura zero) ou fora da imagem é
        # palpite malfeito, não localização.
        x, y, largura, altura = valores
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
    """Uma coisa vista numa foto, ainda não escrita no laudo.

    Note os DOIS níveis de confiança (regra 14 do pedido). O motor antigo
    tinha um número só, e ele misturava duas perguntas muito diferentes:
    "está claro na imagem?" e "é deste cômodo?". Uma parede de corredor pode
    estar nitidíssima na foto da cozinha — percepção 99, escopo 10."""

    id: str
    foto_id: str
    categoria: str
    observacao: str
    confianca_percepcao: int = 0
    confianca_escopo: int = 0
    e_reflexo: bool = False
    e_ambiente_adjacente: bool = False
    regiao: Regiao | None = None

    # Preenchidos pela validação determinística (validar_escopo).
    status: StatusEvidencia = StatusEvidencia.ACEITA
    motivo_descarte: MotivoDescarte | None = None
    detalhe_descarte: str = ""
    confianca_final: int = 0
    corroborada_por: list[str] = field(default_factory=list)

    @property
    def aceita(self) -> bool:
        return self.status is StatusEvidencia.ACEITA

    def para_dict(self) -> dict:
        return {
            "id": self.id,
            "foto_id": self.foto_id,
            "categoria": self.categoria,
            "observacao": self.observacao,
            "confianca_percepcao": self.confianca_percepcao,
            "confianca_escopo": self.confianca_escopo,
            "confianca_final": self.confianca_final,
            "e_reflexo": self.e_reflexo,
            "e_ambiente_adjacente": self.e_ambiente_adjacente,
            "regiao": self.regiao.para_dict() if self.regiao else None,
            "status": self.status.value,
            "motivo_descarte": self.motivo_descarte.value if self.motivo_descarte else None,
            "detalhe_descarte": self.detalhe_descarte,
            "corroborada_por": list(self.corroborada_por),
        }


@dataclass
class ConflitoEscopo:
    """Divergência que o CÓDIGO detectou e que NÃO pode ser resolvida sozinha.

    Vira pendência do tipo scope_conflict (regra 19 do pedido): quem decide é
    o vistoriador, olhando a foto."""

    categoria: str
    resumo: str
    evidencias: list[str]
    fotos: list[str]


@dataclass
class ResultadoEscopo:
    """O que a validação determinística produziu, pronto para a redação."""

    aceitas: list[Evidencia]
    descartadas: list[Evidencia]
    conflitos: list[ConflitoEscopo]
    cobertura_incompleta: bool
    fotos_utilizaveis: int
    fotos_totais: int

    def por_categoria(self) -> dict:
        agrupado = {categoria: [] for categoria in CATEGORIAS}
        for evidencia in self.aceitas:
            agrupado[evidencia.categoria].append(evidencia)
        return agrupado


# --------------------------------------------------------------------------
# Vocabulário para detectar contradição entre fotos.
#
# Deliberadamente pequeno e fechado. Ele existe só para o código PERCEBER que
# duas fotos afirmam coisas incompatíveis sobre a mesma superfície — nunca
# para escolher quem está certo. Quem escolhe é o vistoriador.
# --------------------------------------------------------------------------

_CATEGORIAS_DE_SUPERFICIE = ("paredes", "piso", "teto")

_CORES = (
    "branco", "branca", "preto", "preta", "cinza", "bege", "marrom", "palha",
    "amarelo", "amarela", "azul", "verde", "vermelho", "vermelha", "rosa",
    "laranja", "roxo", "roxa", "dourado", "dourada", "prata", "amadeirado",
    "amadeirada", "creme", "grafite", "chumbo", "terracota", "salmao", "gelo",
    "neve", "cromio", "natural", "fume", "incolor",
)

# Cor e material que, dito de duas formas, é a mesma coisa. Sem isto o sistema
# gritaria "contradição" entre "branco" e "branca".
_SINONIMOS = {
    "branca": "branco", "preta": "preto", "amarela": "amarelo",
    "vermelha": "vermelho", "roxa": "roxo", "dourada": "dourado",
    "amadeirada": "amadeirado", "salmao": "salmao",
    "ceramica": "ceramico", "porcelanato": "porcelanato",
}

_MATERIAIS = (
    "ceramico", "ceramica", "porcelanato", "laminado", "vinilico", "madeira",
    "granito", "marmore", "gesso", "alvenaria", "pvc", "azulejo", "pastilha",
    "textura", "pintura", "cimento", "pedra", "carpete", "tijolinho", "mdf",
)


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return texto.encode("ascii", "ignore").decode()


def _termos(observacao: str, vocabulario: tuple) -> set:
    """Termos do vocabulário presentes na observação, já normalizados."""
    palavras = set(re.findall(r"[a-z]+", _sem_acento(observacao)))
    achados = {palavra for palavra in palavras if palavra in vocabulario}
    return {_SINONIMOS.get(termo, termo) for termo in achados}


def _assinatura(evidencia: Evidencia) -> tuple:
    """(cores, materiais) de uma evidência de superfície."""
    return (_termos(evidencia.observacao, _CORES),
            _termos(evidencia.observacao, _MATERIAIS))


# --------------------------------------------------------------------------
# Validação de escopo — o coração determinístico
# --------------------------------------------------------------------------

def validar_escopo(
    evidencias: list,
    analises: dict,
    nome_comodo: str,
) -> ResultadoEscopo:
    """Decide quais evidências podem virar texto do laudo deste cômodo.

    `analises` é {foto_id: AnaliseFoto}. Nenhuma evidência é apagada: as que
    não passam voltam em `descartadas`, com o motivo, para a auditoria.

    A ordem das travas importa. Reflexo e ambiente adjacente são checados
    ANTES dos limiares numéricos, porque são fatos categóricos: uma parede
    refletida no espelho não vira parede deste cômodo por ter confiança 99."""
    aceitas, descartadas, conflitos = [], [], []

    def descartar(evidencia: Evidencia, motivo: MotivoDescarte, detalhe: str = ""):
        evidencia.status = StatusEvidencia.DESCARTADA
        evidencia.motivo_descarte = motivo
        evidencia.detalhe_descarte = detalhe
        evidencia.confianca_final = 0
        descartadas.append(evidencia)

    for evidencia in evidencias:
        analise = analises.get(evidencia.foto_id)

        if evidencia.categoria not in CATEGORIAS:
            descartar(evidencia, MotivoDescarte.CATEGORIA_INVALIDA,
                      f"categoria '{evidencia.categoria}' não existe no laudo")
            continue

        if not evidencia.observacao.strip():
            descartar(evidencia, MotivoDescarte.OBSERVACAO_VAZIA)
            continue

        # A foto inteira já foi descartada para este cômodo.
        if analise is None or not analise.utilizavel:
            descartar(evidencia, MotivoDescarte.FOTO_FORA_DE_ESCOPO,
                      (analise.motivo if analise else
                       "a foto não passou pela análise de escopo"))
            continue

        # Fato categórico, não questão de grau: o que está no espelho já foi
        # (ou será) descrito onde ele de fato está. Contar de novo aqui
        # duplicaria o item — foi assim que um "armário de madeira" inexistente
        # entrou num laudo em 22/09/2026.
        if evidencia.e_reflexo:
            descartar(evidencia, MotivoDescarte.REFLEXO,
                      "o modelo identificou a imagem como reflexo em espelho ou vidro")
            continue

        # Também categórico: isto é o problema que motivou o módulo inteiro.
        # Vira conflito, não silêncio — o vistoriador decide olhando a foto.
        if evidencia.e_ambiente_adjacente:
            descartar(evidencia, MotivoDescarte.AMBIENTE_ADJACENTE,
                      f"o modelo atribuiu esta região a um ambiente vizinho, não a {nome_comodo}")
            conflitos.append(ConflitoEscopo(
                categoria=evidencia.categoria,
                resumo=(f"{evidencia.observacao} — a foto mostra isso, mas a região foi "
                        f"classificada como ambiente vizinho, e não como parte de "
                        f"{nome_comodo}."),
                evidencias=[evidencia.id],
                fotos=[evidencia.foto_id],
            ))
            continue

        if evidencia.confianca_percepcao < PISO_CONFIANCA_PERCEPCAO:
            descartar(evidencia, MotivoDescarte.PERCEPCAO_INSUFICIENTE,
                      f"o modelo não viu isso com clareza suficiente "
                      f"({evidencia.confianca_percepcao}%)")
            continue

        if evidencia.confianca_escopo < PISO_CONFIANCA_ESCOPO:
            descartar(evidencia, MotivoDescarte.ESCOPO_INSUFICIENTE,
                      f"não dá para afirmar que isto pertence a {nome_comodo} "
                      f"({evidencia.confianca_escopo}%)")
            conflitos.append(ConflitoEscopo(
                categoria=evidencia.categoria,
                resumo=(f"{evidencia.observacao} — aparece na foto, mas sem certeza "
                        f"suficiente de que faz parte de {nome_comodo}."),
                evidencias=[evidencia.id],
                fotos=[evidencia.foto_id],
            ))
            continue

        # Passou. A confiança final parte da afirmação MENOS segura — mesma
        # filosofia que o laudo já usava para a certeza do item ("se a porta é
        # claramente de madeira mas a roseta mal aparece, a certeza do item é
        # a da roseta"). Ver INSTRUCAO_CERTEZA em style_guide.
        base = min(evidencia.confianca_percepcao, evidencia.confianca_escopo)
        if analise.escopo is EscopoFoto.PARCIAL:
            base -= PENALIDADE_FOTO_PARCIAL
        evidencia.confianca_final = max(0, min(100, base))
        evidencia.status = StatusEvidencia.ACEITA
        aceitas.append(evidencia)

    _aplicar_corroboracao(aceitas)
    conflitos.extend(_detectar_contradicoes(aceitas))

    utilizaveis = sum(1 for analise in analises.values() if analise.utilizavel)
    return ResultadoEscopo(
        aceitas=aceitas,
        descartadas=descartadas,
        conflitos=conflitos,
        # Regra 35/CASO 3: se nenhuma foto cobre o cômodo por inteiro, o
        # sistema não pode concluir que algo NÃO EXISTE. Quem usa isso é a
        # consolidação, para não deixar "Não se aplica." sair com certeza alta.
        cobertura_incompleta=any(
            analise.escopo is EscopoFoto.PARCIAL for analise in analises.values()
        ) or utilizaveis == 0,
        fotos_utilizaveis=utilizaveis,
        fotos_totais=len(analises),
    )


def _aplicar_corroboracao(aceitas: list) -> None:
    """Ver a mesma coisa em FOTOS DIFERENTES melhora a PERCEPÇÃO — e só ela.

    Esta assimetria é o ponto inteiro da regra 14, e vale reler devagar:

    - ver três vezes responde melhor "o que é isso?". Uma bancada que apareceu
      desfocada numa foto e nítida em outras dua é uma bancada bem vista;
    - ver três vezes NÃO responde "isso é deste cômodo?". Uma parede de
      corredor fotografada de cinco ângulos continua sendo do corredor.

    Por isso o bônus entra na percepção e a confiança final continua limitada
    pela confiança de ESCOPO. Consequência prática: quando o escopo já é o
    fator limitante, corroborar não muda nada — que é exatamente o
    comportamento desejado.

    Só conta foto diferente: três evidências da mesma foto não são três
    confirmações, são a mesma observação picotada."""
    for categoria in CATEGORIAS:
        do_grupo = [e for e in aceitas if e.categoria == categoria]
        for evidencia in do_grupo:
            cores, materiais = _assinatura(evidencia)
            if not cores and not materiais:
                continue
            apoios = []
            for outra in do_grupo:
                if outra is evidencia or outra.foto_id == evidencia.foto_id:
                    continue
                outras_cores, outros_materiais = _assinatura(outra)
                if (cores & outras_cores) or (materiais & outros_materiais):
                    apoios.append(outra.id)
            if not apoios:
                continue
            evidencia.corroborada_por = apoios
            bonus = min(MAX_BONUS_CORROBORACAO, BONUS_CORROBORACAO * len(apoios))
            percepcao = min(100, evidencia.confianca_percepcao + bonus)
            # Recalcula a partir da percepção melhorada, mantendo o teto de
            # escopo e a penalidade de foto parcial que já tinham sido aplicados.
            desconto = min(evidencia.confianca_percepcao,
                           evidencia.confianca_escopo) - evidencia.confianca_final
            evidencia.confianca_final = max(
                0, min(100, min(percepcao, evidencia.confianca_escopo) - desconto)
            )


def _detectar_contradicoes(aceitas: list) -> list:
    """Acha superfícies (parede/piso/teto) descritas de formas incompatíveis.

    NÃO é votação (regra 13 do pedido). O código não elege a versão com mais
    fotos e apaga o resto: a foto isolada pode ser justamente a que mostra a
    parede certa — foi o que aconteceu com a parede vermelha em textura
    projetada da R. Correia de Freitas, que aparecia em poucas fotos e era
    real. Aqui o código só PERCEBE o desacordo, rebaixa as duas versões e
    entrega a decisão ao vistoriador."""
    conflitos = []
    for categoria in _CATEGORIAS_DE_SUPERFICIE:
        do_grupo = [e for e in aceitas if e.categoria == categoria]
        if len(do_grupo) < 2:
            continue

        por_cor = {}
        for evidencia in do_grupo:
            cores, _ = _assinatura(evidencia)
            for cor in cores:
                por_cor.setdefault(cor, []).append(evidencia)

        # Uma cor só (ou nenhuma reconhecida): nada a decidir.
        if len(por_cor) < 2:
            continue

        # Um mesmo item pode citar duas cores legitimamente ("branca com faixa
        # decorativa em tons de verde"). Só é contradição quando as versões
        # vêm de evidências DIFERENTES que não compartilham nenhuma cor.
        grupos = list(por_cor.items())
        divergentes = [
            (cor, evidencias) for cor, evidencias in grupos
            if not any(e in evidencias for outra_cor, outras in grupos
                       if outra_cor != cor for e in outras)
        ]
        if len(divergentes) < 2:
            continue

        envolvidas = [e for _, evidencias in divergentes for e in evidencias]
        for evidencia in envolvidas:
            evidencia.status = StatusEvidencia.EM_CONFLITO
            evidencia.confianca_final = max(
                0, evidencia.confianca_final - PENALIDADE_CONTRADICAO)
        conflitos.append(ConflitoEscopo(
            categoria=categoria,
            resumo=("as fotos não concordam sobre esta superfície: "
                    + "; ".join(f"{cor} ({len(evidencias)} evidência(s))"
                                for cor, evidencias in divergentes)
                    + ". Nenhuma versão foi descartada — confira qual é a do cômodo."),
            evidencias=[e.id for e in envolvidas],
            fotos=sorted({e.foto_id for e in envolvidas}),
        ))
    return conflitos


# --------------------------------------------------------------------------
# Construção a partir da resposta do modelo
# --------------------------------------------------------------------------

_ESCOPO_POR_TEXTO = {
    "valid": EscopoFoto.VALIDA,
    "valida": EscopoFoto.VALIDA,
    "partial": EscopoFoto.PARCIAL,
    "parcial": EscopoFoto.PARCIAL,
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

    Escopo desconhecido cai em FORA_DE_ESCOPO, não em VALIDA: quando o sistema
    não entendeu a resposta, a saída segura é não usar a foto (regra 16)."""
    escopo = _ESCOPO_POR_TEXTO.get(
        _sem_acento(str(dados.get("escopo", ""))).strip(), EscopoFoto.FORA_DE_ESCOPO
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
    return Evidencia(
        id=evidencia_id,
        foto_id=foto_id,
        categoria=str(dados.get("categoria", "")).strip(),
        observacao=" ".join(str(dados.get("observacao", "")).split()),
        confianca_percepcao=_inteiro(dados.get("confianca_percepcao")),
        confianca_escopo=_inteiro(dados.get("confianca_escopo")),
        e_reflexo=bool(dados.get("reflexo")),
        e_ambiente_adjacente=bool(dados.get("ambiente_adjacente")),
        regiao=Regiao.de_dict(dados.get("regiao")),
    )
