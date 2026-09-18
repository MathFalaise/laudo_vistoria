"""
Camada fina sobre a API do Google Gemini: envia as fotos
de um cômodo + o prompt com as 8 categorias e retorna o texto gerado em JSON.
"""

import json
import re
import time

import httpx
from google import genai
from google.genai import errors, types

from config import API_KEY, MODEL_NAME, CATEGORIAS, LIMIAR_CERTEZA, ROTULOS_CATEGORIA
from report_writer import (
    TEXTO_NAO_SE_APLICA,
    TEXTO_SEM_OBSERVACOES,
    linha_com_mais_um,
    normalizar_linha,
    texto_vazio_da_categoria,
)
from style_guide import montar_prompt_comodo, montar_prompt_consolidacao, montar_prompt_revisao

# Nº de tentativas e espera entre elas em falha transitória: 503 (servidor
# sobrecarregado — a própria API pede pra tentar de novo) ou falha de rede,
# inclusive o tempo limite abaixo estourar.
MAX_TENTATIVAS = 4
ESPERA_BASE_SEGUNDOS = 10

# Tempo máximo de espera por UMA chamada. Sem isso, uma conexão que o
# servidor deixou pendurada trava o script para sempre — aconteceu em
# 18/09/2026, com o processo parado 10+ minutos esperando resposta. O
# cômodo mais lento já medido levou ~2 min (51 fotos); 5 min é folga.
TEMPO_LIMITE_CHAMADA_SEGUNDOS = 300

SEM_MOTIVO = "(o modelo não explicou)"
MOTIVO_MAIS_UM = (
    'item repetido escrito com "Mais um/uma", e a correção automática não '
    "resolveu — troque as linhas por uma só, com a quantidade total (ex.: "
    '"*Duas portas ...")'
)


def criar_cliente() -> genai.Client:
    if not API_KEY:
        raise RuntimeError(
            "Defina a variável de ambiente GEMINI_API_KEY antes de rodar o script "
            "(gere uma em https://aistudio.google.com/apikey, num projeto com "
            "faturamento ativo — ver CLAUDE.md)."
        )
    return genai.Client(
        api_key=API_KEY,
        http_options=types.HttpOptions(timeout=TEMPO_LIMITE_CHAMADA_SEGUNDOS * 1000),
    )


def _extrair_json(texto: str) -> dict:
    """Extrai o objeto JSON da resposta do modelo, mesmo que ele venha
    embrulhado em ```json ... ```, com espaços/quebras extras, ou dentro
    de uma lista (ex.: [{...}]) em vez de um objeto solto."""
    texto = texto.strip()
    match = re.search(r"```(?:json)?\s*(.*)\s*```", texto, re.DOTALL)
    if match:
        texto = match.group(1).strip()

    dados = json.loads(texto)
    if isinstance(dados, list):
        if not dados or not isinstance(dados[0], dict):
            raise ValueError("Resposta é uma lista JSON sem objeto de categorias dentro.")
        dados = dados[0]
    return dados


# Quantos caracteres da resposta do modelo entram na mensagem de erro.
# O suficiente pra depurar um JSON malformado, sem despejar o laudo
# inteiro (descrição do imóvel do cliente) num traceback que pode acabar
# colado em e-mail, issue ou canal de suporte.
LIMITE_TRECHO_ERRO = 300


def _trecho_para_erro(texto: str) -> str:
    """Devolve só o começo da resposta do modelo, para mensagens de erro."""
    if not texto:
        return "(resposta vazia)"
    texto = texto.strip()
    if len(texto) <= LIMITE_TRECHO_ERRO:
        return texto
    omitidos = len(texto) - LIMITE_TRECHO_ERRO
    return f"{texto[:LIMITE_TRECHO_ERRO]}... [+{omitidos} caracteres omitidos]"


def _schema_categorias(categorias: list) -> types.Schema:
    """Monta o response_schema que força o modelo a devolver um objeto
    JSON plano com uma chave string por categoria, evitando que a
    resposta venha embrulhada em lista ou com chaves inesperadas."""
    return types.Schema(
        type="OBJECT",
        properties={categoria: types.Schema(type="STRING") for categoria in categorias},
        required=categorias,
    )


