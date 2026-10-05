"""
Schema NEUTRO de resposta, comum a todos os provedores.

O formato é um dicionário com os mesmos campos do `types.Schema` do Gemini
(`type`, `properties`, `required`, `property_ordering`, `items`, `enum`,
`minimum`, `maximum`, `min_items`), porque foi nele que os schemas do motor
foram escritos e testados. Assim:

- o provedor Gemini converte com `types.Schema.model_validate` e manda
  EXATAMENTE o mesmo pedido de antes (há teste comparando objeto a objeto);
- os provedores HTTP (GLM, Claude) recebem o mesmo schema como JSON Schema,
  por `para_json_schema`.

A ordem das propriedades importa para a qualidade da resposta (o modelo
escreve o item, depois o motivo, só então dá a nota). JSON Schema não tem
`property_ordering`, então a conversão insere as propriedades nessa ordem —
é a ordem que os modelos seguem na prática.
"""

from __future__ import annotations

_CAMPOS = ("type", "properties", "required", "property_ordering", "items", "enum",
           "minimum", "maximum", "min_items")


def esquema(**campos) -> dict:
    """Constrói um nó de schema neutro, sem os campos vazios.

    Tem a mesma assinatura do `types.Schema(...)` que o motor usava — a troca
    foi mecânica, e o teste `test_schemas_neutros_sao_os_mesmos_do_gemini`
    prova que nada mudou no pedido."""
    desconhecidos = set(campos) - set(_CAMPOS)
    if desconhecidos:
        raise ValueError(f"campo de schema não suportado: {sorted(desconhecidos)}")
    return {chave: valor for chave, valor in campos.items() if valor is not None}


def para_json_schema(no: dict) -> dict:
    """Converte o schema neutro em JSON Schema (OpenAI, Anthropic)."""
    tipo = str(no.get("type", "")).lower()
    saida: dict = {"type": tipo} if tipo else {}

    if "enum" in no:
        saida["enum"] = list(no["enum"])
    if "minimum" in no:
        saida["minimum"] = no["minimum"]
    if "maximum" in no:
        saida["maximum"] = no["maximum"]
    if "min_items" in no:
        saida["minItems"] = no["min_items"]
    if "items" in no:
        saida["items"] = para_json_schema(no["items"])

    if "properties" in no:
        propriedades = no["properties"]
        ordem = list(no.get("property_ordering") or [])
        ordem += [nome for nome in propriedades if nome not in ordem]
        saida["properties"] = {
            nome: para_json_schema(propriedades[nome]) for nome in ordem if nome in propriedades
        }
    if "required" in no:
        saida["required"] = list(no["required"])
    return saida
