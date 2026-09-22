"""
Guia de estilo do laudo — define o padrão de escrita que o modelo deve seguir
e as instruções específicas de cada categoria.

Este arquivo concentra TODO o "jeito de escrever" do laudo. Ajustar o texto
aqui muda o resultado em todas as categorias, sem mexer no resto do código.
"""

import os

from config import ARQUIVO_REGRAS_VALIDADAS

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
  descarga, registro, tanque), logo depois da peça dentro da linha:
  "...torneira monocomando em metal cromado, testada e em funcionamento,
  sifão em PVC...".
  "Testado e em funcionamento" vale SÓ para esses dois grupos: item
  elétrico e peça hidráulica. NUNCA escreva isso em parede, piso, teto,
  porta, janela, soleira, rodapé, nem em mobília sem função elétrica ou
  hidráulica (armário, gabinete, bancada, espelho, box, prateleira,
  porta-toalha, porta-papel, saboneteira, cabide). Parede não é testada:
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
armários, que entram em Mobília): material, cor, tipo (lisa, veneziana,
almofadada), fechadura/maçaneta e dobradiças, estado de conservação.
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
nunca em Componentes Elétricos. Descreva cada peça que aparecer nas
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


def _regras() -> str:
    """REGRAS_GERAIS + as regras adotadas pelo vistoriador, se houver."""
    regras = carregar_regras_validadas()
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
