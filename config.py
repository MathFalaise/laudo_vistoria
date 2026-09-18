"""
Configurações gerais do gerador automático de laudo de vistoria.
"""

import os

# Chave de API do Google Gemini (defina como variável de ambiente GEMINI_API_KEY).
# Gerada em https://aistudio.google.com/apikey. O projeto da chave precisa
# estar na camada PAGA (dados de clientes) — ver CLAUDE.md.
API_KEY = os.environ.get("GEMINI_API_KEY")

# Modelo Gemini usado para leitura das fotos (precisa suportar visão).
# gemini-3.5-flash-lite: qualidade equivalente ao 3.6-flash nos testes com
# dados reais (11/09/2026) e entrada 5x mais barata — ver CLAUDE.md.
MODEL_NAME = "gemini-3.5-flash-lite"

# Extensões de imagem aceitas dentro das pastas de cômodo
EXTENSOES_IMAGEM = (".jpg", ".jpeg", ".png", ".heic")

# Tamanho máximo (em pixels, lado maior) para redimensionar as fotos antes de
# enviar à API — reduz custo/tempo sem perder detalhe relevante
TAMANHO_MAX_IMAGEM = 1568

# Categorias do laudo, na ordem em que devem aparecer no relatório final
CATEGORIAS = [
    "paredes",
    "piso",
    "teto",
    "porta",
    "janela",
    "eletrico",
    "mobilia",
    "obs",
]

# Rótulos de exibição de cada categoria
ROTULOS_CATEGORIA = {
    "paredes": "Paredes",
    "piso": "Piso",
    "teto": "Teto",
    "porta": "Porta",
    "janela": "Janela",
    "eletrico": "Componentes Elétricos",
    "mobilia": "Mobília",
    "obs": "OBS",
}
