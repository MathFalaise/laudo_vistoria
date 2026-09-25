"""
Guia de estilo do laudo — define o padrão de escrita que o modelo deve seguir
e as instruções específicas de cada categoria.

Este arquivo concentra TODO o "jeito de escrever" do laudo. Ajustar o texto
aqui muda o resultado em todas as categorias, sem mexer no resto do código.
"""

import os

from core.config import ARQUIVO_REGRAS_VALIDADAS, ROTULOS_CATEGORIA

REGRAS_GERAIS = """
Você é um vistoriador redigindo um laudo de vistoria de entrada de imóvel
residencial no Brasil. Escreva em português, seguindo rigorosamente estas
regras de formatação:

- Cada item observado é uma linha iniciada por "*".
- NÃO deixe linha em branco entre os itens — cada "*" começa logo na linha
  seguinte ao item anterior.
- Padrão de frase: "Um/Uma [item] em [material] na(s) cor(es) [cor(es)],
  com [detalhes relevantes], em bom estado."
- Se as notas do imóvel (ver abaixo) especificarem um nome de cor com
  iniciais maiúsculas (nome de catálogo/fabricante, ex.: "Branco Gelo",
  "Branco Neve", "Crômio"), reproduza esse nome EXATAMENTE como está nas
  notas — mesma capitalização, sem hifenizar, sem converter para
  minúsculo. Isso vale em TODOS os cômodos onde a nota se aplicar, sem
  exceção — não varie a grafia entre um cômodo e outro.
- Cores compostas usam hífen (ex.: marrom-claro, branco-gelo, cinza-chumbo).
- Respeite a concordância de gênero e número em português.
- Seja específico e direto — nunca use termos vagos como "aparenta",
  "possivelmente", "parece ser". Afirme o que está vendo nas fotos.
- Informe quantidades exatas quando aplicável (número de portas, gavetas,
  tomadas, etc.).
- Descreva apenas o que está de fato visível nas fotos fornecidas. Não
  invente itens, materiais ou cores que não possam ser confirmados.
- A FOTO MANDA, A NOTA ORIENTA: as informações confirmadas do imóvel (ver
  abaixo) descrevem o PADRÃO da casa, não o conteúdo de cada cômodo. Cada
  cômodo é descrito a partir das FOTOS DELE. Se a foto mostrar ACABAMENTO
  diferente do que a nota diz (a nota diz parede pintada e a foto mostra
  textura projetada, azulejo ou madeira), escreva o que a FOTO mostra, sem
  tentar encaixar a nota à força. O mesmo vale para item que existe ou não
  existe no cômodo.
  A exceção é COR informada na nota: foto tem sombra, contraluz e balanço
  de branco, e a mesma tinta aparece mais clara ou mais escura de um
  cômodo para outro. Se a nota disser a cor da parede (ou de qualquer
  acabamento), use a cor da NOTA em todos os cômodos onde ela se aplica —
  só mude se a foto mostrar outro acabamento, não por impressão de tom.
- DEFEITO NÃO SE ESPALHA: furo, trinca, mancha, mofo, quebra, risco,
  estufamento e afins só entram no texto do cômodo em que você CONSEGUE
  VER o defeito nas fotos daquele cômodo. Uma nota dizendo que as paredes
  estão "em estado regular, com furos" descreve o imóvel em geral — ela
  NÃO autoriza escrever "com furos" num cômodo cujas fotos não mostram
  furo nenhum. Sem o defeito visível, escreva "em bom estado".
- FERRAGENS (maçaneta, fechadura, dobradiças, roseta, alisares, puxadores,
  etc.): cite SOMENTE os componentes que você consegue identificar
  claramente na foto. NÃO complete o conjunto com peças que "costumam
  vir junto" (ex.: não escreva "roseta" só porque a porta tem maçaneta e
  fechadura, se a roseta em si não aparecer visível na imagem). Na
  dúvida sobre um componente específico, omita-o em vez de arriscar.
- ITENS REPETIDOS: quando houver mais de um item do MESMO tipo no cômodo,
  escreva UMA ÚNICA linha com a quantidade total, no plural — nunca uma
  linha por unidade. NUNCA use "Mais um", "Mais uma", "Mais dois" etc.
  - Iguais: "*Duas portas em madeira na cor branca, tipo lisa, com
    maçaneta cromada, em bom estado." (e não "*Uma porta..." seguida de
    "*Mais uma porta...").
  - Mesmo tipo, com algum detalhe diferente: continue numa linha só,
    usando "sendo um/uma ... e outro/outra ...": "*Dois armários em MDF
    nas cores marrom e bege, sendo um com quatro portas e outro com duas
    portas, com dobradiças metálicas e interior na cor branca, em bom
    estado."
  - Posição, tamanho ou função NÃO fazem um tipo diferente: armário
    inferior, superior, aéreo e de canto são todos "armários"; placa de
    tomada, de interruptor e placa cega são todas "placas". Ex.: "*Dois
    armários em MDF na cor [cor], sendo um inferior com [n] portas e
    outro aéreo com [n] portas, em bom estado."
  - Itens de tipos DIFERENTES (ex.: bancada e tanque) ficam em linhas
    separadas, cada uma começando com "Um/Uma" ou com a quantidade.
- TESTES: só escreva que algo foi "testado" se as informações confirmadas
  do imóvel disserem que os testes foram feitos — você não vê o teste na
  foto (no máximo, "aceso" se a luz aparecer acesa). Quando as notas
  confirmarem os testes ELÉTRICOS, todo item de Componentes Elétricos
  (pontos de iluminação, placas, quadro de disjuntores) leva "testado(s)
  e em funcionamento" antes de "em bom estado", com a concordância certa
  ("*Três placas ..., testadas e em funcionamento, em bom estado.").
  Quando confirmarem os testes HIDRÁULICOS, faça o mesmo com cada peça
  hidráulica (torneira, misturador, chuveiro, ducha, ducha higiênica,
  descarga, registro), logo depois da peça dentro da linha:
  "...torneira monocomando em metal cromado, testada e em funcionamento,
  sifão em PVC...".
  "Testado e em funcionamento" vale SÓ para esses dois grupos: item
  elétrico e peça hidráulica. NUNCA escreva isso em parede, piso, teto,
  porta, janela, soleira, rodapé, nem em mobília sem função elétrica ou
  hidráulica (armário, gabinete, bancada, espelho, box, prateleira,
  porta-toalha, porta-papel, saboneteira, cabide). Também não se testa a
  peça que só recebe água — tanque, bancada, cuba, pia: o que é testado ali
  é a torneira ou o registro. Parede não é testada:
  se as notas confirmarem os testes, isso NÃO muda o texto dessas
  categorias.
- Se a categoria não tiver nada a relatar naquele cômodo (por exemplo, um
  cômodo sem janela), responda apenas: "Não se aplica."
- Vidro de box de banheiro: use sempre o termo "vidro Blindex" (nunca
  "vidro temperado").
- ORTOGRAFIA E GRAMÁTICA: revise mentalmente cada frase antes de
  finalizar. Erro de digitação, palavra errada ou concordância errada
  (ex.: "en" em vez de "em", "suspendo" em vez de "suspenso") NUNCA pode
  aparecer no texto final — isso é inaceitável neste laudo.
- CONSISTÊNCIA ENTRE CÔMODOS: quando o mesmo tipo de acabamento aparecer
  em mais de um cômodo (ex.: parede pintada lisa na mesma cor, piso no
  mesmo material/cor, revestimento cerâmico igual), descreva com a MESMA
  estrutura de frase em todos os cômodos, mudando apenas o que realmente
  for diferente (cor, detalhes extras como rodapé). NÃO varie a fórmula
  da frase à toa (ex.: não alterne entre "Paredes com acabamento em
  pintura...", "Paredes com pintura lisa...", "Paredes em pintura..." —
  escolha uma fórmula fixa por tipo de acabamento e repita).
"""

