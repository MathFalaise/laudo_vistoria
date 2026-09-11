# laudo_vistoria

Gerador automático de laudo de vistoria de entrada de imóvel residencial,
a partir de fotos organizadas por cômodo. Usa a API de visão da Anthropic
(Claude) para descrever cada cômodo em 8 categorias e grava o resultado em
arquivos `.txt`.

## Uso

```bash
python main.py "C:\caminho\para\o\imovel"
```

A pasta do imóvel deve conter uma subpasta por cômodo, cada uma com as
fotos daquele cômodo (`.jpg`, `.jpeg`, `.png`, `.heic`).

Requer a variável de ambiente `ANTHROPIC_API_KEY` definida antes de rodar.

## Arquitetura

- **config.py** — configurações gerais: chave de API, nome do modelo,
  extensões de imagem aceitas, tamanho máximo de redimensionamento e a
  lista `CATEGORIAS` (paredes, piso, teto, porta, janela, eletrico,
  mobilia, obs) com seus rótulos de exibição.
- **style_guide.py** — concentra todo o "jeito de escrever" do laudo:
  regras gerais de formatação (`REGRAS_GERAIS`), exemplos de padrão
  validado (`EXEMPLOS_MOBILIA`), instruções por categoria
  (`INSTRUCAO_CATEGORIA`) e `montar_prompt_comodo`, que monta um único
  prompt cobrindo as 8 categorias de um cômodo e pede a resposta em JSON.
- **image_utils.py** — localiza as fotos de um cômodo, redimensiona (lado
  maior limitado a `TAMANHO_MAX_IMAGEM`) e codifica em base64 para entrar
  no bloco `content` da mensagem da API.
- **claude_client.py** — camada fina sobre a API da Anthropic:
  `analisar_comodo` envia as fotos + o prompt do cômodo, faz **1 única
  chamada de API por cômodo** e faz o parse do JSON de resposta
  (`_extrair_json`, tolerante a texto embrulhado em ```` ```json ````).
- **room_processor.py** — orquestra o processamento de um cômodo: lê as
  fotos e chama `analisar_comodo`.
- **report_writer.py** — grava o `.txt` de cada cômodo (dentro da própria
  pasta de fotos) e o `.txt` consolidado do imóvel inteiro
  (`Laudo_Vistoria_Completo.txt`, na raiz da pasta do imóvel).
- **main.py** — ponto de entrada via CLI: percorre as subpastas de cômodo
  do imóvel e junta tudo.

## Decisões importantes

- Desde a refatoração de set/2026, cada cômodo gera **apenas 1 chamada de
  API** (antes eram 8, uma por categoria) — o modelo recebe todas as fotos
  do cômodo de uma vez e devolve as 8 categorias num único JSON. Isso
  reduz bastante o consumo de tokens. Ao alterar o formato do prompt ou o
  parsing da resposta, manter esse contrato de 1 chamada por cômodo.
- Todo o texto de saída é em português, seguindo as regras de formatação
  de `REGRAS_GERAIS` (item por linha começando com `*`, sem linha em
  branco entre itens, padrão de frase fixo). Mudanças de estilo do laudo
  devem ser feitas em `style_guide.py`, não espalhadas pelo resto do
  código.
