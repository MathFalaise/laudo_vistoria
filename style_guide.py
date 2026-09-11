"""
Guia de estilo do laudo — define o padrão de escrita que o modelo deve seguir
e as instruções específicas de cada categoria.

Este arquivo concentra TODO o "jeito de escrever" do laudo. Ajustar o texto
aqui muda o resultado em todas as categorias, sem mexer no resto do código.
"""

REGRAS_GERAIS = """
Você é um vistoriador redigindo um laudo de vistoria de entrada de imóvel
residencial no Brasil. Escreva em português, seguindo rigorosamente estas
regras de formatação:

- Cada item observado é uma linha iniciada por "*".
- NÃO deixe linha em branco entre os itens — cada "*" começa logo na linha
  seguinte ao item anterior.
- Padrão de frase: "Um/Uma [item] em [material] na(s) cor(es) [cor(es)],
  com [detalhes relevantes], em bom estado."
- Cores compostas usam hífen (ex.: marrom-claro, branco-gelo, cinza-chumbo).
- Respeite a concordância de gênero e número em português.
- Seja específico e direto — nunca use termos vagos como "aparenta",
  "possivelmente", "parece ser". Afirme o que está vendo nas fotos.
- Informe quantidades exatas quando aplicável (número de portas, gavetas,
  tomadas, etc.).
- Descreva apenas o que está de fato visível nas fotos fornecidas. Não
  invente itens, materiais ou cores que não possam ser confirmados.
- Se dois ou mais itens forem idênticos ou muito parecidos, agrupe usando
  "Mais um/uma [item]..." em vez de repetir a descrição inteira.
- Se a categoria não tiver nada a relatar naquele cômodo (por exemplo, um
  cômodo sem janela), responda apenas: "Não se aplica."
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
""",
    "piso": """
Descreva o piso do cômodo: material (porcelanato, laminado, cerâmica,
vinílico, etc.), cor e padrão (se houver), e estado de conservação
(riscos, trincas, desgaste, rejunte).
""",
    "teto": """
Descreva o teto do cômodo: tipo (laje pintada, forro de gesso, sanca,
forro de PVC), cor e estado de conservação.
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
Descreva os componentes elétricos visíveis do cômodo: tomadas e
interruptores (quantidade e tipo), pontos de luz, disjuntores visíveis,
informando se foram testados e se estão funcionando, e estado de
conservação.
""",
    "mobilia": """
Descreva TODA a mobília fixa/planejada do cômodo (armários, painéis,
cristaleiras, bancadas, prateleiras fixas e afins): material, cor(es),
número exato de portas/gavetas, se são espelhadas ou de vidro, cor do
interior das gavetas, tipo de puxador, se dobradiças e corrediças são
cromadas, e estado de conservação. NÃO descreva paredes, piso, teto,
janelas, portas de acesso ou eletrodomésticos soltos — apenas mobília.
"""
    + EXEMPLOS_MOBILIA,
    "obs": """
Liste observações relevantes que não se encaixam nas categorias
anteriores: avarias, manchas, infiltrações, itens danificados, cheiros,
ou qualquer ponto que mereça destaque no laudo. Se não houver nada
relevante, responda apenas: "Sem observações."
""",
}


def montar_prompt_comodo(nome_comodo: str, categorias: list, notas_extras: str = "") -> str:
    """Monta UM ÚNICO prompt pedindo as 8 categorias de uma vez, com a
    resposta em JSON — troca 8 chamadas de API por cômodo por apenas 1.

    `notas_extras` é informação específica do imóvel em vistoria (ex.: nome
    exato da cor de tinta usada, confirmado pelo vistoriador) que ajuda o
    modelo a não precisar advinhar detalhes que a foto sozinha não garante.
    Fica de fora de REGRAS_GERAIS/INSTRUCAO_CATEGORIA porque é válida só
    para esta vistoria, não para todo laudo gerado pelo script."""
    blocos_categoria = "\n".join(
        f'- "{categoria}": {INSTRUCAO_CATEGORIA[categoria].strip()}'
        for categoria in categorias
    )

    chaves_exemplo = ", ".join(f'"{categoria}": "..."' for categoria in categorias)

    bloco_notas = ""
    if notas_extras.strip():
        bloco_notas = (
            "Informações confirmadas sobre este imóvel específico (use estes "
            "dados exatos sempre que se aplicarem, em vez de tentar advinhar "
            f"pela foto):\n{notas_extras.strip()}\n\n"
        )

    return (
        f"{REGRAS_GERAIS}\n\n"
        f"Cômodo: {nome_comodo}\n\n"
        f"{bloco_notas}"
        "Analise todas as fotos fornecidas deste cômodo e descreva CADA uma "
        "das categorias abaixo, seguindo à risca as instruções de cada uma "
        "e o formato de escrita definido acima:\n\n"
        f"{blocos_categoria}\n\n"
        "IMPORTANTE — formato da resposta:\n"
        "Responda APENAS com um objeto JSON válido, sem texto antes ou "
        "depois, sem markdown, sem ```json. O JSON deve ter exatamente "
        "estas chaves, cada uma com uma string como valor (use \\n para "
        "separar as linhas dentro do texto de cada categoria, sem linha em "
        f"branco entre os itens): {{{chaves_exemplo}}}"
    )
