# laudo_vistoria

Gerador automático de laudo de vistoria de entrada de imóvel residencial,
a partir de fotos organizadas por cômodo. Usa a API de visão do Google
Gemini (camada paga) para descrever cada cômodo em 8 categorias e
grava o resultado em arquivos `.txt`.

## Uso

Duas frentes, **um motor só** (`core/`). O que sai de laudo é igual nas duas.

**Aplicação web** (desde 25/09/2026) — navegador, celular, qualquer sistema:

```bash
docker compose up -d        # http://localhost:8000
```

Ver `docs/instalacao.md`, `docs/producao.md` e `docs/backup.md`.

**Linha de comando** — continua funcionando, sem alteração:

```bash
python main.py "C:\caminho\para\o\imovel"      # gera laudo + pendências (clássico)
python main.py "C:\caminho" --comodos "Sala"   # refaz só esses cômodos
python main.py "C:\caminho" --evidencias       # motor V2 (escopo, fronteira, cobertura)
python main.py "C:\caminho" --evidencias-v1    # motor V1, mantido para comparação
python validar.py "C:\caminho\para\o\imovel"   # aplica as decisões do vistoriador
python conferir.py "C:\caminho\para\o\imovel"  # confere as fotos contra o laudo
python revisar.py "C:\caminho\para\o\imovel"   # opcional: repadroniza o texto
python benchmark.py "C:\caminho" --motores classico evidencias_v2   # A/B
python -m pytest                              # 277 testes, nenhum chama a API
```

O `main.py` já roda a conferência no fim (desligue com `--sem-conferencia`);
o `conferir.py` avulso serve para laudo antigo, gerado antes dela.

A pasta do imóvel deve conter uma subpasta por cômodo, cada uma com as
fotos daquele cômodo (`.jpg`, `.jpeg`, `.png`, `.heic`).

Nessa ordem: `revisar.py` reescreve o texto dos itens, e pendências em
aberto deixariam de bater com o laudo — por isso ele se recusa a rodar se
houver pendência aberta (a não ser com `--ignorar-pendencias`).

Requer a variável de ambiente `GEMINI_API_KEY` definida antes de rodar
(gerada em https://aistudio.google.com/apikey, num projeto com
faturamento ativo — ver "Decisões importantes").

## Onde fica cada coisa

```
core/          MOTOR. Regra de laudo mora só aqui — CLI e web chamam isto.
  evidencias.py  escopo e validação determinística (o que pertence ao cômodo)
  pipeline.py    orquestração: fotos -> evidências -> escopo -> laudo
  style_guide.py, report_writer.py, gemini_client.py, validacao.py, ...
backend/       API FastAPI + SQLite. Traduz entre o motor e o banco.
frontend/      React + TypeScript + Vite. Responsivo, celular primeiro.
tests/         178 testes. Nenhum chama o Gemini.
*.py (raiz)    CLI + aliases de compatibilidade para core/
```

Os módulos na raiz com nome de módulo do motor (`config.py`,
`report_writer.py`, ...) são **aliases do mesmo objeto de módulo** que está em
`core/`, não cópias. Foi assim que o CLI continuou funcionando sem
alteração, e é o que garante que não existam duas versões da mesma regra.

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
- **conferir.py** — CLI da conferência: monta as fotos em mosaico
  (`image_utils.montar_mosaicos`), chama `gemini_client.conferir_comodo` e
  grava as divergências como pendências de validação.
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
- Toda chamada ao Gemini tem tempo limite de 5 min
  (`TEMPO_LIMITE_CHAMADA_SEGUNDOS`) e tenta de novo, com espera crescente,
  em `503` (sobrecarga do servidor) e em falha de rede/tempo limite
  (`httpx.TransportError`). Sem o tempo limite, em 18/09/2026 uma conexão
  pendurada pelo servidor travou o script por 10+ min sem erro nenhum.
  Cota estourada (`429`) não tem nova tentativa automática — não adianta.
