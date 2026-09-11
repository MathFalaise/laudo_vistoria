import json
import re

import anthropic

from config import API_KEY, MODEL_NAME, CATEGORIAS
from style_guide import montar_prompt_comodo


def criar_cliente() -> anthropic.Anthropic:
    if not API_KEY:
        raise RuntimeError(
            "Defina a variável de ambiente ANTHROPIC_API_KEY antes de rodar o script."
        )
    return anthropic.Anthropic(api_key=API_KEY)


def _extrair_json(texto: str) -> dict:
    """Extrai o objeto JSON da resposta do modelo, mesmo que ele venha
    embrulhado em ```json ... ``` ou com espaços/quebras extras."""
    texto = texto.strip()
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", texto, re.DOTALL)
    if match:
        texto = match.group(1)
    elif not texto.startswith("{"):
        inicio = texto.find("{")
        fim = texto.rfind("}")
        if inicio != -1 and fim != -1:
            texto = texto[inicio : fim + 1]
    return json.loads(texto)


def analisar_comodo(cliente: anthropic.Anthropic, blocos_imagem: list, nome_comodo: str) -> dict:
    """Chama a API UMA vez para o cômodo inteiro e retorna
    {categoria: texto} para as 8 categorias definidas em config.CATEGORIAS."""
    prompt = montar_prompt_comodo(nome_comodo, CATEGORIAS)
    conteudo = list(blocos_imagem) + [{"type": "text", "text": prompt}]

    resposta = cliente.messages.create(
        model=MODEL_NAME,
        max_tokens=2048,
        messages=[{"role": "user", "content": conteudo}],
    )

    texto_bruto = resposta.content[0].text

    try:
        dados = _extrair_json(texto_bruto)
    except (json.JSONDecodeError, ValueError) as erro:
        raise RuntimeError(
            f"Não foi possível interpretar a resposta do modelo como JSON "
            f"para o cômodo '{nome_comodo}'. Erro: {erro}\n\n"
            f"Resposta recebida:\n{texto_bruto}"
        ) from erro

    return {categoria: str(dados.get(categoria, "")).strip() for categoria in CATEGORIAS}
