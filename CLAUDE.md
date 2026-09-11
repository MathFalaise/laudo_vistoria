# laudo_vistoria

Gerador automático de laudo de vistoria de entrada de imóvel residencial,
a partir de fotos organizadas por cômodo. Usa a API de visão do Google
Gemini (camada gratuita) para descrever cada cômodo em 8 categorias e
grava o resultado em arquivos `.txt`.

## Uso

```bash
python main.py "C:\caminho\para\o\imovel"
```

A pasta do imóvel deve conter uma subpasta por cômodo, cada uma com as
fotos daquele cômodo (`.jpg`, `.jpeg`, `.png`, `.heic`).

Requer a variável de ambiente `GEMINI_API_KEY` definida antes de rodar
(chave gratuita, sem cartão de crédito, gerada em
https://aistudio.google.com/apikey).

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
  maior limitado a `TAMANHO_MAX_IMAGEM`) e converte em `Part` do SDK
  `google-genai`, prontos para entrar no `contents` da mensagem da API.
- **gemini_client.py** — camada fina sobre a API do Google Gemini:
  `analisar_comodo` envia as fotos + o prompt do cômodo, faz **1 única
  chamada de API por cômodo** (com `response_mime_type="application/json"`
  forçando saída em JSON) e faz o parse da resposta (`_extrair_json`,
  tolerante a texto embrulhado em ```` ```json ```` como camada extra de
  segurança).
- **room_processor.py** — orquestra o processamento de um cômodo: lê as
  fotos e chama `analisar_comodo`.
- **report_writer.py** — grava o `.txt` de cada cômodo (dentro da própria
  pasta de fotos) e o `.txt` consolidado do imóvel inteiro
  (`Laudo_Vistoria_Completo.txt`, na raiz da pasta do imóvel).
- **main.py** — ponto de entrada via CLI: percorre as subpastas de cômodo
  do imóvel e junta tudo.

## Decisões importantes

- Desde set/2026 o motor é o **Google Gemini** (`gemini-2.5-flash`), não
  mais a Anthropic — troca feita para eliminar custo, já que a API do
  Gemini tem camada gratuita generosa (sem cartão de crédito) para esse
  volume de uso. Se um dia precisar trocar de novo, os únicos arquivos
  acoplados ao SDK são `image_utils.py` (monta `types.Part`) e
  `gemini_client.py` (chama `client.models.generate_content`); o resto do
  projeto é agnóstico de provedor.
- Cada cômodo gera **apenas 1 chamada de API** (antes eram 8, uma por
  categoria) — o modelo recebe todas as fotos do cômodo de uma vez e
  devolve as 8 categorias num único JSON. Ao alterar o formato do prompt
  ou o parsing da resposta, manter esse contrato de 1 chamada por cômodo.
- Todo o texto de saída é em português, seguindo as regras de formatação
  de `REGRAS_GERAIS` (item por linha começando com `*`, sem linha em
  branco entre itens, padrão de frase fixo). Mudanças de estilo do laudo
  devem ser feitas em `style_guide.py`, não espalhadas pelo resto do
  código.