EXEMPLOS_MOBILIA = """
Exemplos de padrão já validado (use como referência de nível de detalhe e
de formatação, não copie o conteúdo):

*Um armário em MDF nas cores marrom-claro e branca, com seis portas, sendo
três espelhadas, nichos e seis gavetas, com puxadores e pegadores
metálicos, dobradiças cromadas e corrediças cromadas, em bom estado.
*Uma bancada em mármore na cor preta, com cuba acoplada em aço inox,
sifão, torneira monocomando cromada e mangueira flexível metálica para
alimentação de água, em bom estado.
*Um painel de TV em MDF nas cores marrom e bege, com três portas
superiores com pistão, três nichos, prateleira central e três gavetas
inferiores, puxadores e corrediças metálicas, em bom estado.
*Uma cristaleira em MDF nas cores marrom e bege, com duas portas de vidro
fumê, três gavetas, interior na cor branca, puxadores e corrediças
metálicas, em bom estado.
"""

INSTRUCAO_CATEGORIA = {
    "paredes": """
Descreva as paredes do cômodo: material/acabamento (pintura, revestimento,
papel de parede, textura), cor(es) e estado de conservação (trincas,
manchas, bolhas, desgaste). Não descreva móveis nem outros itens.
O RODAPÉ NÃO entra aqui — ele é descrito na categoria Piso.
Use sempre uma destas fórmulas fixas de abertura de frase, conforme o
acabamento (nunca varie a fórmula para o mesmo tipo de acabamento):
- Parede pintada lisa: "Paredes em pintura lisa na cor [cor], em bom
  estado."
- Parede com revestimento cerâmico: "Paredes em revestimento cerâmico na
  cor [cor], em bom estado." (acrescente ", com rejunte na cor [cor]," se
  o rejunte for visível e de cor diferente do revestimento).
""",
    "piso": """
Descreva o piso do cômodo: material (porcelanato, laminado, cerâmica,
vinílico, etc.), cor e padrão (se houver), e estado de conservação
(riscos, trincas, quebras, afundamentos, desgaste, rejunte).
O RODAPÉ é descrito AQUI, junto com o piso (nunca em Paredes):
"Piso em [material] na cor [cor], com rodapé em [material] na cor [cor],
em bom estado." Se o cômodo não tiver rodapé (ex.: parede com
revestimento cerâmico até o chão), não invente um.
""",
    "teto": """
Descreva o teto do cômodo. A estrutura do teto em si é sempre de laje/
alvenaria — quando houver um forro instalado por baixo dela, descreva como
"rebaixo em gesso" (nunca use o termo genérico "forro" sozinho; use
"rebaixo em gesso", "rebaixo em gesso com sanca", etc., conforme o caso).
Se não houver rebaixo e o teto for só a laje pintada, descreva como "laje
pintada". Informe também cor e estado de conservação.
""",
    "porta": """
Descreva a(s) porta(s) de acesso do cômodo (não confundir com portas de
armários, que entram em Mobília): material, cor, tipo (lisa, frisada,
veneziana, almofadada), fechadura/maçaneta e dobradiças, estado de
conservação.

SEMPRE olhe e descreva também, em cada porta:
- o BATENTE (o marco onde a folha encosta): material e cor;
- as VISTAS (as guarnições/alizares que cobrem a junção do batente com a
  parede): material, cor e se são lisas ou trabalhadas;
- a SOLEIRA, quando houver: material e cor (ex.: soleira em granito na cor
  preta). Se a foto não mostrar soleira nenhuma no vão, não escreva que
  há uma — e também não escreva que não há.
Batente e vistas costumam ser do mesmo material e cor da folha; ainda
assim, confirme na foto antes de escrever, porque nem sempre são.
""",
    "janela": """
Descreva a(s) janela(s) do cômodo: material do caixilho (alumínio, madeira,
PVC), tipo de abertura (correr, basculante, maxim-ar), tipo de vidro, cor,
ferragens/fechos, estado de conservação e persianas ou cortinas fixas, se
houver.
""",
    "eletrico": """
Descreva os componentes elétricos visíveis do cômodo:
- Pontos de iluminação: agrupe TODOS os pontos de iluminação do cômodo em
  UMA ÚNICA frase, informando a quantidade total e o tipo (ex.: "Três
  pontos de iluminação do tipo luminária de embutir em LED, na cor
  branca, em bom estado."), mesmo que as luminárias sejam de tipos
  diferentes ("...sendo duas de embutir e uma pendente...").
- Tomadas/interruptores: TODAS as placas do cômodo numa ÚNICA linha, como
  "placas em polímero na cor [cor]", com a quantidade total e a função de
  cada uma (interruptores, tomadas, placas cegas, placas para saída de
  fios de internet/TV, etc.) — ex.: "*Cinco placas em polímero na cor
  branca, sendo duas com uma tomada, uma com um interruptor triplo e duas
  placas cegas, em bom estado." Não use o termo "espelhos" para as placas.
- Disjuntores/quadro de disjuntores, se visíveis (sobre dizer que foram
  testados, siga a regra TESTES acima).
- Estado de conservação geral dos itens acima.
""",
    "mobilia": """
Descreva TODA a mobília fixa/planejada do cômodo (armários, painéis,
cristaleiras, bancadas, prateleiras fixas e afins): material, cor(es),
número exato de portas/gavetas, se são espelhadas ou de vidro, cor do
interior das gavetas, tipo de puxador, se dobradiças e corrediças são
cromadas, e estado de conservação. NÃO descreva paredes, piso, teto,
janelas, portas de acesso ou eletrodomésticos soltos — apenas mobília.

BANHEIROS E LAVABOS: aqui a mobília inclui TODAS as louças, metais e
acessórios fixos — bancada, cuba, torneira/misturador, sifão, gabinete,
nicho, espelho, bacia sanitária (com ou sem caixa acoplada, assento e
tampa, acionamento), box (vidro Blindex), chuveiro/ducha, ducha
higiênica, registros e acessórios (porta-toalha, porta-papel,
saboneteira, cabides/ganchos). Chuveiro e ducha higiênica entram AQUI,
nunca em Componentes Elétricos. O vaso sanitário (bacia sanitária)
também é SEMPRE mobília do banheiro, BWC, suíte ou lavabo — nunca vai
para OBS nem para outra categoria. Descreva cada peça que aparecer nas
fotos, com material, cor e quantidade — é a parte do laudo de banheiro
que mais recebe atenção. Exemplo validado de mobília de banheiro:

*Uma bancada em granito na cor preta, com cuba de apoio retangular em
louça na cor branca, torneira e misturador em metal cromado, em bom estado.
*Um nicho suspenso em MDF na cor bege, com compartimento aberto, em bom
estado.
*Um espelho retangular fixado na parede sobre a bancada, em bom estado.
*Um box de banheiro com folhas em vidro Blindex incolor, trilho e puxador
em alumínio na cor prata, em bom estado.
*Uma bacia sanitária com caixa acoplada em louça na cor branca, assento e
tampa plásticos na cor branca e engate flexível metálico, em bom estado.
*Um porta-papel higiênico em metal cromado, em bom estado.
*Quatro ganchos cabideiros em metal cromado, em bom estado.
"""
    + EXEMPLOS_MOBILIA,
    "obs": """
Liste SOMENTE avarias e observações claramente relevantes que não se
encaixam nas categorias anteriores: trincas visíveis, manchas grandes,
infiltrações, itens danificados de forma perceptível, cheiros fortes, ou
qualquer ponto que realmente mereça destaque no laudo.
NÃO relate: marcas mínimas/pontuais de oxidação (ex.: pequenos pontos em
dobradiças que só aparecem olhando de perto), sujidade, poeira, cinzas ou
resíduos comuns do uso do dia a dia, nem pequenas imperfeições que só
apareceriam em exame minucioso. Na dúvida se um defeito é relevante o
bastante, só relate se ele for facilmente visível a uma pessoa observando
o cômodo normalmente — não ao aproximar a câmera do detalhe.
Se não houver nada relevante, responda apenas: "Sem observações."
""",
}


