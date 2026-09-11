from gemini_client import analisar_comodo
from image_utils import codificar_fotos_comodo


def processar_comodo(cliente, pasta_comodo: str, nome_comodo: str, notas_extras: str = "") -> dict:
    print(f"Lendo fotos de: {nome_comodo}...")
    blocos_imagem = codificar_fotos_comodo(pasta_comodo)

    if not blocos_imagem:
        print(f"  Nenhuma foto encontrada em {pasta_comodo}, pulando.")
        return {}

    print("  -> Analisando cômodo (1 chamada, 8 categorias)...")
    return analisar_comodo(cliente, blocos_imagem, nome_comodo, notas_extras)
