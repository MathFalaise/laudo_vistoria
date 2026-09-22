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

# Itens que o modelo avaliar com certeza ABAIXO deste valor (0-100) vão para
# Pendencias_Validacao.txt, para o vistoriador conferir nas fotos antes de o
# laudo sair. O valor fica só aqui, fora do prompt: se o modelo souber o
# corte, tende a responder logo acima dele. A certeza é autoavaliação do
# modelo, não probabilidade medida — serve para triagem, não como garantia.
LIMIAR_CERTEZA = 85

# Item com certeza ATÉ este valor nem chega ao vistoriador de primeira: o
# script manda o modelo olhar as fotos de novo, só aquele item, e é o texto
# da segunda olhada que entra no laudo (ver
# gemini_client._corrigir_itens_incertos). Pedido do vistoriador em
# 22/09/2026 — ele quer conferir à mão só a faixa do meio, entre este
# limiar e LIMIAR_CERTEZA. Item que continuar aqui embaixo depois da
# segunda olhada vira pendência assim mesmo: ninguém assina um laudo com
# uma afirmação que o próprio motor considera duvidosa.
LIMIAR_CORRECAO_AUTOMATICA = 50

# CONFERÊNCIA (conferir.py): depois do laudo escrito, o modelo olha as fotos
# de novo com o texto pronto na mão e aponta divergências — item que aparece
# na foto e ficou de fora, afirmação que a foto não sustenta. Só vira
# pendência o que ele apontar com certeza a partir daqui; abaixo disso é
# ruído, e pendência demais ninguém lê.
LIMIAR_CONFERENCIA = 70

# Quantas fotos entram em cada mosaico da conferência. O Gemini cobra por
# imagem, não por pixel (medido: 1.101 tokens por foto, em qualquer
# resolução), então 4 fotos numa folha de contato custam 1/4 do preço.
# Se mudar este número, rode a conferência num cômodo com item conhecido
# faltando e veja se ele ainda é encontrado — quanto mais fotos por folha,
# menor a miniatura.
FOTOS_POR_MOSAICO_CONFERENCIA = 4

# Regras gerais adotadas a partir de pendências validadas (ver validar.py).
# Entram no prompt de toda vistoria, junto com REGRAS_GERAIS. O arquivo fica
# no repositório, que é público — por isso só regra geral de redação, nunca
# endereço, nome de cliente ou fato específico de um imóvel.
ARQUIVO_REGRAS_VALIDADAS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "regras_validadas.txt"
)

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
