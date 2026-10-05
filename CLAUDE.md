# laudo_vistoria

Gerador de laudo de vistoria de entrada de imóvel residencial a partir de
fotos organizadas por cômodo. Um modelo multimodal descreve cada cômodo em 8
categorias — paredes, piso, teto, porta, janela, eletrico, mobilia, obs — e o
resultado sai em `.txt`, em português. O padrão é o Google Gemini (camada
paga); GLM e Claude entram por configuração (ver "Multimodelo").

## Uso

Duas frentes, **um motor só** (`core/`): o laudo sai igual pelas duas.

**Linha de comando** — é o que gerou todas as vistorias reais:

```bash
python main.py "C:\caminho\do\imovel" --notas "..."   # laudo + conferência + pendências
python main.py "C:\caminho" --comodos "Sala" "BWC"    # refaz só esses cômodos
python main.py "C:\caminho" --evidencias              # motor V2 (padrão continua o clássico)
python main.py "C:\caminho" --evidencias-v1           # V1, só para comparação
python validar.py "C:\caminho"     # aplica as decisões do Pendencias_Validacao.txt
python conferir.py "C:\caminho"    # conferência avulsa, para laudo antigo
python revisar.py "C:\caminho"     # repadroniza o texto; recusa se houver pendência aberta
python benchmark.py "C:\caminho" --motores classico evidencias_v2   # A/B
python main.py "C:\caminho" --evidencias --provedor glm --validador claude
python benchmark.py "C:\caminho" --provedores gemini glm glm+claude  # A/B de provedor
python -m pytest                   # 354 testes, nenhum chama a API
```

- A pasta do imóvel tem uma subpasta por cômodo, com as fotos dele
  (`.jpg`, `.jpeg`, `.png`, `.heic`). O `.txt` de cada cômodo é gravado na
  própria subpasta; o `Laudo_Vistoria_Completo.txt` e o
  `Pendencias_Validacao.txt` na raiz do imóvel — **ambos têm dado de
  cliente**, nunca vão para o repositório.