# Como o modelo deve avaliar a própria certeza em cada item. O limiar de
# corte (config.LIMIAR_CERTEZA) NÃO aparece aqui de propósito: se o modelo
# souber que abaixo de X vai para revisão, tende a responder X+1.
INSTRUCAO_CERTEZA = """
CERTEZA POR ITEM — para CADA item (cada linha do laudo) informe também:
- "motivo": o que, dentro do item, NÃO está claramente visível nas fotos e
  por quê (ex.: "roseta aparece em uma única foto, desfocada", "não dá para
  distinguir granito de mármore com essa luz"). Se tudo no item está
  claramente visível, deixe vazio.
- "certeza": de 0 a 100, coerente com o motivo. A certeza do item é a da
  afirmação MENOS segura dentro dele: se a porta é claramente de madeira
  branca mas a roseta mal aparece, a certeza do item é a da roseta.
  - 95 a 100: tudo no item está claramente visível, de preferência em mais
    de uma foto, sem ambiguidade de material, cor ou quantidade. O que vem
    das informações confirmadas do imóvel conta como 100.
  - 85 a 94: visível, mas algum detalhe saiu de uma única foto ou de um
    ângulo ruim.
  - 60 a 84: parte do item está desfocada, escura ou coberta; o material é
    ambíguo (granito x mármore, MDF x madeira maciça, porcelanato x
    cerâmica); ou a quantidade pode estar errada.
  - abaixo de 60: você está deduzindo algo que não aparece claramente (ex.:
    uma peça que "costuma vir junto").
- Isso vale também para "Não se aplica." e "Sem observações.": se as fotos
  não mostram o cômodo inteiro e você não pode afirmar que não há janela,
  porta, etc., a certeza deve ser baixa.
- Seja honesto. Um item com certeza baixa vai ser conferido por um
  vistoriador humano; um item errado com certeza alta vai direto para o
  laudo do cliente.
"""


