# laudo_vistoria

Gerador automático de laudo de vistoria de entrada de imóvel residencial,
a partir de fotos organizadas por cômodo. Usa a API de visão do Google
Gemini (camada paga) para descrever cada cômodo em 8 categorias e
grava o resultado em arquivos `.txt`.

## Uso

```bash
python main.py "C:\caminho\para\o\imovel"      # gera laudo + pendências
python validar.py "C:\caminho\para\o\imovel"   # aplica as decisões do vistoriador
python revisar.py "C:\caminho\para\o\imovel"   # opcional: repadroniza o texto
```

A pasta do imóvel deve conter uma subpasta por cômodo, cada uma com as
fotos daquele cômodo (`.jpg`, `.jpeg`, `.png`, `.heic`).

Nessa ordem: `revisar.py` reescreve o texto dos itens, e pendências em
aberto deixariam de bater com o laudo — por isso ele se recusa a rodar se
houver pendência aberta (a não ser com `--ignorar-pendencias`).

Requer a variável de ambiente `GEMINI_API_KEY` definida antes de rodar
(gerada em https://aistudio.google.com/apikey, num projeto com
faturamento ativo — ver "Decisões importantes").

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
  chamada de API por cômodo** e devolve `(dados, incertos)`: o texto de
  cada categoria e a lista de itens com certeza abaixo de
  `config.LIMIAR_CERTEZA`. O `response_schema` pede cada categoria como
  lista de itens `{texto, motivo, certeza}`, nessa ordem (o modelo escreve
  o item, diz o que é duvidoso e só depois dá a nota).
- **validacao.py** — formato do `Pendencias_Validacao.txt` (gravado na
  pasta do imóvel, tem dado de cliente), leitura das decisões do
  vistoriador (OK / CORRIGIR / REMOVER), aplicação nos `.txt` dos cômodos e
  adoção das regras gerais em `regras_validadas.txt`.
- **validar.py** — CLI do fluxo acima; reconstrói o laudo consolidado.
- **regras_validadas.txt** — regras gerais adotadas pelo vistoriador;
  `style_guide._regras()` injeta no prompt de toda vistoria e da revisão.
  Fica no repositório PÚBLICO: só regra de redação, nunca dado de cliente.
- **room_processor.py** — orquestra o processamento de um cômodo: lê as
  fotos e chama `analisar_comodo`. Aceita `notas_extras` opcional
  (informação confirmada sobre o imóvel, ex.: cor exata de tinta) que é
  repassada até o prompt — ver `main.py --notas`.
- **report_writer.py** — grava o `.txt` de cada cômodo (dentro da própria
  pasta de fotos) e o `.txt` consolidado do imóvel inteiro
  (`Laudo_Vistoria_Completo.txt`, na raiz da pasta do imóvel).
- **main.py** — ponto de entrada via CLI: percorre as subpastas de cômodo
  do imóvel e junta tudo.

## Decisões importantes

- Desde set/2026 o motor é o **Google Gemini**, não mais a Anthropic. Se
  um dia precisar trocar de novo, os únicos arquivos acoplados ao SDK são
  `image_utils.py` (monta `types.Part`) e `gemini_client.py` (chama
  `client.models.generate_content`); o resto do projeto é agnóstico de
  provedor.
- **O projeto do Gemini TEM que ficar na camada paga** (faturamento ativo
  desde 18/09/2026 — Nível 1, pré-pagamento). Motivo: os termos da camada
  gratuita permitem que o Google use o conteúdo enviado para melhorar
  produtos, com revisão humana, e pedem explicitamente para não enviar
  informação pessoal ou confidencial — e este script envia fotos do
  interior de imóveis de clientes (LGPD). Na camada paga, o Google não usa
  prompts nem arquivos para isso. Custo medido: ~US$ 0,14 na maior
  vistoria até agora (11 cômodos, 358 fotos, ~420 mil tokens de entrada) —
  não vale voltar para a gratuita para economizar isso. Para conferir:
  aistudio.google.com/projects, coluna "Nível de faturamento".