- `main.py` isola falha por cômodo: se um cômodo der erro mesmo após as
  tentativas, o script segue para o próximo e, no fim, mostra o comando
  pronto com `--comodos` para refazer só os que falharam. As pendências
  são gravadas a cada cômodo (não só no fim), para uma interrupção não
  perder o trabalho feito; e o consolidado é montado de TODOS os
  `_vistoria.txt` no disco, inclusive dos cômodos não reprocessados.
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
- **Segunda olhada (desde 22/09/2026):** item com certeza até
  `config.LIMIAR_CORRECAO_AUTOMATICA` (50) não vai direto para o
  vistoriador — `_corrigir_itens_incertos` faz UMA chamada por cômodo, com
  as mesmas fotos, focada só nesses itens e citando a dúvida que o próprio
  modelo apontou; é o texto da segunda olhada que entra no laudo. Só roda
  quando algum item sai lá embaixo (na R. Correia de Freitas foi 1 item em
  14 cômodos), então não é "rodar tudo duas vezes" — o vistoriador
  recusou dobrar o custo. A ideia é que o trabalho manual dele fique na
  faixa do meio (de 50 a `LIMIAR_CERTEZA`): abaixo disso o modelo tenta
  resolver sozinho, acima não é pendência. Item que continuar baixo depois
  da segunda olhada VIRA pendência assim mesmo, com `MOTIVO_REANALISADO` —
  laudo é documento assinado, afirmação duvidosa não passa calada.
- **"Mais um/uma" é proibido** (pedido explícito do vistoriador, depois de
  aparecer em 3 laudos seguidos apesar da regra antiga). Item repetido vira
  UMA linha com a quantidade total ("*Duas portas..."), com "sendo um...
  e outro..." se algum detalhe diferir. Como só a regra no prompt já tinha
  falhado antes, há três camadas: (1) a regra ITENS REPETIDOS em
  `REGRAS_GERAIS`; (2) se ainda assim aparecer, `_consolidar_repetidos` faz
  UMA chamada de texto puro só para aquela categoria (fração de centavo,
  só quando o modelo desobedece); (3) o que sobrar vira pendência de
  certeza 0 com todas as linhas envolvidas. Vale na análise com fotos e no
  `revisar.py`.
  A detecção pega "Mais um/uma" (`linha_com_mais_um`) E o mesmo item em
  linhas separadas sem "Mais" (`grupos_de_itens_repetidos`: linhas que
  começam com quantidade + o mesmo substantivo). O segundo caso apareceu na
  R. Leopoldo (8 placas em 4 linhas, 3 armários em 3 linhas) depois que o
  "Mais um" sumiu. Posição/tamanho não fazem tipo diferente: armário
  inferior e aéreo são "armários" (confirmado pelo vistoriador).
  **Só "Mais um/uma" vira pendência** (camada 3) desde 22/09/2026: o
  substantivo repetido continua disparando a correção automática (camada
  2, onde o modelo julga com o texto na mão), mas o que sobrar dele fica
  como está. A heurística de substantivo é palpite e errou na Cozinha da
  R. Correia de Freitas, juntando "*Uma bancada em granito com cuba..."
  com "*Uma bancada de apoio...", que são móveis diferentes — o
  vistoriador decidiu "manter textos separados; apenas não colocar 'Mais
  uma...'".
  Os exemplos da regra usam [cor]/[n] de propósito: um exemplo tirado de
  um imóvel real foi copiado palavra por palavra pelo modelo no teste.
- **Testes:** só se escreve "testado" quando `--notas` confirma os testes
  (o modelo não vê teste em foto). Com testes confirmados, todo item
  elétrico e cada peça hidráulica levam "testado(s) e em funcionamento"
  (pedido do vistoriador, 18/09/2026) — e NADA além disso. Na R. Correia
  de Freitas (21/09/2026), com todos os testes confirmados nas notas, o
  modelo espalhou a frase pelo laudo inteiro: "paredes testadas e em
  funcionamento", "teto testado", "espelho testado". Por isso a regra no
  prompt tem uma trava determinística junto:
  `report_writer.limpar_testes_indevidos` tira a frase de paredes, piso,
  teto, porta, janela e OBS, e da mobília sem função elétrica ou
  hidráulica (armário, bancada, espelho, box, acessório). Roda dentro de
  `_montar_categoria`, então vale para `main.py` e para `revisar.py`.