def carregar_regras_validadas() -> list:
    """Lê as regras gerais que o vistoriador adotou via validar.py. Linhas
    vazias e linhas começando com "#" são ignoradas."""
    if not os.path.isfile(ARQUIVO_REGRAS_VALIDADAS):
        return []
    regras = []
    with open(ARQUIVO_REGRAS_VALIDADAS, "r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            regras.append(linha.lstrip("-").strip())
    return regras


# Regras injetadas por quem chama, em vez de lidas do arquivo. É o que a
# aplicação web usa: em produção as regras adotadas vivem no banco (regra 23
# do pedido), não no repositório, porque o repositório é público e porque
# várias instalações não podem escrever umas por cima das outras.
#
# `None` (o padrão) significa "leia o arquivo", que é o comportamento do CLI.
# Uma lista vazia NÃO é o mesmo que None: ela significa "nenhuma regra
# adotada", e é resposta legítima de um banco recém-criado.
_regras_injetadas: list | None = None


def definir_regras_extras(regras: list | None) -> None:
    """Define as regras adotadas sem passar pelo arquivo.

    Chamar com None devolve o comportamento de ler regras_validadas.txt."""
    global _regras_injetadas
    _regras_injetadas = None if regras is None else [
        " ".join(str(regra).split()) for regra in regras if str(regra).strip()
    ]


def regras_em_vigor() -> list:
    """As regras que vão entrar no próximo prompt, venham de onde vierem."""
    if _regras_injetadas is not None:
        return list(_regras_injetadas)
    return carregar_regras_validadas()


def _regras() -> str:
    """REGRAS_GERAIS + as regras adotadas pelo vistoriador, se houver."""
    regras = regras_em_vigor()
    if not regras:
        return REGRAS_GERAIS.strip()
    adotadas = "\n".join(f"- {regra}" for regra in regras)
    return (
        f"{REGRAS_GERAIS.strip()}\n\n"
        "REGRAS ADOTADAS PELO VISTORIADOR (validadas em vistorias anteriores; "
        "têm a mesma força das regras acima e prevalecem em caso de "
        f"conflito):\n{adotadas}"
    )


def montar_prompt_comodo(nome_comodo: str, categorias: list, notas_extras: str = "") -> str:
    """Monta UM ÚNICO prompt pedindo as 8 categorias de uma vez, com a
    resposta em JSON — troca 8 chamadas de API por cômodo por apenas 1.
    Cada categoria volta como lista de itens, cada um com a certeza do
    modelo (ver INSTRUCAO_CERTEZA).

    `notas_extras` é informação específica do imóvel em vistoria (ex.: nome
    exato da cor de tinta usada, confirmado pelo vistoriador) que ajuda o
    modelo a não precisar advinhar detalhes que a foto sozinha não garante.
    Fica de fora de REGRAS_GERAIS/INSTRUCAO_CATEGORIA porque é válida só
    para esta vistoria, não para todo laudo gerado pelo script."""
    blocos_categoria = "\n".join(
        f'- "{categoria}": {INSTRUCAO_CATEGORIA[categoria].strip()}'
        for categoria in categorias
    )

    chaves = ", ".join(f'"{categoria}"' for categoria in categorias)

    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = (
            "Informações confirmadas sobre este imóvel específico (use estes "
            "dados exatos sempre que se aplicarem, em vez de tentar advinhar "
            f"pela foto):\n{notas_extras.strip()}\n\n"
        )

    return (
        f"{_regras()}\n\n"
        f"Cômodo: {nome_comodo}\n\n"
        f"{bloco_notas}"
        "Analise todas as fotos fornecidas deste cômodo e descreva CADA uma "
        "das categorias abaixo, seguindo à risca as instruções de cada uma "
        "e o formato de escrita definido acima:\n\n"
        f"{blocos_categoria}\n\n"
        f"{INSTRUCAO_CERTEZA.strip()}\n\n"
        "IMPORTANTE — formato da resposta:\n"
        "Responda APENAS com um objeto JSON válido, sem texto antes ou "
        f"depois, sem markdown, sem ```json. Chaves: {chaves}. Cada chave é "
        "uma LISTA de itens, e cada item é um objeto com \"texto\" (UMA "
        "linha do laudo, começando com \"*\", ou exatamente \"Não se "
        "aplica.\" / \"Sem observações.\"), \"motivo\" e \"certeza\". "
        "Exemplo: {\"paredes\": [{\"texto\": \"*Paredes em pintura lisa na "
        "cor branca, em bom estado.\", \"motivo\": \"\", \"certeza\": 97}]}"
    )


def montar_prompt_revisao(laudo_json: str, categorias: list, notas_extras: str = "") -> str:
    """Monta o prompt de REVISÃO: pega um laudo já gerado (todos os cômodos
    de um imóvel, em JSON) e pede pro modelo reescrever o texto seguindo as
    regras de estilo atuais — sem olhar fotos de novo, é uma passada de
    texto puro, bem mais barata que reprocessar tudo com as imagens.

    Útil quando o style_guide muda depois que um laudo já foi gerado: em
    vez de rodar main.py de novo (gastando cota de API com as fotos), roda
    revisar.py só pra padronizar o texto já escrito com a regra nova."""
    blocos_categoria = "\n".join(
        f'- "{categoria}": {INSTRUCAO_CATEGORIA[categoria].strip()}'
        for categoria in categorias
    )

    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = (
            "Informações confirmadas sobre este imóvel específico (use estes "
            "dados exatos sempre que se aplicarem):\n"
            f"{notas_extras.strip()}\n\n"
        )

    return (
        f"{_regras()}\n\n"
        f"{bloco_notas}"
        "Abaixo está um laudo de vistoria JÁ GERADO para um imóvel inteiro, "
        "em JSON (cada chave é o nome de um cômodo; dentro de cada cômodo, "
        "uma chave por categoria com o texto já escrito):\n\n"
        f"{laudo_json}\n\n"
        "Sua tarefa é REVISAR esse texto para seguir à risca as regras de "
        "formatação acima e as instruções de cada categoria abaixo, "
        "SEM reanalisar fotos (você não tem acesso a elas nesta etapa):\n\n"
        f"{blocos_categoria}\n\n"
        "REGRAS DA REVISÃO — muito importante:\n"
        "- NÃO invente, remova nem altere fatos já observados (materiais, "
        "cores, quantidades, tipos, marcas, medidas) — mexa só na "
        "terminologia, formatação e nível de detalhe, conforme as regras.\n"
        "- A única remoção de conteúdo permitida é a de itens triviais na "
        "categoria \"obs\" que a instrução acima manda excluir (marcas "
        "mínimas de oxidação, sujidade/poeira/cinzas comuns, etc.).\n"
        "- Mantenha 'Não se aplica.' e 'Sem observações.' exatamente como "
        "estão nos cômodos/categorias onde já aparecem assim.\n"
        "- Devolva TODOS os cômodos e TODAS as categorias que vieram no "
        "JSON de entrada, no mesmo formato (cômodo -> categoria -> texto), "
        "sem pular nenhum.\n\n"
        "IMPORTANTE — formato da resposta:\n"
        "Responda APENAS com um objeto JSON válido, sem texto antes ou "
        "depois, sem markdown, sem ```json. Use \\n para separar linhas "
        "dentro do texto de cada categoria, sem linha em branco entre os "
        "itens."
    )


def montar_prompt_inventario(
    nome_comodo: str, quantidade_fotos: int, quantidade_imagens: int, notas_extras: str = ""
) -> str:
    """Passo 1 da conferência: o modelo LISTA tudo o que vê no cômodo, sem
    ver o laudo.

    Por que sem o laudo: em 22/09/2026 tentei o caminho direto — mandar as
    fotos junto com o texto pronto e pedir "aponte as divergências". O
    modelo devolveu lista vazia nos dois cômodos testados, inclusive num
    que tinha erro grosseiro (teto descrito como forro de PVC sendo laje
    pintada). Lendo o texto ele concorda com o texto. Listar o que vê, sem
    nada para concordar, ele faz bem: o mesmo cômodo devolveu 31 itens,
    com peitoril, registro e o vidro fumê do box que o laudo não tinha."""
    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = (
            "Informações confirmadas sobre este imóvel (valem como verdade):\n"
            f"{notas_extras.strip()}\n\n"
        )

    if quantidade_imagens < quantidade_fotos:
        descricao_imagens = (
            f"As imagens são {quantidade_imagens} folhas de contato: cada uma traz "
            f"VÁRIAS fotos deste cômodo lado a lado, {quantidade_fotos} fotos no "
            "total. Olhe cada miniatura."
        )
    else:
        descricao_imagens = f"São {quantidade_fotos} fotos deste cômodo."

    return (
        f"Cômodo: {nome_comodo}\n\n"
        f"{bloco_notas}"
        f"{descricao_imagens}\n\n"
        "Faça o INVENTÁRIO do cômodo: liste TUDO o que aparece nas fotos, "
        "item por item. Não é o laudo — é lista de conferência, para nada "
        "ficar de fora.\n\n"
        "Seja exaustivo, principalmente em:\n"
        "- louças e metais: bacia sanitária, cuba, torneira, chuveiro, "
        "ducha higiênica, registro, sifão, engate;\n"
        "- mobília fixa: cada armário, gabinete, bancada, prateleira, "
        "nicho, espelho, box;\n"
        "- pontos elétricos: cada ponto de luz, cada placa, quadro de "
        "disjuntores, interfone;\n"
        "- esquadrias: porta, janela, batente, vistas, soleira, peitoril;\n"
        "- acabamentos: parede, piso, teto, rodapé, faixa decorativa;\n"
        "- acessórios: porta-toalha, porta-papel, saboneteira, cabide, "
        "varal, corrimão.\n\n"
        "CUIDADO com armadilha de foto: foto tirada de lado (o cômodo "
        "aparece deitado) e REFLEXO em espelho ou vidro. Não liste como "
        "item novo o que é reflexo de algo que já está no cômodo, nem "
        "confunda uma porta fotografada deitada com um armário.\n\n"
        "Para cada item devolva a categoria (paredes, piso, teto, porta, "
        "janela, eletrico, mobilia, obs), o item em poucas palavras com "
        "material e cor, e a certeza de 0 a 100 de que ele está mesmo ali.\n\n"
        f"{INSTRUCAO_CERTEZA.strip()}\n\n"
        "Responda APENAS com um objeto JSON válido, sem markdown: "
        '{"inventario": [{"categoria": "...", "item": "...", "certeza": 0}]}'
    )


def montar_prompt_divergencias(
    nome_comodo: str, texto_laudo: str, inventario: list, notas_extras: str = ""
) -> str:
    """Passo 2 da conferência: TEXTO PURO (sem fotos, custa quase nada).
    Compara o inventário do passo 1 com o laudo já escrito e devolve o que
    não bate."""
    lista = "\n".join(
        f"- [{item.get('categoria', '?')}] {item.get('item', '')}"
        for item in inventario
    )
    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = (
            "Informações confirmadas sobre este imóvel (valem como verdade):\n"
            f"{notas_extras.strip()}\n\n"
        )

    return (
        f"{_regras()}\n\n"
        f"Cômodo: {nome_comodo}\n\n"
        f"{bloco_notas}"
        "INVENTÁRIO — o que foi visto nas fotos deste cômodo:\n"
        f"{lista}\n\n"
        "LAUDO — o texto que já está escrito para este cômodo:\n"
        "-----\n"
        f"{texto_laudo.strip()}\n"
        "-----\n\n"
        "Compare os dois e devolva SOMENTE o que não bate, de dois tipos:\n"
        '- "falta" (o mais importante): item do inventário que o laudo não '
        "descreve de jeito nenhum — ex.: um peitoril, um registro, um "
        "varal, uma prateleira. Atenção: o laudo costuma juntar vários "
        "itens numa linha só (a torneira e o sifão aparecem dentro da linha "
        "da cuba) — isso NÃO é item faltando. Só aponte o que realmente não "
        "está lá.\n"
        '- "errado": o inventário AFIRMA, sobre o mesmo item, material, '
        "cor, tipo ou quantidade diferente do que o laudo escreveu (ex.: "
        "laudo diz forro de PVC e o inventário diz laje pintada).\n\n"
        "REGRAS DA COMPARAÇÃO — leia com atenção, elas evitam estrago:\n"
        "- O inventário é uma lista rápida, MENOS detalhada que o laudo. "
        "Item que o inventário não cita NÃO é prova de que não existe. "
        "Silêncio do inventário nunca é divergência.\n"
        "- A conferência não encurta o laudo. Nunca proponha remover item, "
        'nunca sugira "Não se aplica." ou "Sem observações." como '
        "correção, e nunca troque uma linha detalhada por uma mais pobre.\n"
        "- A linha sugerida tem que MANTER tudo o que já estava na linha do "
        "laudo, mudando só o fato que conflita.\n"
        "- Defeito que já está escrito no laudo (trinca, estufamento, "
        "mancha, quebra) FICA. Ele foi confirmado por quem esteve no "
        "imóvel; não sugira tirar porque o inventário não citou.\n"
        "- Diferença só de redação (mesma coisa dita com outras palavras) "
        "NÃO é divergência.\n\n"
        "Para cada um devolva:\n"
        '- "categoria": paredes, piso, teto, porta, janela, eletrico, '
        "mobilia ou obs;\n"
        '- "tipo": "falta" ou "errado";\n'
        '- "linha_atual": em "errado", a linha do LAUDO copiada '
        'EXATAMENTE, caractere por caractere (em "falta", string vazia);\n'
        '- "linha_sugerida": a linha pronta para entrar no laudo, no padrão '
        'de escrita acima, começando com "*";\n'
        '- "o_que_vi": em uma frase, o que no inventário sustenta isso;\n'
        '- "certeza": 0 a 100.\n\n'
        "Se o laudo já cobre tudo, devolva a lista vazia.\n\n"
        "Responda APENAS com um objeto JSON válido, sem markdown: "
        '{"divergencias": [...]}'
    )


def montar_prompt_correcao(nome_comodo: str, itens: list, notas_extras: str = "") -> str:
    """Prompt da SEGUNDA OLHADA: as mesmas fotos do cômodo, mas focado só
    nos itens que saíram com certeza muito baixa (até
    config.LIMIAR_CORRECAO_AUTOMATICA). Na primeira passada o modelo olha o
    cômodo inteiro e divide a atenção entre 8 categorias; aqui ele olha
    poucos itens de cada vez, sabendo exatamente qual era a dúvida.

    `itens` é uma lista de {"rotulo", "texto", "motivo"}, na ordem em que a
    resposta tem que voltar — ver gemini_client._corrigir_itens_incertos."""
    lista = "\n\n".join(
        f"{numero}. Categoria: {item['rotulo']}\n"
        f"   Texto atual: {item['texto']}\n"
        f"   Dúvida que você mesmo apontou: {item['motivo'] or '(não informada)'}"
        for numero, item in enumerate(itens, start=1)
    )

    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = (
            "Informações confirmadas sobre este imóvel específico (use estes "
            "dados exatos sempre que se aplicarem, em vez de tentar advinhar "
            f"pela foto):\n{notas_extras.strip()}\n\n"
        )

    return (
        f"{_regras()}\n\n"
        f"Cômodo: {nome_comodo}\n\n"
        f"{bloco_notas}"
        "Você já descreveu este cômodo a partir destas mesmas fotos, e os "
        "itens abaixo saíram com certeza muito baixa. Olhe as fotos de novo, "
        "agora só para eles, e resolva a dúvida de cada um:\n\n"
        f"{lista}\n\n"
        "Para cada item, procure nas fotos o detalhe que faltava e reescreva "
        "a linha do laudo. Regras da reescrita:\n"
        "- Se as fotos mostrarem o detalhe, escreva a linha completa e "
        "correta, com a certeza alta que isso merece.\n"
        "- Se as fotos NÃO mostrarem, tire da linha a parte que você não "
        "consegue confirmar, em vez de advinhar: uma linha mais curta e "
        "verdadeira vale mais do que uma detalhada e errada.\n"
        "- Se o item não existir mesmo no cômodo, responda exatamente "
        '"Não se aplica." (ou "Sem observações.", na categoria OBS).\n'
        "- Não mude nada que já estava certo, e não descreva outros itens "
        "do cômodo: responda só sobre os que estão na lista.\n\n"
        f"{INSTRUCAO_CERTEZA.strip()}\n\n"
        "IMPORTANTE — formato da resposta:\n"
        "Responda APENAS com um objeto JSON válido, sem texto antes ou "
        'depois, sem markdown, sem ```json: {"itens": [...]}, com '
        f"EXATAMENTE {len(itens)} item(ns), na MESMA ORDEM da lista acima. "
        'Cada item é um objeto com "texto" (uma linha do laudo, começando '
        'com "*"), "motivo" (o que ainda ficou duvidoso, ou "" se nada '
        'ficou) e "certeza".'
    )


def montar_prompt_consolidacao(rotulo_categoria: str, texto_categoria: str) -> str:
    """Prompt de TEXTO PURO (sem fotos, barato) para consertar uma categoria
    que violou a regra de ITENS REPETIDOS (o mesmo item em várias linhas, ou
    "Mais um/uma..."). Só é usado quando o modelo desobedece — ver
    gemini_client._consolidar_repetidos."""
    return (
        f"{_regras()}\n\n"
        f'Abaixo estão as linhas da categoria "{rotulo_categoria}" de um '
        "cômodo, já escritas, mas violando a regra de ITENS REPETIDOS (o "
        "mesmo tipo de item aparece em mais de uma linha, e/ou há linhas "
        'começando com "Mais um", "Mais uma" etc.):\n\n'
        f"{texto_categoria}\n\n"
        "Reescreva essas linhas corrigindo SOMENTE isso:\n"
        "- Linhas que descrevem o MESMO tipo de item viram uma linha só, com "
        "a quantidade total no plural (e \"sendo um/uma ... e outro/outra "
        '..." se algum detalhe for diferente entre eles). Posição, tamanho '
        "ou função não fazem um tipo diferente (armário inferior e superior "
        "são armários; placa de tomada e placa cega são placas).\n"
        '- Se a linha com "Mais um/uma" descreve um item de tipo DIFERENTE '
        'da linha anterior, apenas troque o começo por "Um/Uma".\n'
        "- Não invente, não remova e não altere nenhum fato (material, cor, "
        "quantidade, estado de conservação). Mantenha idênticas as linhas "
        "que não precisam mudar.\n\n"
        "Responda APENAS com um objeto JSON válido, sem markdown: "
        '{"linhas": ["*...", "*..."]} — uma string por linha do laudo.'
    )


# ==========================================================================
# ESCOPO E EVIDÊNCIAS (desde 25/09/2026)
#
# Os dois prompts abaixo substituem o caminho direto "fotos -> laudo" pelo
# caminho "fotos -> evidências -> (código valida escopo) -> laudo".
#
# O primeiro NÃO pede texto de laudo: pede observação crua e, para cada uma,
# duas confianças separadas — "está claro na imagem?" e "é deste cômodo?".
# O segundo escreve o laudo SEM ver as fotos, só com as evidências que o
# código aprovou. É assim que uma parede de corredor deixa de conseguir
# chegar ao texto da cozinha: ela nem é oferecida a quem escreve.
# ==========================================================================

INSTRUCAO_ESCOPO = """
ESCOPO — a pergunta mais importante desta etapa.

Estas fotos foram guardadas na pasta de um cômodo, mas ESTAR NA PASTA NÃO
PROVA NADA. Fotógrafo enquadra o que cabe no visor: a foto da cozinha pega a
porta, e pela porta se vê o corredor; o espelho do banheiro reflete o quarto;
a última foto do quarto pega meia parede da sala.

Para CADA foto, classifique em "escopo":
- "valid": a foto é predominantemente do cômodo alvo e o que ela mostra pode
  ser atribuído a ele.
- "partial": a foto mostra o cômodo alvo, mas também mostra ambiente vizinho,
  reflexo de outro ambiente, ou região que você não consegue atribuir com
  segurança.
- "out_of_scope": a foto não é do cômodo alvo (foi parar na pasta errada, ou
  é uma foto de outro ambiente tirada da porta).

Informe também:
- "relevancia" (0-100): o quanto desta foto é útil para descrever o cômodo alvo.
- "ambiente_adjacente" (true/false): aparece parte de outro ambiente.
- "reflexo" (true/false): há espelho ou vidro refletindo outro ambiente.
- "motivo": em uma frase, o que te fez classificar assim.

Nenhuma foto é apagada por causa disso — a classificação só controla o que
pode virar afirmação sobre este cômodo.
"""

INSTRUCAO_EVIDENCIAS = """
EVIDÊNCIAS — o que você viu, ainda NÃO é texto de laudo.

Liste cada coisa observada como uma evidência separada e crua. Não escreva
frase de laudo aqui, não use "*", não junte itens, não conte totais entre
fotos: isso é feito depois, por outra etapa, com todas as evidências na mão.
Descreva o que está NAQUELA foto.

Para cada evidência informe:
- "foto_indice": o número da foto onde você viu isso.
- "categoria": uma de paredes, piso, teto, porta, janela, eletrico, mobilia, obs.
- "observacao": o que é, com material, cor, quantidade e estado que você
  consegue ver NESTA foto. Se o material é ambíguo, diga que é ambíguo em vez
  de escolher um.
- "confianca_percepcao" (0-100): o quanto ESTA IMAGEM deixa claro o que é.
  Desfoque, sombra, distância e oclusão derrubam este número.
- "confianca_escopo" (0-100): o quanto você tem certeza de que isto PERTENCE
  ao cômodo alvo, e não a um ambiente vizinho, a um reflexo, ou ao outro lado
  de uma porta aberta.
  ATENÇÃO: estes dois números são independentes. Uma parede de corredor pode
  estar nitidíssima na foto da cozinha — percepção 99, escopo 10. Não repita
  o mesmo número nos dois campos por hábito.
- "ambiente_adjacente" (true/false): isto está em ambiente vizinho, não no
  cômodo alvo.
- "reflexo" (true/false): isto é a imagem refletida num espelho ou vidro, e
  não o objeto real. Na dúvida entre objeto real e reflexo, marque true: o
  objeto real vai aparecer em outra foto, e contar duas vezes é pior.
- "regiao" (opcional): onde está na foto, em fração do lado, com x, y, largura
  e altura entre 0 e 1. Se você não souber com segurança, OMITA o campo. NÃO
  invente uma região — uma região errada é pior do que região nenhuma.

Regra que vale acima de todas nesta etapa: é melhor deixar de registrar uma
evidência do que registrar uma que pertence a outro ambiente. O que você não
registrar pode ser recuperado depois pela conferência; o que entrar errado vai
para um documento assinado.
"""


def montar_prompt_escopo(nome_comodo: str, quantidade_fotos: int,
                         notas_extras: str = "") -> str:
    """Passo 1 do motor novo: classificar as fotos e extrair evidências cruas.

    Repare no que este prompt NÃO faz: ele não pede texto de laudo, não
    menciona formato de item, não fala em "*". Pedir as duas coisas na mesma
    chamada foi o erro da arquitetura antiga — o modelo entra em modo
    "redator" e passa a justificar a frase bonita em vez de julgar se aquilo
    é mesmo do cômodo."""
    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = (
            "Informações confirmadas sobre este imóvel (contexto; elas "
            "descrevem o PADRÃO da casa, não o conteúdo deste cômodo):\n"
            f"{notas_extras.strip()}\n\n"
        )

    return (
        "Você está examinando fotos de uma vistoria de imóvel residencial no "
        "Brasil. Esta etapa NÃO escreve laudo: ela separa o que pertence ao "
        "cômodo do que não pertence.\n\n"
        f"Cômodo alvo: {nome_comodo}\n"
        f"Foram enviadas {quantidade_fotos} foto(s), numeradas de 1 a "
        f"{quantidade_fotos} na ordem em que aparecem.\n\n"
        f"{bloco_notas}"
        f"{INSTRUCAO_ESCOPO.strip()}\n\n"
        f"{INSTRUCAO_EVIDENCIAS.strip()}\n\n"
        "IMPORTANTE — formato da resposta:\n"
        "Responda APENAS com um objeto JSON válido, sem markdown, com as "
        'chaves "fotos" e "evidencias". "fotos" tem um objeto por foto '
        'enviada, na ordem, com o campo "indice" de 1 a '
        f"{quantidade_fotos}."
    )


def montar_prompt_consolidacao_evidencias(
    nome_comodo: str,
    categorias: list,
    evidencias_por_categoria: dict,
    cobertura_incompleta: bool,
    notas_extras: str = "",
) -> str:
    """Passo 2 do motor novo: escrever o laudo do cômodo A PARTIR DAS
    EVIDÊNCIAS APROVADAS — sem as fotos.

    Tirar as fotos daqui é deliberado (regra 15 do pedido). Com as imagens na
    mão, o modelo volta a descrever o que vê, inclusive o que o código acabou
    de descartar por ser de outro ambiente; sem elas, ele só pode escrever
    sobre o que passou pela validação de escopo. O filtro deixa de ser um
    pedido no prompt e vira uma propriedade do que chega até ele.

    É uma chamada de TEXTO PURO, sem imagem — a parte cara continua sendo o
    passo 1, que manda as fotos uma vez só."""
    blocos_categoria = "\n".join(
        f'- "{categoria}": {INSTRUCAO_CATEGORIA[categoria].strip()}'
        for categoria in categorias
    )

    linhas_evidencia = []
    for categoria in categorias:
        evidencias = evidencias_por_categoria.get(categoria, [])
        rotulo = ROTULOS_CATEGORIA[categoria]
        if not evidencias:
            linhas_evidencia.append(f"{rotulo}: (nenhuma evidência aprovada)")
            continue
        itens = "\n".join(
            f"  - [{evidencia.id}] foto {evidencia.foto_id}: {evidencia.observacao} "
            f"(confiança {evidencia.confianca_final})"
            + (f" — corroborada por {len(evidencia.corroborada_por)} outra(s) foto(s)"
               if evidencia.corroborada_por else "")
            for evidencia in evidencias
        )
        linhas_evidencia.append(f"{rotulo}:\n{itens}")
    bloco_evidencias = "\n".join(linhas_evidencia)

    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = (
            "Informações confirmadas sobre este imóvel (use estes dados exatos "
            "sempre que se aplicarem, em vez de advinhar):\n"
            f"{notas_extras.strip()}\n\n"
        )

    aviso_cobertura = ""
    if cobertura_incompleta:
        aviso_cobertura = (
            "COBERTURA INCOMPLETA: as fotos não cobrem este cômodo por "
            "inteiro. Você NÃO pode concluir que algo não existe só porque "
            'não há evidência dele. Se for usar "Não se aplica." numa '
            "categoria, dê certeza BAIXA — quem confere é o vistoriador, no "
            "imóvel.\n\n"
        )

    chaves = ", ".join(f'"{categoria}"' for categoria in categorias)
    return (
        f"{_regras()}\n\n"
        f"Cômodo: {nome_comodo}\n\n"
        f"{bloco_notas}"
        "Abaixo estão as EVIDÊNCIAS já validadas deste cômodo. Elas passaram "
        "por uma etapa que separou o que pertence a este cômodo do que "
        "pertence a ambiente vizinho ou é reflexo — o que foi descartado NÃO "
        "está nesta lista e não deve aparecer no laudo.\n\n"
        f"{bloco_evidencias}\n\n"
        f"{aviso_cobertura}"
        "REGRAS DESTA ETAPA — muito importante:\n"
        "- Escreva o laudo APENAS a partir das evidências acima. Você não tem "
        "as fotos nesta etapa e não deve supor nada além do que está listado.\n"
        "- NÃO acrescente material, cor, quantidade, defeito, ferragem, "
        "equipamento ou item que não apareça nas evidências. Se as evidências "
        "não bastam para afirmar algo, deixe de fora.\n"
        "- Várias evidências podem descrever o MESMO item visto em fotos "
        "diferentes — junte-as numa linha só, não repita o item. Este é o "
        "lugar certo para contar totais.\n"
        "- Evidência com confiança baixa vira item com certeza baixa, não "
        "vira afirmação segura.\n"
        "- Se as evidências de uma categoria se contradizem, escreva a versão "
        "que as evidências sustentam melhor e dê certeza baixa ao item — não "
        "invente uma média entre as duas.\n\n"
        "Instruções de cada categoria:\n\n"
        f"{blocos_categoria}\n\n"
        f"{INSTRUCAO_CERTEZA.strip()}\n\n"
        "IMPORTANTE — formato da resposta:\n"
        "Responda APENAS com um objeto JSON válido, sem texto antes ou "
        f"depois, sem markdown. Chaves: {chaves}. Cada chave é uma LISTA de "
        'itens, e cada item é um objeto com "texto" (UMA linha do laudo, '
        'começando com "*", ou exatamente "Não se aplica." / "Sem '
        'observações."), "motivo" e "certeza".'
    )


# ==========================================================================
# ESCOPO E EVIDÊNCIAS — V2 (desde 25/09/2026)
#
# A V1 mostrou, no benchmark de 107 fotos, que separar "o que vi" de "isso é
# daqui" acerta mais fatos que o caminho direto foto -> laudo. E mostrou dois
# defeitos, que estes prompts atacam:
#
#   - ela resumia. Porta-papel, ganchos e toalheiro sumiram. Daí o pedido de
#     inventário EXAUSTIVO, item por item, instância por instância;
#   - ela tratava elemento de fronteira como ambiente vizinho. Daí a
#     taxonomia de escopo com ROOM_BOUNDARY, explicada com os exemplos que
#     de fato deram errado.
# ==========================================================================

INSTRUCAO_ESCOPO_V2 = """
ESCOPO — a pergunta mais importante desta etapa.

Estas fotos foram guardadas na pasta de um cômodo, mas ESTAR NA PASTA NÃO
PROVA NADA. O fotógrafo enquadra o que cabe no visor: a foto da cozinha pega a
porta, e pela porta se vê o corredor; o espelho do banheiro reflete o quarto.

Para CADA foto, classifique em "escopo":
- "valid": a foto é predominantemente do cômodo alvo.
- "partial": mostra o cômodo alvo, mas também ambiente vizinho, reflexo ou
  região que você não consegue atribuir com segurança.
- "out_of_scope": não é do cômodo alvo.

Informe também "relevancia" (0-100), "ambiente_adjacente", "reflexo" e
"motivo" em uma frase.

Nenhuma foto é apagada por causa disso.
"""

INSTRUCAO_EVIDENCIAS_V2 = """
EVIDÊNCIAS — inventário EXAUSTIVO, não resumo.

Liste CADA coisa visualmente identificável como uma evidência separada. Esta
etapa não escreve laudo: não use "*", não junte itens, não conte totais entre
fotos, não escreva frase de laudo. Descreva o que está NAQUELA foto.

EXAUSTIVIDADE — leia com atenção, é o ponto desta etapa.
Não resuma um conjunto numa evidência só. "Acessórios do banheiro" é resposta
errada. Num banheiro, cada um destes é uma evidência própria quando aparecer:
bacia sanitária; caixa acoplada; assento; tampa; acionamento da descarga;
bancada; cuba; torneira; sifão; engate; gabinete; espelho; nicho; box;
chuveiro; ducha higiênica; cada registro; porta-papel; porta-toalha; cada
gancho; saboneteira; porta-shampoo; prateleira. Peça pequena fixada na parede
é a que mais se perde — procure-a de propósito.

ESCOPO DE CADA EVIDÊNCIA — campo "escopo", com um destes valores:
- "room_interior": está dentro do cômodo alvo.
- "room_boundary": é ESTRUTURA DO CÔMODO na divisa com outro ambiente.
  Use este valor para porta, folha, batente, vistas, guarnição, SOLEIRA,
  janela, porta-janela, PEITORIL, esquadria, caixilho e trilho.
  ATENÇÃO — este é o erro mais comum nesta etapa: essas peças mostram o outro
  lado por natureza, e mesmo assim PERTENCEM ao cômodo. A soleira continua
  sendo do cômodo mesmo dividindo dois pisos diferentes. A porta-janela
  continua sendo do cômodo mesmo dando para a varanda. O peitoril continua
  sendo do cômodo mesmo mostrando a rua. NÃO classifique nada disso como
  "adjacent_room".
- "adjacent_room": é de OUTRO ambiente, visto daqui (a parede do corredor
  vista pela porta aberta, o móvel do quarto visto do banheiro).
- "outside": é a área externa — o telhado do vizinho, o jardim, a rua. Ou
  seja, o CENÁRIO visto através da abertura, não a abertura.
- "reflection": é a imagem refletida num espelho ou vidro, não o objeto real.
  Na dúvida entre objeto real e reflexo, use "reflection": o objeto real vai
  aparecer em outra foto, e contar duas vezes é pior.
- "ambiguous": você não conseguiu decidir.

CONFIANÇAS — dois números INDEPENDENTES:
- "confianca_percepcao" (0-100): o quanto ESTA IMAGEM deixa claro o que é.
  Desfoque, sombra, distância e oclusão derrubam este número.
- "confianca_escopo" (0-100): o quanto você tem certeza da classificação de
  escopo acima.
  Uma parede de corredor pode estar nitidíssima na foto da cozinha: percepção
  99, escopo 10. Não repita o mesmo número nos dois campos por hábito.

ATRIBUTOS — campo "atributos", um objeto com as chaves que você conseguir
preencher, cada uma com UM valor curto:
  "material", "cor", "acabamento", "rejunte_material", "rejunte_cor",
  "tipo", "estado", "defeito".
Separe o que é de coisas diferentes: numa parede de azulejo branco com rejunte
cinza, "cor" é branca e "rejunte_cor" é cinza — não misture os dois.
Preencha só o que você vê. Material ambíguo: deixe "material" de fora e diga
na observação que é ambíguo, em vez de escolher um.

INSTÂNCIA — campo "instancia": quando o mesmo tipo de coisa aparece várias
vezes, numere (1, 2, 3...) e faça uma evidência para cada. Isso vale
especialmente para placas elétricas, tomadas, interruptores, gavetas, portas
de armário e ganchos.

REGIÃO — campo "regiao", opcional: x, y, largura e altura entre 0 e 1. Se você
não souber com segurança, OMITA. Região errada é pior que região nenhuma.

Regra que vale acima de todas nesta etapa: é melhor deixar de registrar uma
evidência do que registrar uma que pertence a outro ambiente. Mas NÃO deixe
de registrar uma peça pequena do próprio cômodo — é o erro oposto, e ele
também chega ao documento assinado.
"""


def montar_prompt_escopo_v2(nome_comodo: str, quantidade_fotos: int,
                            notas_extras: str = "") -> str:
    """Passo 1 da V2: classificar as fotos e extrair evidências exaustivas.

    Repare no que este prompt NÃO faz: não pede texto de laudo, não menciona
    formato de item, não fala em "*". Pedir as duas coisas na mesma chamada
    foi o erro da arquitetura original — o modelo entra em modo "redator" e
    passa a justificar a frase bonita em vez de julgar se aquilo é do cômodo."""
    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = (
            "Informações confirmadas sobre este imóvel (contexto; elas "
            "descrevem o PADRÃO da casa, não o conteúdo deste cômodo):\n"
            f"{notas_extras.strip()}\n\n"
        )

    return (
        "Você está examinando fotos de uma vistoria de imóvel residencial no "
        "Brasil. Esta etapa NÃO escreve laudo: ela separa o que pertence ao "
        "cômodo do que não pertence, e lista exaustivamente o que há.\n\n"
        f"Cômodo alvo: {nome_comodo}\n"
        f"Foram enviadas {quantidade_fotos} foto(s), numeradas de 1 a "
        f"{quantidade_fotos} na ordem em que aparecem.\n\n"
        f"{bloco_notas}"
        f"{INSTRUCAO_ESCOPO_V2.strip()}\n\n"
        f"{INSTRUCAO_EVIDENCIAS_V2.strip()}\n\n"
        "IMPORTANTE — formato da resposta:\n"
        "Responda APENAS com um objeto JSON válido, sem markdown, com as "
        'chaves "fotos" e "evidencias". "fotos" tem um objeto por foto '
        f'enviada, com "indice" de 1 a {quantidade_fotos}.'
    )


def montar_prompt_segunda_olhada_dirigida(
    nome_comodo: str, quantidade_fotos: int, instrucao: str,
    procurando: list, notas_extras: str = "",
) -> str:
    """Segunda olhada DIRIGIDA (pedido, item 23).

    Quando a checklist de cobertura aponta um tipo sem evidência, não se
    reprocessa o cômodo inteiro: manda-se o modelo olhar as mesmas fotos
    procurando SÓ aquilo. É mais barato e acha mais — atenção dividida entre
    oito categorias é o que faz o porta-papel sumir.

    O resultado são EVIDÊNCIAS novas, nunca texto de laudo."""
    alvos = "; ".join(procurando)
    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = f"Contexto do imóvel:\n{notas_extras.strip()}\n\n"

    return (
        "Segunda passagem nas MESMAS fotos de uma vistoria, agora com um alvo "
        "único.\n\n"
        f"Cômodo alvo: {nome_comodo}\n"
        f"Foram enviadas {quantidade_fotos} foto(s), numeradas de 1 a "
        f"{quantidade_fotos}.\n\n"
        f"{bloco_notas}"
        f"TAREFA: {instrucao}\n\n"
        f"O que a primeira passagem não encontrou: {alvos}.\n\n"
        "Se você encontrar, registre uma evidência POR OBJETO, com a mesma "
        "estrutura de sempre. Se NÃO encontrar, devolva a lista vazia — não "
        "invente para preencher a lacuna. Ausência de evidência é uma resposta "
        "legítima e é melhor que um item inventado num documento assinado.\n\n"
        f"{INSTRUCAO_EVIDENCIAS_V2.strip()}\n\n"
        "IMPORTANTE — formato da resposta:\n"
        'Responda APENAS com um objeto JSON válido, com a chave "evidencias".'
    )


def montar_prompt_consolidacao_v2(
    nome_comodo: str, categorias: list, evidencias_por_categoria: dict,
    cobertura_incompleta: bool, tipos_eletricos: list,
    estado_rodape: str = "", notas_extras: str = "",
) -> str:
    """Passo final da V2: escrever o laudo A PARTIR DAS EVIDÊNCIAS APROVADAS,
    sem as fotos.

    Tirar as imagens daqui é deliberado (item 32). Com elas na mão, o modelo
    volta a descrever o que vê, inclusive o que o código acabou de descartar
    por ser de outro ambiente. Sem elas, o filtro deixa de ser um pedido no
    prompt e vira propriedade do que chega até ele.

    A estrutura que chega é rica de propósito: atributos, instâncias e
    confiança. A V1 entregava só o texto da observação, e o redator perdia
    "dobradiça dourada" para "dobradiças metálicas"."""
    blocos_categoria = "\n".join(
        f'- "{categoria}": {INSTRUCAO_CATEGORIA[categoria].strip()}'
        for categoria in categorias
    )

    linhas = []
    for categoria in categorias:
        evidencias = evidencias_por_categoria.get(categoria, [])
        rotulo = ROTULOS_CATEGORIA[categoria]
        if not evidencias:
            linhas.append(f"{rotulo}: (nenhuma evidência aprovada)")
            continue
        itens = []
        for evidencia in evidencias:
            atributos = ", ".join(
                f"{chave}={valor}" for chave, valor in sorted(evidencia.atributos.items())
            )
            marcas = []
            if evidencia.e_fronteira:
                marcas.append("estrutura de divisa do cômodo")
            if evidencia.corroborada_por:
                marcas.append(f"visto em +{len(evidencia.corroborada_por)} foto(s)")
            if evidencia.atributos_em_conflito:
                marcas.append("as fotos divergem em: "
                              + ", ".join(evidencia.atributos_em_conflito))
            itens.append(
                f"  - [{evidencia.id}] foto {evidencia.foto_id}"
                f" (inst. {evidencia.instancia}, confiança {evidencia.confianca_final})"
                f": {evidencia.observacao}"
                + (f"\n      atributos: {atributos}" if atributos else "")
                + (f"\n      obs.: {'; '.join(marcas)}" if marcas else "")
            )
        linhas.append(f"{rotulo} ({len(evidencias)} evidência(s)):\n" + "\n".join(itens))
    bloco_evidencias = "\n".join(linhas)

    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = (
            "Informações confirmadas sobre este imóvel (use estes dados exatos "
            "sempre que se aplicarem, em vez de advinhar):\n"
            f"{notas_extras.strip()}\n\n"
        )

    aviso_cobertura = ""
    if cobertura_incompleta:
        aviso_cobertura = (
            "COBERTURA INCOMPLETA: as fotos não cobrem este cômodo por "
            "inteiro. Você NÃO pode concluir que algo não existe só porque "
            'não há evidência dele. Se for usar "Não se aplica." numa '
            "categoria, dê certeza BAIXA.\n\n"
        )

    bloco_rodape = ""
    if estado_rodape == "baseboard_absent":
        bloco_rodape = (
            "RODAPÉ: as evidências indicam que NÃO há rodapé neste cômodo (o "
            "revestimento da parede desce até o piso). NÃO escreva rodapé.\n\n"
        )
    elif estado_rodape == "baseboard_not_visible":
        bloco_rodape = (
            "RODAPÉ: a junção entre parede e piso não aparece nas fotos. NÃO "
            "afirme que há rodapé nem que não há — omita o assunto.\n\n"
        )

    bloco_eletrico = ""
    if tipos_eletricos:
        bloco_eletrico = (
            "COMPONENTES ELÉTRICOS — regra própria, diferente das demais "
            "categorias.\n"
            "Os tipos encontrados neste cômodo foram: "
            + ", ".join(tipos_eletricos) + ".\n"
            "O que importa aqui é NOMEAR OS TIPOS e a composição, não contar "
            "unidades. NÃO é obrigatório escrever \"sete placas\", \"duas "
            "tomadas\" ou \"três interruptores\": a contagem de placas quase "
            "sempre sai errada e deixa a frase pior. Prefira a composição, no "
            "espírito de \"com placas em polímero na cor branca, sendo "
            "tomadas, interruptores e placa cega\" — sem copiar esse exemplo "
            "ao pé da letra.\n"
            "Só escreva quantidade de item elétrico quando ela estiver "
            "claramente determinada E for realmente útil (por exemplo, o "
            "número de pontos de iluminação do teto).\n"
            "Cuidado: \"tomada dupla\", \"interruptor triplo\" e \"módulo\" "
            "são CONFIGURAÇÕES da peça, não quantidade de placas.\n\n"
        )

    chaves = ", ".join(f'"{categoria}"' for categoria in categorias)
    return (
        f"{_regras()}\n\n"
        f"Cômodo: {nome_comodo}\n\n"
        f"{bloco_notas}"
        "Abaixo estão as EVIDÊNCIAS já validadas deste cômodo. Elas passaram "
        "por uma etapa que separou o que pertence a este cômodo do que "
        "pertence a ambiente vizinho ou é reflexo — o que foi descartado NÃO "
        "está nesta lista e não deve aparecer no laudo.\n\n"
        f"{bloco_evidencias}\n\n"
        f"{aviso_cobertura}{bloco_rodape}{bloco_eletrico}"
        "REGRAS DESTA ETAPA — muito importante:\n"
        "- Escreva o laudo APENAS a partir das evidências acima. Você não tem "
        "as fotos nesta etapa e não deve supor nada além do que está listado.\n"
        "- NÃO acrescente material, cor, quantidade, defeito, ferragem, "
        "equipamento ou item que não apareça nas evidências.\n"
        "- NÃO PERCA DETALHE. Se a evidência diz \"dobradiça metálica "
        "dourada\", escreva dourada — não troque por \"metálica\". Se diz "
        "\"porta almofadada\", não escreva \"lisa\". Se diz \"banheira de "
        "hidromassagem\", não escreva só \"banheira\". O atributo mais "
        "específico sustentado pela evidência é o que vai para o laudo.\n"
        "- NÃO DEIXE ITEM DE FORA. Cada evidência aprovada tem que aparecer "
        "em alguma linha. Peça pequena (porta-papel, gancho, saboneteira, "
        "porta-toalha) é item de laudo como qualquer outro — não agrupe em "
        "\"acessórios\" nem omita por ser pequena.\n"
        "- Várias evidências podem descrever o MESMO objeto visto em fotos "
        "diferentes — junte-as numa linha só. Evidências com instâncias "
        "diferentes são objetos diferentes.\n"
        "- Quando a quantidade for relevante e estiver clara (portas, "
        "janelas, armários, gavetas, peças de mobília), preserve-a. Se estiver "
        "incerta, descreva sem número em vez de chutar.\n"
        "- Evidência com confiança baixa vira item com certeza baixa.\n"
        "- Se as evidências divergem num atributo, escolha a melhor "
        "sustentada e dê certeza baixa ao item; os demais atributos "
        "continuam valendo.\n\n"
        "Instruções de cada categoria:\n\n"
        f"{blocos_categoria}\n\n"
        f"{INSTRUCAO_CERTEZA.strip()}\n\n"
        "IMPORTANTE — formato da resposta:\n"
        "Responda APENAS com um objeto JSON válido, sem texto antes ou "
        f"depois, sem markdown. Chaves: {chaves}. Cada chave é uma LISTA de "
        'itens, e cada item é um objeto com "texto" (UMA linha do laudo, '
        'começando com "*", ou exatamente "Não se aplica." / "Sem '
        'observações."), "motivo" e "certeza".'
    )