- `--notas` é o fato confirmado em campo (cor de tinta, testes feitos, "imóvel
  sem luz"). O modelo usa em vez de adivinhar pela foto.
- `main.py` roda a conferência no fim (`--sem-conferencia` desliga).
- `revisar.py` reescreve os itens, e pendência aberta deixaria de bater com o
  laudo — por isso recusa rodar com pendência aberta (`--ignorar-pendencias`
  força). Ordem: `main.py` → `validar.py` → `revisar.py`.
- `LAUDO_MOTOR_EVIDENCIAS=1` troca o padrão do CLI para a V2; `--classico` força
  o clássico.
- Exige a chave do provedor em uso: `GEMINI_API_KEY` no padrão
  (aistudio.google.com/apikey, projeto com faturamento); `GLM_API_KEY`,
  `CLAUDE_API_KEY` e `CLAUDE_MODEL` para os outros (ver `.env.example`).
- No fim, `main.py` grava `Telemetria_Modelos.json` na raiz do imóvel:
  chamadas, tokens e custo, sem prompt nem imagem.

**Aplicação web** (desde 25/09/2026): `docker compose up -d`, depois
http://localhost:8000. Ver `docs/instalacao.md`, `docs/producao.md`,
`docs/backup.md`. **O Dockerfile e o compose nunca foram executados** — Docker
não está instalado na máquina de desenvolvimento. É o primeiro teste a fazer
antes de confiar neles.

## Onde fica cada coisa

```
core/                MOTOR. Regra de laudo mora só aqui; CLI e web chamam isto.
  config.py          modelo, limiares, categorias, preços por modelo
  style_guide.py     TODO o jeito de escrever: REGRAS_GERAIS, exemplos, prompts
  gemini_client.py   todas as chamadas a modelo (nome histórico): análise,
                     evidências, segunda olhada, redação, conferência
  providers/         Gemini, GLM e Claude atrás de um contrato só
  validacao_visual.py  validação visual seletiva + reanálise dirigida (V2)
  telemetria.py      uma linha por chamada: tokens, tempo, custo
  image_utils.py     fotos -> Imagem neutra; mosaicos da conferência
  room_processor.py  processa um cômodo (motor clássico)
  pipeline.py        escolhe o motor e orquestra fotos -> evidências -> laudo
  evidencias.py      validação de escopo, agrupamento de objetos, conflitos
  taxonomia.py       escopos, elementos de fronteira, categoria canônica, rodapé
  cobertura.py       checklist por tipo de cômodo -> busca dirigida
  report_writer.py   grava os .txt; travas determinísticas de texto
  validacao.py       formato e aplicação do Pendencias_Validacao.txt
backend/app/         FastAPI + SQLAlchemy + SQLite (Alembic). Motor <-> banco.
frontend/src/        React + TypeScript + Vite, celular primeiro.
tests/               354 testes (+3 de integração com API real, desligados).
main.py, validar.py, conferir.py, revisar.py, benchmark.py    CLI
config.py, style_guide.py, gemini_client.py, ... (raiz)       aliases
regras_validadas.txt regras de redação adotadas (conjunto inicial)
```

Os módulos da raiz com nome de módulo do motor **não são cópias**: fazem
`sys.modules[__name__] = core.<modulo>`, então são o mesmo objeto. Edite
sempre em `core/`.

Só `core/providers/` conhece SDK ou HTTP de modelo. O resto do motor manda
partes (texto e `Imagem`), um schema NEUTRO (`providers/esquema.py`) e um teto
de saída, e recebe texto JSON. Todas as chamadas passam por
`gemini_client._gerar_com_retry`. Provedor novo = um arquivo em `providers/`.

## Regras que não se quebram

Cada uma tem o porquê em "Decisões", abaixo.

1. **Foto de cliente só vai a provedor pago, que não treina com os dados.**
   Gemini na camada paga (a gratuita permite ao Google usar o conteúdo com
   revisão humana); GLM e Claude só depois de o vistoriador conferir a política
   de dados do provedor (LGPD). Por isso o padrão continua Gemini.
2. **Limiar fica no código, nunca no prompt.** Modelo que sabe o corte
   responde logo acima dele.
3. **Nada entra sozinho no laudo.** Conferência, cobertura e conflito de escopo
   só geram pendência. Laudo é documento assinado.
4. **Estilo do laudo só muda em `style_guide.py`.** Item por linha começando
   com `*`, sem linha em branco entre itens, padrão de frase fixo.
5. **Motor clássico: 1 chamada de API por cômodo**, com todas as fotos e as 8
   categorias num JSON só (eram 8 chamadas). Manter ao mexer em prompt ou
   parsing.
6. **"testado" só quando `--notas` confirma os testes**, e só em item elétrico
   ou peça hidráulica. O modelo não vê teste em foto.
7. **"Mais um/uma" é proibido.** Item repetido é UMA linha com o total
   ("*Duas portas..."), com "sendo um... e outro..." se algo diferir.
8. **`regras_validadas.txt` fica no repositório PÚBLICO**: só regra geral de
   redação, nunca endereço, cliente ou fato de um imóvel. Fato de imóvel ("a
   cozinha não tem porta") se resolve com CORRIGIR/REMOVER ou `--notas` —
   como regra, o modelo passaria a achar que nenhuma cozinha tem porta.
9. **O validador não escreve e não ressuscita.** O validador visual só
   confirma, corrige ou tira evidência que o código ACEITOU; o veto é aplicado
   por `validar_escopo`, depois de todas as regras. Conflito entre fotos não
   vai ao validador (não é votação), e falha de validação nunca vira aprovação.

## Revisão antes de entregar um laudo

O motor erra de formas repetidas. Antes de passar as pendências ao
vistoriador, confira nas fotos — não no texto:

- **Rodapé e roda-teto.** Os erros mais frequentes. Na R. Octavio de Carvalho
  o laudo disse "sem rodapé" em dois cômodos que têm rodapé, e só achou a
  moldura de gesso em um dos quatro cômodos que têm.
- **Luminária.** O modelo tende a "luminária de embutir em LED". Na R.
  Octavio eram plafons de sobrepor em todos os cômodos, e o laudo errou o tipo
  em cinco deles.
- **Banheiro.** Chuveiro, ducha higiênica, registros e ralo somem com
  facilidade — a R. Octavio saiu com box e sem chuveiro.
- **Categoria ou item grande faltando.** Na R. Octavio a Sala saiu sem Porta
  com a porta de entrada nas fotos dela, e a churrasqueira sem parapeito,
  ralo e condensadora de ar-condicionado. Cômodo sem Porta ou Janela merece
  olhar.
- **Escopo.** O espelho mostra outro cômodo e pode duplicar contagem.
  Interruptor visto pelo espelho ou pela porta aberta pode ser do vizinho (o
  do BWC da R. Octavio fica no corredor).
- **Nota genérica do vistoriador não vale para todo cômodo.** "Paredes possuem
  marcas e algumas paredes possuem furos" (R. Paulo Furtado Velasco) foi
  aplicado a todas as paredes pintadas; só a Sala tinha marcas, e o BWC Suíte
  nem é pintado. Confira cômodo a cômodo.
- **A conferência acerta ~metade.** Recuse a sugestão que piora: acrescentar
  pintura a parede toda revestida, trocar a redação sem corrigir fato,
  duplicar item que já está em outra linha.

**Semântica das decisões** (`core/validacao.aplicar_no_texto`), fácil de
errar:

| Pendência | OK | CORRIGIR | REMOVER |
|---|---|---|---|
| normal (a linha está no laudo) | mantém a linha | troca pela CORREÇÃO | **apaga a linha do laudo** |
| `Tipo: falta` (proposta) | acrescenta o Item | acrescenta a CORREÇÃO | descarta a proposta |
| `Tipo: scope_conflict` (conflito de escopo ou validação visual) | **erro, fica aberta** | acrescenta a CORREÇÃO | fica fora do laudo |

Para **recusar** a sugestão de uma pendência normal e manter o laudo, a
decisão é **OK**, nunca REMOVER. Pendência sem DECISÃO fica aberta e não mexe
no laudo. O `Item:` de pendência normal tem que bater ao caractere com a linha
do `.txt` — copie da linha, não redigite.

No `scope_conflict` o `Item:` é um **resumo** do conflito, não linha de laudo,
e nunca é acrescentado. OK é recusado de propósito (05/10/2026): o laudo não
tem o que manter e o OK é ambíguo — lido como "confirmo que é deste cômodo",
sumiria em silêncio um item real; "deixar fora" já é o REMOVER. A web faz o
mesmo (`servicos.decidir_pendencia`). Os conflitos do validador visual
(motivo "VALIDAÇÃO VISUAL") chegam ao `.txt` com esse mesmo tipo.

## Decisões e o porquê

**Modelo e custo.** `gemini-3.5-flash-lite` (`config.MODEL_NAME`), escolhido em
11/09/2026 quando o `gemini-3.6-flash` estourou a cota de 20 req/dia no meio
de uma vistoria. Na camada paga a cota some, mas o flash-lite ficou:
qualidade equivalente nos testes reais e entrada 5× mais barata (US$ 0,30 vs.
1,50 por milhão de tokens). Trocar de modelo exige teste real de ponta a
ponta, não só `models.list()`. Faturamento ativo desde 18/09/2026 (Nível 1,
pré-pago); a maior vistoria custou ~US$ 0,14 (11 cômodos, 358 fotos). Conferir
em aistudio.google.com/projects, coluna "Nível de faturamento".

**O Gemini cobra por IMAGEM, não por pixel.** Medido com `usage_metadata`:
1.101 tokens por foto, igual em 1568px e em 256px. Reduzir resolução não
economiza nada; juntar fotos num mosaico economiza.

**Resiliência.** Toda chamada tem limite de 5 min
(`TEMPO_LIMITE_CHAMADA_SEGUNDOS`) — sem ele, em 18/09/2026 uma conexão
pendurada travou o script 10+ min sem erro. Nova tentativa com espera
crescente em `503` e `httpx.TransportError`; `429` não tenta de novo. O
`main.py` isola falha por cômodo e no fim imprime o `--comodos` para refazer
só os que falharam; pendências são gravadas a cada cômodo, e o consolidado é
montado de todos os `_vistoria.txt` do disco.

**Certeza (18/09/2026).** O modelo dá 0–100 por item; abaixo de
`LIMIAR_CERTEZA` (85) vira pendência, e o item continua no laudo — a lista é
de conferência, não de exclusão. **É autoavaliação, não probabilidade:** no
primeiro teste real deu ≥85% para tudo, inclusive "Janela: Não se aplica."
num cômodo onde a rodada anterior tinha visto uma janela de correr. Serve de
triagem, não de garantia. O `response_schema` pede `{texto, motivo, certeza}`
nessa ordem: o modelo escreve, diz o que duvida, e só então dá a nota.

**Segunda olhada (22/09/2026).** Item com certeza ≤
`LIMIAR_CORRECAO_AUTOMATICA` (50) ganha UMA chamada extra por cômodo
(`_corrigir_itens_incertos`), com as mesmas fotos e citando a dúvida do
próprio modelo. Só roda quando algo sai lá embaixo — o vistoriador recusou
dobrar o custo rodando tudo duas vezes. A faixa 50–85 é o trabalho manual
dele. O que continuar baixo vira pendência com `MOTIVO_REANALISADO`.

**"Mais um/uma" em três camadas**, porque só a regra no prompt já tinha
falhado em 3 laudos seguidos: (1) regra ITENS REPETIDOS em `REGRAS_GERAIS`;
(2) se aparecer, `_consolidar_repetidos` faz uma chamada de texto puro só
naquela categoria; (3) o que sobrar vira pendência de certeza 0. A detecção
pega "Mais um" (`linha_com_mais_um`) e o mesmo substantivo em linhas
separadas (`grupos_de_itens_repetidos` — na R. Leopoldo, 8 placas em 4
linhas). Só "Mais um" vira pendência: a heurística de substantivo errou na
R. Correia de Freitas juntando duas bancadas diferentes, e o vistoriador
decidiu manter linhas separadas nesse caso. Posição e tamanho não fazem tipo
diferente — armário inferior e aéreo são "armários". Os exemplos da regra
usam `[cor]`/`[n]` porque um exemplo tirado de imóvel real foi copiado
palavra por palavra.

**Trava de "testado".** Com testes confirmados, todo item elétrico e cada
peça hidráulica levam "testado(s) e em funcionamento" (pedido do vistoriador,
18/09/2026). Na R. Correia de Freitas o modelo espalhou a frase por paredes,
teto e espelho, então há trava determinística:
`report_writer.limpar_testes_indevidos` tira a frase de paredes, piso, teto,
porta, janela, OBS e da mobília sem função elétrica ou hidráulica. Roda em
`_montar_categoria`, logo vale no `main.py` e no `revisar.py`.

**Conferência (22/09/2026)**, três decisões medidas:
1. **Dois passos.** Fotos + laudo pronto juntos devolveram lista VAZIA — lendo
   o texto, o modelo concorda com o texto (aceitou "forro de PVC" numa laje
   pintada). Passo 1 é inventário às cegas; passo 2 compara inventário ×
   laudo em texto puro. O mesmo cômodo passou a dar 4 divergências reais.
2. **Mosaico** de 4 fotos por imagem (`FOTOS_POR_MOSAICO_CONFERENCIA`): a
   conferência inteira custa ~1/4 de uma vistoria.
3. **Só gera pendência**, precisão medida de ~50–60%. Item faltando vira
   `tipo="falta"`; divergência vira pendência com a sugestão em CORREÇÃO.

Travas contra o vício de usar o silêncio do inventário como prova de
ausência: é descartada a sugestão que remove item, que vira "Não se aplica.",
que encolhe a linha mais de 25% ou que se justifica com "o inventário não
menciona" (`_ARGUMENTO_DE_AUSENCIA`). Sem elas, ela propôs apagar trinca e
estufamento confirmados em campo.

**Evidências e escopo (25/09/2026)** — o motivo da evolução arquitetural.
Foto na pasta "Cozinha" não prova que o que aparece nela é da cozinha: pela
porta se vê o corredor, o espelho reflete o quarto. Escrever mais parágrafos
no prompt já tinha falhado; o pertencimento virou variável do sistema:

    FOTO -> ANÁLISE -> EVIDÊNCIAS -> ESCOPO -> TAXONOMIA -> COBERTURA
         -> CONSOLIDAÇÃO -> LAUDO -> CONFERÊNCIA -> VALIDAÇÃO HUMANA

O **modelo** diz o que vê e dá duas confianças independentes por evidência:
percepção ("está claro?") e escopo ("é deste cômodo?") — uma parede de
corredor pode estar nítida na foto da cozinha (99 e 10). O **código**
(`evidencias.validar_escopo`) decide sem depender de obediência:
- reflexo e ambiente adjacente são descartados — fato categórico, não grau;
- escopo abaixo de `PISO_CONFIANCA_ESCOPO` (70) não vira texto;
- corroboração entre fotos sobe a percepção, **nunca** o escopo;
- contradição não é votação (a foto isolada pode ser a certa — a parede
  vermelha em textura da R. Correia de Freitas): vira conflito com os dois
  lados, para o vistoriador;
- sem evidência aprovada, o cômodo não é escrito.

A redação recebe só as evidências aprovadas, **sem as fotos**: com as imagens
na mão o modelo volta a descrever o que acabou de ser descartado. Nenhuma
foto é apagada; conflito vira pendência `scope_conflict`.

**V2 (25/09/2026).** Benchmark da V1 com 107 fotos reais (BWC Suíte + Quarto
Suíte): acertou mais fatos que o clássico (um split inteiro, bacia de válvula
de parede que o clássico chamou de caixa acoplada, banheira de
hidromassagem) e entregou laudo pior em três pontos, corrigidos por código:
1. **Fronteira.** Soleira, peitoril, batente, vistas, esquadria e
   porta-janela mostram o outro lado, e o modelo os marcava como adjacentes —
   sumiram a soleira do BWC e a Janela inteira do Quarto. Agora existe
   `Escopo.FRONTEIRA` e `taxonomia.e_elemento_de_fronteira` promove. A peça é
   do cômodo; o cenário através dela não é.
2. **Categoria.** O modelo propõe, `taxonomia.categoria_canonica` decide:
   soleira → Porta, peitoril → Janela, box → Mobília, porta-papel/ganchos/
   toalheiro → Mobília.
3. **Cobertura.** Porta-papel, ganchos e toalheiro sumiram sem reclamação.
   `cobertura.py` checa por tipo de cômodo; o que faltar vira busca dirigida
   nas mesmas fotos (máx. 3 por cômodo) e, se persistir, pendência — dúvida,
   nunca "não existe".

Também: contradição é por **atributo** (cerâmica branca e rejunte cinza não
competem), rodapé tem três estados (presente / ausente / não visível), e em
componentes elétricos importa a composição, não a contagem de placas.

**Placas elétricas sem número, em todos os motores (29/09/2026).** O que a
V2 fazia virou regra do vistoriador: "*Placas em polímero na cor [cor],
sendo tomadas, interruptores e placas cegas, em bom estado." — só os tipos
que existem no cômodo, singular quando há um só. Mora em três lugares que
têm que concordar: o bloco "Tomadas/interruptores" do `style_guide.py`, a
exceção em ITENS REPETIDOS (que senão mandaria juntar "com a quantidade
total") e `regras_validadas.txt`. `test_placas_eletricas_sem_quantidade_no_prompt`
barra a volta de exemplo contado — o modelo copia exemplo mais do que obedece
regra.

**A V2 reprovou no primeiro teste real, registrado de propósito**: 220
pendências no BWC e 365 no Quarto. Conflito era emitido por PAR (40
evidências de parede = 780 pares), e o redator lia uma evidência por foto
como um objeto — o mesmo chuveiro em duas fotos virou "dois chuveiros".
Agregar conflito por (categoria, atributo) e agrupar objetos
(`evidencias.agrupar_objetos`) baixou para 26 e 22. O agrupamento exige que o
**substantivo-núcleo** bata: com material e cor no critério, "porta-papel em
metal cromado" e "chuveiro em metal cromado" viravam um objeto só — sumir
item é pior que contar duas vezes.

**Três motores convivem, e isso não é indecisão.** O clássico gerou todas as
vistorias reais e é o padrão do CLI; a V1 fica para comparação; a V2 é o
padrão na web. A V2 custa ~3× (US$ 0,10 contra 0,035 nas 107 fotos),
detalha menos mobília planejada e ainda gera pendência demais. Não substitui
o clássico enquanto o `benchmark.py` não provar em mais imóveis — de
preferência com cozinha e área de serviço, onde ela é mais fraca.

**Multimodelo (05/10/2026)** — GLM como analista barato, Claude como
auditor visual seletivo, sem tirar o Gemini. Grafo da V2 com validador:

    FOTOS -> ANÁLISE (analista) -> ESCOPO (código) -> BUSCA DIRIGIDA
          -> POLÍTICA (código) -> VALIDAÇÃO (validador, com a foto)
          -> REANÁLISE (analista, só o ponto em dúvida) -> VALIDAÇÃO
          -> ESCOPO de novo (código) -> COBERTURA -> REDAÇÃO -> LAUDO

- **Padrão inalterado**: Gemini, validador desligado. Nada do caminho antigo
  muda sem `VISION_PROVIDER`/`VALIDATION_ENABLED`. Teste prova, schema a
  schema, que o pedido ao Gemini é o mesmo objeto de antes da abstração.
- **GLM-5.3-Flash pelo OpenCode Zen**, HTTP compatível com OpenAI. Conferido
  na documentação oficial em 05/10/2026: endpoint `opencode.ai/zen/v1`,
  `Bearer`, US$ 0,15/0,50 por milhão, retenção zero (exceto modelos
  gratuitos); o models.dev o registra como multimodal. **Não documentado:**
  que o Zen repassa a imagem e aceita JSON Schema. Só
  `INTEGRATION_TESTS=1 pytest tests/test_integracao_provedores.py` prova; se
  o schema for recusado, `GLM_FORMATO_RESPOSTA=json_object`.
- **Claude via HTTP**, saída estruturada por ferramenta forçada; sem SDK (não
  traria vantagem). O modelo vem de `CLAUDE_MODEL`, nunca fixo no código.
- **O validador recebe a FOTO**, não só o texto do analista: lendo o texto, o
  modelo concorda com o texto (a lição da conferência, 22/09/2026).
- **Política no código** (`config.py`): confiança final < 85, fronteira
  promovida, defeito/OBS e tudo que a busca dirigida achou (mandado procurar,
  o modelo tende a "achar"); teto de 30 por cômodo, uma chamada por foto. Fora
  do teto segue como o escopo decidiu, marcada `nao_validada_limite`.
- **Correção é aplicada** (precedente: a segunda olhada também troca o texto
  do item duvidoso), guardando a observação original;
  `VALIDATION_CORRECTED_POLICY=conflito` manda os dois lados ao vistoriador.
- **Reanálise atualiza a MESMA evidência** (mesmo id, `revisao` +1), máx. 1.
  Dúvida que persiste vira `nao_resolvida` e sai do laudo, com pendência.
- **Resposta fora do contrato não é interpretada** (decisão fora do enum, id
  repetido, correção sem texto, reanálise sem foco): a evidência fica em
  estado seguro (`VALIDATION_FAILURE_POLICY`; padrão: não entra sem
  conferência).
- **Só V2.** O clássico e a V1 não têm evidência para validar.
- **Banco: tabelas novas, nenhuma coluna nova** — a subida faz `create_all`,
  que cria tabela mas não coluna; banco antigo sem migração não quebra.
- **Nada disso foi testado com API real** até 05/10/2026: custo, qualidade e
  taxa de reanálise do GLM+Claude são desconhecidos. Antes de trocar o
  padrão: `benchmark.py --provedores` em imóveis reais.

**Rastreabilidade no banco:** `Foto -> Evidencia -> ItemLaudo -> Pendencia`.
A pendência aponta o item por ID; no `.txt` ela é achada pelo texto exato e
se perde se alguém reescrever a linha.

**Regras em produção vivem no banco**, não no repositório: várias
instalações não podem sobrescrever umas às outras, e o repositório é público.
`regras_validadas.txt` é só o conjunto inicial, semeado na primeira subida.
Regra nova vale por adoção explícita, nunca porque "o sistema aprendeu".