- **Conferência (desde 22/09/2026):** depois do laudo escrito, `conferir.py`
  olha as fotos de novo e aponta o que divergir. Roda sozinha no fim do
  `main.py`. Três decisões de projeto, todas medidas:
  1. **Em dois passos, e nessa ordem.** Mandar fotos + texto pronto junto e
     pedir "aponte as divergências" devolveu lista VAZIA em dois cômodos
     testados, um deles com o teto descrito como forro de PVC sendo laje
     pintada: lendo o texto, o modelo concorda com o texto. Então o passo 1
     é um INVENTÁRIO às cegas (o modelo lista o que vê, sem ver o laudo) e o
     passo 2 compara inventário × laudo, em chamada de texto puro. Com isso
     o mesmo cômodo devolveu 25 itens e 4 divergências reais.
  2. **Fotos em mosaico.** O Gemini cobra por IMAGEM, não por pixel —
     medido com `usage_metadata`: 1.101 tokens por foto, igual em 1568px e
     em 256px. Diminuir resolução não economiza nada; juntar 4 fotos numa
     folha de contato economiza 4× (`FOTOS_POR_MOSAICO_CONFERENCIA`). A
     conferência inteira sai por ~1/4 de uma vistoria nova.
  3. **Nada entra sozinho no laudo.** A conferência só gera pendência: item
     faltando vira pendência `tipo="falta"`, em que a linha "Item" é uma
     PROPOSTA e o OK do vistoriador acrescenta ao laudo (ver `validacao`).
     Divergência de fato vira pendência normal com a sugestão já preenchida
     em CORREÇÃO. A precisão medida foi de ~50-60%: boa para uma lista de
     conferência, péssima para aplicar sem ler.
  Travas contra o vício conhecido da conferência — usar o silêncio do
  inventário como prova de ausência e encurtar o laudo: sugestão que remove
  item, que vira "Não se aplica." ou que encolhe a linha em mais de 25% é
  descartada, assim como a que se justifica com "o inventário não menciona"
  (`_ARGUMENTO_DE_AUSENCIA`). Sem elas, ela propôs apagar a trinca e o
  estufamento que o vistoriador tinha confirmado em campo.
- **Evidências e escopo (desde 25/09/2026):** o problema que motivou a
  evolução arquitetural. Uma foto guardada na pasta "Cozinha" NÃO prova que o
  que aparece nela é da cozinha: o fotógrafo enquadra a porta e pela porta se
  vê o corredor, o espelho do banheiro reflete o quarto, a última foto do
  quarto pega meia parede da sala. O motor antigo transformava tudo isso em
  afirmação sobre o cômodo — e laudo é documento assinado.

  A correção NÃO foi escrever mais parágrafos no prompt (já se tentou). O
  pertencimento virou VARIÁVEL do sistema, com estado e validação
  determinística:

      FOTO -> ANÁLISE DA FOTO -> EVIDÊNCIAS -> VALIDAÇÃO DE ESCOPO
           -> CONSOLIDAÇÃO -> LAUDO -> CONFERÊNCIA -> VALIDAÇÃO HUMANA

  O que o MODELO faz: olha a foto, diz o que vê, classifica a foto (valid /
  partial / out_of_scope) e dá DUAS confianças por evidência — "está claro na
  imagem?" e "é deste cômodo?". Elas são independentes de propósito: uma
  parede de corredor pode estar nitidíssima na foto da cozinha (percepção 99,
  escopo 10).

  O que o CÓDIGO faz (`core/evidencias.validar_escopo`), sem depender de o
  modelo ter obedecido a nada:
  - reflexo e ambiente adjacente são descartados por serem fatos categóricos,
    não questão de grau — 100% de certeza de que é um reflexo não transforma
    o reflexo em móvel do cômodo;
  - abaixo de `PISO_CONFIANCA_ESCOPO` (70) não vira texto;
  - corroboração entre fotos melhora a PERCEPÇÃO e nunca o pertencimento:
    uma parede de corredor fotografada de cinco ângulos continua do corredor;
  - contradição entre fotos NÃO é resolvida por votação (a foto isolada pode
    ser justamente a certa — foi o caso da parede vermelha em textura
    projetada da R. Correia de Freitas): vira conflito, com os dois lados
    preservados e rebaixados, para o vistoriador decidir;
  - sem evidência aprovada, o cômodo NÃO é escrito. Falso negativo com
    pendência explicando é melhor que laudo deduzido.

  A redação recebe SÓ as evidências aprovadas, **sem as fotos**. Com as
  imagens na mão o modelo volta a descrever o que vê, inclusive o que acabou
  de ser descartado; sem elas, o filtro deixa de ser um pedido no prompt e
  vira propriedade do que chega até ele.

  Nada disso apaga foto (ela continua no disco e no banco, com o motivo) nem
  entra sozinho no laudo: conflito de escopo vira pendência `scope_conflict`.

  Custo: cada foto continua sendo enviada UMA vez (o Gemini cobra por imagem).
  O acréscimo é um prompt repetido por lote de 10 fotos, mais uma chamada de
  texto puro. Fica desligado por padrão no CLI (`--evidencias` liga) até o
  vistoriador rodar os dois motores no mesmo imóvel e comparar; na web é o
  padrão da tela.