- `gemini-3.5-flash-lite` é o padrão em `config.MODEL_NAME`. Foi escolhido
  em 11/09/2026, ainda na camada gratuita, porque o `gemini-3.6-flash` tinha
  cota de só 20 requisições/dia por projeto e estourou no meio de uma
  vistoria. Na camada paga essa limitação some, mas o flash-lite continua
  sendo o padrão: qualidade equivalente nos testes com dados reais e
  entrada 5× mais barata (US$ 0,30 vs. US$ 1,50 por milhão de tokens). Se
  trocar de modelo, rode um teste real de ponta a ponta, não só um
  `models.list()`.
- `gemini_client.analisar_comodo` já tenta de novo automaticamente (com
  espera crescente) quando o Gemini responde `503` (sobrecarga do
  servidor — comum e transitório). Cota estourada (`429`) não tem nova
  tentativa automática — não adianta, o request tem que esperar o reset
  da cota ou trocar de modelo.
- `main.py` isola falha por cômodo: se um cômodo der erro mesmo após as
  tentativas, o script segue para o próximo em vez de derrubar o laudo
  inteiro, e lista no final quais cômodos precisam rodar de novo.
- **Sistema de certeza (desde 18/09/2026):** cada item do laudo vem com
  uma certeza 0–100 dada pelo próprio modelo; abaixo de
  `config.LIMIAR_CERTEZA` (85) vira pendência para o vistoriador conferir.
  O limiar fica SÓ no código, nunca no prompt — se o modelo souber o corte,
  tende a responder logo acima dele. Os itens incertos continuam no laudo
  (a lista é de conferência, não de exclusão).
  **Limitação comprovada:** a certeza é autoavaliação, não probabilidade
  medida. No primeiro teste real (Churrasqueira da R. Xavier), o modelo
  deu ≥85% para TUDO — inclusive "Janela: Não se aplica.", quando a rodada
  anterior do mesmo cômodo, com as mesmas fotos, tinha descrito uma janela
  de correr. Erro confiante não é pego por esse sistema: ele serve de
  triagem ("onde olhar primeiro"), não de garantia.
- **"Mais um/uma" é proibido** (pedido explícito do vistoriador, depois de
  aparecer em 3 laudos seguidos apesar da regra antiga). Item repetido vira
  UMA linha com a quantidade total ("*Duas portas..."), com "sendo um...
  e outro..." se algum detalhe diferir. Como só a regra no prompt já tinha
  falhado antes, há três camadas: (1) a regra ITENS REPETIDOS em
  `REGRAS_GERAIS`; (2) se ainda assim aparecer, `_consolidar_repetidos` faz
  UMA chamada de texto puro só para aquela categoria (fração de centavo,
  só quando o modelo desobedece); (3) o que sobrar vira pendência de
  certeza 0 levando junto a linha anterior (`report_writer.linha_com_mais_um`
  detecta). Vale na análise com fotos e no `revisar.py`.
- Regra adotada via `validar.py` é regra GERAL (vale para todo imóvel).
  Fato de um imóvel específico ("a cozinha não tem porta") se resolve com
  CORRIGIR/REMOVER ou `--notas`, nunca como regra — senão o modelo passa a
  achar que nenhuma cozinha tem porta.
- Cada cômodo gera **apenas 1 chamada de API** (antes eram 8, uma por
  categoria) — o modelo recebe todas as fotos do cômodo de uma vez e
  devolve as 8 categorias num único JSON. Ao alterar o formato do prompt
  ou o parsing da resposta, manter esse contrato de 1 chamada por cômodo.
- Todo o texto de saída é em português, seguindo as regras de formatação
  de `REGRAS_GERAIS` (item por linha começando com `*`, sem linha em
  branco entre itens, padrão de frase fixo). Mudanças de estilo do laudo
  devem ser feitas em `style_guide.py`, não espalhadas pelo resto do
  código.
