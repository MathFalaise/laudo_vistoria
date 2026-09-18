"""
Camada fina sobre a API do Google Gemini: envia as fotos
de um cômodo + o prompt com as 8 categorias e retorna o texto gerado em JSON.
"""

import json
import re
import time

from google import genai
from google.genai import errors, types

from config import API_KEY, MODEL_NAME, CATEGORIAS, LIMIAR_CERTEZA
from report_writer import (
    TEXTO_NAO_SE_APLICA,
    TEXTO_SEM_OBSERVACOES,
    normalizar_linha,
    texto_vazio_da_categoria,
)
from style_guide import montar_prompt_comodo, montar_prompt_revisao

# Nº de tentativas extras e espera entre elas quando o Gemini responde
# 503 (servidor sobrecarregado) — esse erro é comum e quase sempre
# transitório; a própria API pede pra tentar de novo mais tarde.
MAX_TENTATIVAS = 4
ESPERA_BASE_SEGUNDOS = 10


def criar_cliente() -> genai.Client:
    if not API_KEY:
        raise RuntimeError(
            "Defina a variável de ambiente GEMINI_API_KEY antes de rodar o script "
            "(gere uma em https://aistudio.google.com/apikey, num projeto com "
            "faturamento ativo — ver CLAUDE.md)."
        )
    return genai.Client(api_key=API_KEY)


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


def _montar_categoria(categoria: str, itens) -> tuple:
    """Junta os itens de uma categoria no texto do laudo e separa os que
    ficaram abaixo de LIMIAR_CERTEZA. Devolve (texto, itens_incertos)."""
    if not isinstance(itens, list) or not itens:
        # O schema pede pelo menos 1 item; se mesmo assim vier vazio, não dá
        # para afirmar nada sobre a categoria — vai para validação.
        vazio = texto_vazio_da_categoria(categoria)
        return vazio, [{
            "categoria": categoria,
            "texto": vazio,
            "certeza": 0,
            "motivo": "o modelo não devolveu nenhum item para esta categoria",
        }]

    linhas, incertos = [], []
    for item in itens:
        if not isinstance(item, dict):
            continue
        try:
            certeza = max(0, min(100, int(item.get("certeza", 0))))
        except (TypeError, ValueError):
            certeza = 0
        motivo = " ".join(str(item.get("motivo", "")).split())
        # Um "texto" com várias linhas vira vários itens com a mesma certeza.
        for bruta in str(item.get("texto", "")).splitlines():
            linha = normalizar_linha(bruta)
            if not linha:
                continue
            linhas.append(linha)
            if certeza < LIMIAR_CERTEZA:
                incertos.append({
                    "categoria": categoria,
                    "texto": linha,
                    "certeza": certeza,
                    "motivo": motivo or "(o modelo não explicou)",
                })

    # "Não se aplica."/"Sem observações." não convivem com itens reais; e,
    # sem itens reais, a categoria fica com o texto vazio certo para ela
    # ("Sem observações." no OBS, "Não se aplica." no resto).
    vazios = (TEXTO_NAO_SE_APLICA, TEXTO_SEM_OBSERVACOES)
    reais = [linha for linha in linhas if linha not in vazios]
    if reais:
        return "\n".join(reais), [i for i in incertos if i["texto"] not in vazios]

    vazio = texto_vazio_da_categoria(categoria)
    if incertos:
        menos_certo = min(incertos, key=lambda i: i["certeza"])
        incertos = [dict(menos_certo, texto=vazio)]
    return vazio, incertos


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
        except errors.ServerError as erro:
            if tentativa == MAX_TENTATIVAS:
                raise
            espera = ESPERA_BASE_SEGUNDOS * tentativa
            print(
                f"  Servidor do Gemini indisponível para {descricao_erro} "
                f"({erro.__class__.__name__}), tentativa {tentativa}/{MAX_TENTATIVAS}. "
                f"Aguardando {espera}s..."
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
        texto, incertos_categoria = _montar_categoria(categoria, dados.get(categoria))
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
        revisado[nome_comodo] = {
            categoria: str(dados_revisados.get(categoria, dados_originais.get(categoria, ""))).strip()
            for categoria in CATEGORIAS
        }
    return revisado