- **Motor de evidências V2 (desde 25/09/2026):** a V1 foi a benchmark com
  107 fotos reais (BWC Suíte + Quarto Suíte) e o resultado decidiu o resto.
  Ela acertou mais FATOS que o clássico — achou um ar-condicionado split
  inteiro que ele perdeu, corrigiu a bacia sanitária (o clássico escreveu
  "com caixa acoplada" numa bacia de válvula de parede), pegou a porta
  almofadada, as dobradiças douradas e a banheira de hidromassagem, e
  descartou o reflexo que teria criado um terceiro criado-mudo. E entregou um
  laudo pior em três pontos, que a V2 corrige POR CÓDIGO:

  1. **Elemento de fronteira.** Soleira, peitoril, batente, vistas, esquadria
     e porta-janela ficam entre dois ambientes por natureza, e o modelo as
     lia como "ambiente adjacente" justamente porque mostram o outro lado. O
     laudo perdeu a soleira do BWC e a categoria Janela inteira do Quarto.
     Agora existe `Escopo.FRONTEIRA` e o código PROMOVE o que o modelo
     rebaixou (`core/taxonomia.e_elemento_de_fronteira`). A peça é do cômodo;
     o cenário visto através dela não é — e quem decide qual dos dois a frase
     descreve é quem vem primeiro no texto.
  2. **Categoria.** O modelo propõe, o código decide
     (`core/taxonomia.categoria_canonica`): soleira → Porta mesmo dividindo
     dois pisos, peitoril → Janela, box → Mobília mesmo tendo folhas de
     correr, porta-papel/ganchos/toalheiro → Mobília. A V1 mandou o box para
     Porta e a soleira para Piso porque acreditou no modelo.
  3. **Cobertura.** Porta-papel, ganchos e toalheiro sumiram na consolidação
     sem que nada reclamasse. `core/cobertura.py` pergunta, por tipo de
     cômodo, se há evidência para cada tipo esperado; o que faltar vira busca
     DIRIGIDA nas mesmas fotos (máx. 3 por cômodo) e, se ainda faltar,
     pendência. A saída é sempre dúvida, nunca "o item não existe".

  Mais dois acertos determinísticos: contradição passou a ser por ATRIBUTO
  (cerâmica branca + rejunte cinza são campos diferentes da mesma parede,
  não versões concorrentes), e o rodapé ganhou três estados — no BWC o
  azulejo desce até o piso e NÃO há rodapé, mas os dois motores escreviam
  "com rodapé em cerâmica branca".

  Componentes elétricos têm regra própria: o que importa é nomear os TIPOS e
  a composição, não contar unidades. Contagem de placa quase sempre sai
  errada e deixa a frase pior; a contagem interna continua guardada.

- **A V2 reprovou no primeiro teste real, e isso está registrado de
  propósito.** A primeira versão gerou 220 pendências no BWC e 365 no Quarto.
  Duas causas: a detecção de contradição comparava par a par e emitia um
  conflito POR PAR (40 evidências de parede = 780 pares), e o inventário
  exaustivo gera uma evidência por FOTO, que o redator lia como um objeto —
  o mesmo chuveiro em duas fotos virou "dois chuveiros", um split em três
  fotos virou "três aparelhos". Depois de agregar conflito por
  (categoria, atributo) e agrupar evidências do mesmo objeto
  (`core/evidencias.agrupar_objetos`), caiu para 26 e 22.

  O agrupamento exige que o SUBSTANTIVO-NÚCLEO bata: material e cor são
  boilerplate de laudo, e com eles no critério "porta-papel em metal
  cromado" e "chuveiro em metal cromado" viravam o mesmo objeto — o que
  sumiria com um item, erro pior que contar duas vezes.

- **Os três motores convivem, e isso não é indecisão.** `--classico` é o que
  gerou todas as vistorias reais; `--evidencias-v1` fica para comparação;
  `--evidencias` é a V2, padrão na web. A V2 custa cerca de 3x o clássico
  (medido: ~US$ 0,10 contra ~US$ 0,035 nas 107 fotos), detalha menos mobília
  planejada e ainda gera pendência demais. Ela NÃO substitui o clássico
  enquanto o `benchmark.py` não provar isso em mais imóveis — de preferência
  com cozinha e área de serviço, onde ela está mais fraca.

- **Rastreabilidade (desde 25/09/2026):** no banco, `Foto -> Evidencia ->
  ItemLaudo -> Pendencia`. A pendência aponta para o item por ID, não pelo
  texto — no arquivo `.txt` ela era localizada procurando o texto exato e
  sumia assim que alguém reescrevia a linha.

- **Regras em produção vivem no banco**, não no repositório: várias
  instalações não podem escrever umas por cima das outras, e o repositório é
  público. O `regras_validadas.txt` continua sendo o conjunto INICIAL,
  semeado na primeira subida. Regra nova só vale por adoção explícita —
  nunca porque "o sistema aprendeu".

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