def _schema_itens_com_certeza(categorias: list) -> types.Schema:
    """Schema da análise de um cômodo: cada categoria é uma lista de itens
    {texto, motivo, certeza}. A ordem texto -> motivo -> certeza é
    proposital: o modelo escreve o item, diz o que nele é duvidoso e só
    então dá a nota — em vez de se comprometer com um número antes."""
    item = types.Schema(
        type="OBJECT",
        properties={
            "texto": types.Schema(type="STRING"),
            "motivo": types.Schema(type="STRING"),
            "certeza": types.Schema(type="INTEGER", minimum=0, maximum=100),
        },
        required=["texto", "motivo", "certeza"],
        property_ordering=["texto", "motivo", "certeza"],
    )
    return types.Schema(
        type="OBJECT",
        properties={
            categoria: types.Schema(type="ARRAY", items=item, min_items=1)
            for categoria in categorias
        },
        required=categorias,
        property_ordering=categorias,
    )


def _registros(itens) -> list:
    """Converte a lista de itens devolvida pelo modelo em
    [(linha, certeza, motivo)], uma tupla por linha do laudo. Um "texto" com
    várias linhas vira várias linhas com a mesma certeza."""
    registros = []
    if not isinstance(itens, list):
        return registros
    for item in itens:
        if not isinstance(item, dict):
            continue
        try:
            certeza = max(0, min(100, int(item.get("certeza", 0))))
        except (TypeError, ValueError):
            certeza = 0
        motivo = " ".join(str(item.get("motivo", "")).split())
        for bruta in str(item.get("texto", "")).splitlines():
            linha = normalizar_linha(bruta)
            if linha:
                registros.append((linha, certeza, motivo))
    return registros


def _consolidar_repetidos(cliente: genai.Client, categoria: str, registros: list) -> list:
    """Conserta uma categoria que veio com "Mais um/uma" apesar da regra:
    UMA chamada de texto puro (sem fotos — custa uma fração de centavo) que
    junta os itens repetidos numa linha só. Só roda quando o modelo
    desobedece.

    Linhas que não mudaram mantêm a certeza original; linhas novas (as
    consolidadas) herdam a MENOR certeza entre as que sumiram. Se a chamada
    falhar, devolve os registros originais — a trava de _montar_categoria
    manda o que sobrar para validação."""
    if not any(linha_com_mais_um(linha) for linha, _, _ in registros):
        return registros

    rotulo = ROTULOS_CATEGORIA[categoria]
    texto = "\n".join(linha for linha, _, _ in registros)
    schema = types.Schema(
        type="OBJECT",
        properties={"linhas": types.Schema(type="ARRAY", items=types.Schema(type="STRING"), min_items=1)},
        required=["linhas"],
    )
    try:
        bruto = _gerar_com_retry(
            cliente,
            [montar_prompt_consolidacao(rotulo, texto)],
            response_schema=schema,
            max_output_tokens=4096,
            descricao_erro=f'a correção de "Mais um/uma" ({rotulo})',
        )
        novas = [normalizar_linha(str(linha)) for linha in _extrair_json(bruto).get("linhas", [])]
        novas = [linha for linha in novas if linha]
    except Exception as erro:
        print(f'  Não consegui corrigir "Mais um/uma" em {rotulo} automaticamente ({erro.__class__.__name__}).')
        return registros
    if not novas:
        return registros

    print(f'  Corrigido automaticamente: "Mais um/uma" em {rotulo}.')
    originais = {linha: (certeza, motivo) for linha, certeza, motivo in registros}
    sumiram = [registro for registro in registros if registro[0] not in novas]
    menos_certa = min(sumiram or registros, key=lambda registro: registro[1])
    herdada = (menos_certa[1], menos_certa[2])
    return [(linha, *originais.get(linha, herdada)) for linha in novas]


