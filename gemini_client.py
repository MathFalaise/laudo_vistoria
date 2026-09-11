"""
Camada fina sobre a API do Google Gemini (camada gratuita): envia as fotos
de um cômodo + o prompt com as 8 categorias e retorna o texto gerado em JSON.
"""

import json
import re
import time

from google import genai
from google.genai import errors, types

from config import API_KEY, MODEL_NAME, CATEGORIAS
from style_guide import montar_prompt_comodo

# Nº de tentativas extras e espera entre elas quando o Gemini responde
# 503 (servidor sobrecarregado) — esse erro é comum e quase sempre
# transitório; a própria API pede pra tentar de novo mais tarde.
MAX_TENTATIVAS = 4
ESPERA_BASE_SEGUNDOS = 10


def criar_cliente() -> genai.Client:
    if not API_KEY:
        raise RuntimeError(
            "Defina a variável de ambiente GEMINI_API_KEY antes de rodar o script "
            "(gere uma chave gratuita em https://aistudio.google.com/apikey)."
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


def _schema_categorias(categorias: list) -> types.Schema:
    """Monta o response_schema que força o modelo a devolver um objeto
    JSON plano com uma chave string por categoria, evitando que a
    resposta venha embrulhada em lista ou com chaves inesperadas."""
    return types.Schema(
        type="OBJECT",
        properties={categoria: types.Schema(type="STRING") for categoria in categorias},
        required=categorias,
    )


def analisar_comodo(
    cliente: genai.Client, blocos_imagem: list, nome_comodo: str, notas_extras: str = ""
) -> dict:
    """Chama a API UMA vez para o cômodo inteiro e retorna
    {categoria: texto} para as 8 categorias definidas em config.CATEGORIAS.

    `notas_extras` repassa informação específica deste imóvel (ex.: cor
    exata de tinta confirmada) para o prompt — ver style_guide.montar_prompt_comodo."""
    prompt = montar_prompt_comodo(nome_comodo, CATEGORIAS, notas_extras)
    conteudo = list(blocos_imagem) + [prompt]

    resposta = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resposta = cliente.models.generate_content(
                model=MODEL_NAME,
                contents=conteudo,
                config=types.GenerateContentConfig(
                    # Cômodos com muitas fotos/mobília geram descrições
                    # longas — um teto baixo aqui corta o JSON no meio e
                    # quebra o parsing.
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                    response_schema=_schema_categorias(CATEGORIAS),
                ),
            )
            break
        except errors.ServerError as erro:
            if tentativa == MAX_TENTATIVAS:
                raise
            espera = ESPERA_BASE_SEGUNDOS * tentativa
            print(
                f"  Servidor do Gemini indisponível para '{nome_comodo}' "
                f"({erro.__class__.__name__}), tentativa {tentativa}/{MAX_TENTATIVAS}. "
                f"Aguardando {espera}s..."
            )
            time.sleep(espera)

    candidato = resposta.candidates[0] if resposta.candidates else None
    if candidato is not None and candidato.finish_reason == types.FinishReason.MAX_TOKENS:
        raise RuntimeError(
            f"A resposta do modelo para o cômodo '{nome_comodo}' foi cortada por "
            "atingir o limite de max_output_tokens antes de terminar o JSON "
            "(cômodo com descrição muito longa). Aumente max_output_tokens em "
            "gemini_client.py e tente novamente."
        )

    texto_bruto = resposta.text

    try:
        dados = _extrair_json(texto_bruto)
    except (json.JSONDecodeError, ValueError) as erro:
        raise RuntimeError(
            f"Não foi possível interpretar a resposta do modelo como JSON "
            f"para o cômodo '{nome_comodo}'. Erro: {erro}\n\n"
            f"Resposta recebida:\n{texto_bruto}"
        ) from erro

    return {categoria: str(dados.get(categoria, "")).strip() for categoria in CATEGORIAS}