def _montar_categoria(categoria: str, registros: list) -> tuple:
    """Junta as linhas de uma categoria no texto do laudo e separa as
    pendências. Devolve (texto, pendencias). Vira pendência:

    - linha com certeza abaixo de LIMIAR_CERTEZA;
    - linha "Mais um/uma..." que sobreviveu à correção automática — com
      certeza 0 e levando junto a linha anterior (o item que ela
      "continua"), para o vistoriador trocar as duas por uma só.

    O "texto" de uma pendência pode ter mais de uma linha."""
    vazio = texto_vazio_da_categoria(categoria)
    if not registros:
        # O schema pede pelo menos 1 item; se mesmo assim vier vazio, não dá
        # para afirmar nada sobre a categoria — vai para validação.
        return vazio, [{
            "categoria": categoria,
            "texto": vazio,
            "certeza": 0,
            "motivo": "o modelo não devolveu nenhum item para esta categoria",
        }]

    # "Não se aplica."/"Sem observações." não convivem com itens reais; e,
    # sem itens reais, a categoria fica com o texto vazio certo para ela
    # ("Sem observações." no OBS, "Não se aplica." no resto).
    reais = [r for r in registros if r[0] not in (TEXTO_NAO_SE_APLICA, TEXTO_SEM_OBSERVACOES)]
    if not reais:
        menos_certo = min(registros, key=lambda registro: registro[1])
        if menos_certo[1] >= LIMIAR_CERTEZA:
            return vazio, []
        return vazio, [{
            "categoria": categoria,
            "texto": vazio,
            "certeza": menos_certo[1],
            "motivo": menos_certo[2] or SEM_MOTIVO,
        }]

    pendencias = []
    for indice, (linha, certeza, motivo) in enumerate(reais):
        ultima = pendencias[-1] if pendencias else None
        encosta_na_ultima = ultima is not None and ultima["_ate"] == indice - 1
        if linha_com_mais_um(linha):
            if encosta_na_ultima:
                # A linha anterior já é pendência: junta as duas numa só.
                motivo_anterior = ultima["motivo"]
                ultima["texto"] += "\n" + linha
                ultima["certeza"] = 0
                ultima["motivo"] = (
                    MOTIVO_MAIS_UM
                    if motivo_anterior in (MOTIVO_MAIS_UM, SEM_MOTIVO)
                    else f"{MOTIVO_MAIS_UM}; além disso: {motivo_anterior}"
                )
                ultima["_ate"] = indice
                continue
            linhas = ([reais[indice - 1][0]] if indice > 0 else []) + [linha]
            pendencias.append({
                "categoria": categoria,
                "texto": "\n".join(linhas),
                "certeza": 0,
                "motivo": MOTIVO_MAIS_UM,
                "_ate": indice,
            })
        elif certeza < LIMIAR_CERTEZA:
            pendencias.append({
                "categoria": categoria,
                "texto": linha,
                "certeza": certeza,
                "motivo": motivo or SEM_MOTIVO,
                "_ate": indice,
            })

    for pendencia in pendencias:
        del pendencia["_ate"]
    return "\n".join(linha for linha, _, _ in reais), pendencias


def pendencias_mais_um(categoria: str, texto: str) -> list:
    """Pendências de linhas "Mais um/uma" num texto já pronto (sem
    certeza) — usado pelo revisar.py depois da revisão."""
    registros = [(linha, 100, "") for linha in texto.split("\n") if linha.strip()]
    return _montar_categoria(categoria, registros)[1] if registros else []


def _gerar_com_retry(
    cliente: genai.Client,
    conteudo: list,
    response_schema: types.Schema,
    max_output_tokens: int,
    descricao_erro: str,
) -> str:
    """Chama generate_content com retry automático em erro 503 (servidor
    sobrecarregado — transitório, a própria API pede pra tentar de novo) e
    verifica se a resposta não foi cortada por max_output_tokens. Devolve o
    texto bruto (JSON) da resposta. Compartilhado por analisar_comodo e
    revisar_laudo pra não duplicar a lógica de retry."""
    resposta = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resposta = cliente.models.generate_content(
                model=MODEL_NAME,
                contents=conteudo,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
            break
        except (errors.ServerError, httpx.TransportError) as erro:
            # TransportError cobre o tempo limite estourado e quedas de rede.
            if tentativa == MAX_TENTATIVAS:
                raise
            espera = ESPERA_BASE_SEGUNDOS * tentativa
            print(
                f"  Falha transitória no Gemini para {descricao_erro} "
                f"({erro.__class__.__name__}), tentativa {tentativa}/{MAX_TENTATIVAS}. "
                f"Aguardando {espera}s...",
                flush=True,
            )
            time.sleep(espera)

    candidato = resposta.candidates[0] if resposta.candidates else None
    if candidato is not None and candidato.finish_reason == types.FinishReason.MAX_TOKENS:
        raise RuntimeError(
            f"A resposta do modelo para {descricao_erro} foi cortada por "
            "atingir o limite de max_output_tokens antes de terminar o JSON. "
            "Aumente max_output_tokens em gemini_client.py e tente novamente."
        )

    return resposta.text


def analisar_comodo(
    cliente: genai.Client, blocos_imagem: list, nome_comodo: str, notas_extras: str = ""
) -> tuple:
    """Chama a API UMA vez para o cômodo inteiro e retorna (dados, incertos):

    - dados: {categoria: texto} para as 8 categorias de config.CATEGORIAS,
      no formato que report_writer grava;
    - incertos: itens que o modelo avaliou com certeza abaixo de
      config.LIMIAR_CERTEZA — [{categoria, texto, certeza, motivo}].

    Os itens incertos continuam no laudo; a lista serve para o vistoriador
    conferir (ver validacao.py e validar.py).

    `notas_extras` repassa informação específica deste imóvel (ex.: cor
    exata de tinta confirmada) para o prompt — ver style_guide.montar_prompt_comodo."""
    prompt = montar_prompt_comodo(nome_comodo, CATEGORIAS, notas_extras)
    conteudo = list(blocos_imagem) + [prompt]

    texto_bruto = _gerar_com_retry(
        cliente,
        conteudo,
        response_schema=_schema_itens_com_certeza(CATEGORIAS),
        # Cômodos com muitas fotos/mobília geram descrições longas — um
        # teto baixo aqui corta o JSON no meio e quebra o parsing.
        max_output_tokens=8192,
        descricao_erro=f"o cômodo '{nome_comodo}'",
    )

    try:
        dados = _extrair_json(texto_bruto)
    except (json.JSONDecodeError, ValueError) as erro:
        raise RuntimeError(
            f"Não foi possível interpretar a resposta do modelo como JSON "
            f"para o cômodo '{nome_comodo}'. Erro: {erro}\n\n"
            f"Início da resposta recebida:\n{_trecho_para_erro(texto_bruto)}"
        ) from erro

    resultado, incertos = {}, []
    for categoria in CATEGORIAS:
        registros = _consolidar_repetidos(cliente, categoria, _registros(dados.get(categoria)))
        texto, incertos_categoria = _montar_categoria(categoria, registros)
        resultado[categoria] = texto
        incertos.extend(incertos_categoria)
    return resultado, incertos


def revisar_laudo(cliente: genai.Client, resultados: dict, notas_extras: str = "") -> dict:
    """Passa um laudo JÁ GERADO (todos os cômodos de um imóvel) por uma
    revisão de TEXTO PURO — sem fotos — pra padronizar terminologia e
    formatação conforme o style_guide atual. Usada por revisar.py quando o
    padrão de escrita muda depois que o laudo já foi gerado com as fotos,
    evitando reenviar as imagens (custo e tempo).

    `resultados` é {nome_comodo: {categoria: texto}}; devolve no mesmo
    formato, com o texto revisado."""
    laudo_json = json.dumps(resultados, ensure_ascii=False, indent=2)
    prompt = montar_prompt_revisao(laudo_json, CATEGORIAS, notas_extras)

    schema_laudo = types.Schema(
        type="OBJECT",
        properties={
            nome_comodo: _schema_categorias(CATEGORIAS) for nome_comodo in resultados
        },
        required=list(resultados.keys()),
    )

    texto_bruto = _gerar_com_retry(
        cliente,
        [prompt],
        response_schema=schema_laudo,
        # O laudo inteiro (todos os cômodos) de uma vez é bem mais texto
        # que um cômodo só — precisa de bastante espaço de saída.
        max_output_tokens=32768,
        descricao_erro="a revisão do laudo completo",
    )

    try:
        dados = _extrair_json(texto_bruto)
    except (json.JSONDecodeError, ValueError) as erro:
        raise RuntimeError(
            "Não foi possível interpretar a resposta da revisão como JSON. "
            f"Erro: {erro}\n\nInício da resposta recebida:\n"
            f"{_trecho_para_erro(texto_bruto)}"
        ) from erro

    revisado = {}
    for nome_comodo, dados_originais in resultados.items():
        dados_revisados = dados.get(nome_comodo, {})
        revisado[nome_comodo] = {}
        for categoria in CATEGORIAS:
            texto = str(dados_revisados.get(categoria, dados_originais.get(categoria, ""))).strip()
            # Mesma correção automática da análise com fotos, caso a revisão
            # também tenha escrito "Mais um/uma".
            registros = [(linha, 100, "") for linha in texto.split("\n") if linha.strip()]
            if any(linha_com_mais_um(linha) for linha, _, _ in registros):
                registros = _consolidar_repetidos(cliente, categoria, registros)
                texto = "\n".join(linha for linha, _, _ in registros)
            revisado[nome_comodo][categoria] = texto
    return revisado
