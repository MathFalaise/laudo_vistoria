"""
Camada fina sobre a API do Google Gemini: envia as fotos
de um cômodo + o prompt com as 8 categorias e retorna o texto gerado em JSON.
"""

import json
import re
import time

import httpx
from google import genai
from google.genai import errors, types

from core.config import (API_KEY, MODEL_NAME, CATEGORIAS, LIMIAR_CERTEZA,
                    LIMIAR_CONFERENCIA, LIMIAR_CORRECAO_AUTOMATICA,
                    ROTULOS_CATEGORIA)
from core.report_writer import (
    TEXTO_NAO_SE_APLICA,
    TEXTO_SEM_OBSERVACOES,
    grupos_de_itens_repetidos,
    limpar_testes_indevidos,
    linha_com_mais_um,
    montar_texto_comodo,
    normalizar_linha,
    texto_vazio_da_categoria,
)
from core.evidencias import (AnaliseFoto, EscopoFoto, agrupar_objetos,
                             analise_de_dict, evidencia_de_dict)
from core.style_guide import (montar_prompt_comodo, montar_prompt_consolidacao,
                         montar_prompt_consolidacao_evidencias,
                         montar_prompt_consolidacao_v2,
                         montar_prompt_correcao, montar_prompt_divergencias,
                         montar_prompt_escopo, montar_prompt_escopo_v2,
                         montar_prompt_inventario, montar_prompt_revisao,
                         montar_prompt_segunda_olhada_dirigida)
from core.taxonomia import tipos_eletricos_presentes

# Nº de tentativas e espera entre elas em falha transitória: 503 (servidor
# sobrecarregado — a própria API pede pra tentar de novo) ou falha de rede,
# inclusive o tempo limite abaixo estourar.
MAX_TENTATIVAS = 4
ESPERA_BASE_SEGUNDOS = 10

# Tempo máximo de espera por UMA chamada. Sem isso, uma conexão que o
# servidor deixou pendurada trava o script para sempre — aconteceu em
# 18/09/2026, com o processo parado 10+ minutos esperando resposta. O
# cômodo mais lento já medido levou ~2 min (51 fotos); 5 min é folga.
TEMPO_LIMITE_CHAMADA_SEGUNDOS = 300

SEM_MOTIVO = "(o modelo não explicou)"
MOTIVO_REPETIDOS = (
    'linha começando com "Mais um/uma", e a correção automática não '
    "resolveu — junte com a linha anterior numa só, com a quantidade total "
    '(ex.: "*Duas portas ...", "*Três armários ..., sendo ...")'
)

# Justificativa de conferência baseada no SILÊNCIO do inventário — ver
# conferir_comodo.
_ARGUMENTO_DE_AUSENCIA = re.compile(
    r"n[ãa]o\s+(menciona|cita|lista|informa|aponta|detalha|descreve|traz|"
    r"registra|faz\s+men[çc][ãa]o)", re.IGNORECASE
)

# Item que passou pela segunda olhada nas fotos e MESMO ASSIM ficou com
# certeza baixa (ver _corrigir_itens_incertos).
MOTIVO_REANALISADO = (
    "o modelo já olhou as fotos uma segunda vez, só para este item, e "
    "continuou sem certeza — confira você mesmo"
)


def criar_cliente() -> genai.Client:
    if not API_KEY:
        raise RuntimeError(
            "Defina a variável de ambiente GEMINI_API_KEY antes de rodar o script "
            "(gere uma em https://aistudio.google.com/apikey, num projeto com "
            "faturamento ativo — ver CLAUDE.md)."
        )
    return genai.Client(
        api_key=API_KEY,
        http_options=types.HttpOptions(timeout=TEMPO_LIMITE_CHAMADA_SEGUNDOS * 1000),
    )


def _extrair_json(texto: str) -> dict:
    """Extrai o objeto JSON da resposta do modelo, mesmo que ele venha
    embrulhado em ```json ... ```, com espaços/quebras extras, ou dentro
    de uma lista (ex.: [{...}]) em vez de um objeto solto."""
    texto = texto.strip()
    match = re.search(r"```(?:json)?\s*(.*)\s*```", texto, re.DOTALL)
    if match:
        texto = match.group(1).strip()

    dados = json.loads(texto)
    if isinstance(dados, list):
        if not dados or not isinstance(dados[0], dict):
            raise ValueError("Resposta é uma lista JSON sem objeto de categorias dentro.")
        dados = dados[0]
    return dados


# Quantos caracteres da resposta do modelo entram na mensagem de erro.
# O suficiente pra depurar um JSON malformado, sem despejar o laudo
# inteiro (descrição do imóvel do cliente) num traceback que pode acabar
# colado em e-mail, issue ou canal de suporte.
LIMITE_TRECHO_ERRO = 300


def _trecho_para_erro(texto: str) -> str:
    """Devolve só o começo da resposta do modelo, para mensagens de erro."""
    if not texto:
        return "(resposta vazia)"
    texto = texto.strip()
    if len(texto) <= LIMITE_TRECHO_ERRO:
        return texto
    omitidos = len(texto) - LIMITE_TRECHO_ERRO
    return f"{texto[:LIMITE_TRECHO_ERRO]}... [+{omitidos} caracteres omitidos]"


def _schema_categorias(categorias: list) -> types.Schema:
    """Monta o response_schema que força o modelo a devolver um objeto
    JSON plano com uma chave string por categoria, evitando que a
    resposta venha embrulhada em lista ou com chaves inesperadas."""
    return types.Schema(
        type="OBJECT",
        properties={categoria: types.Schema(type="STRING") for categoria in categorias},
        required=categorias,
    )


def _schema_item_com_certeza() -> types.Schema:
    """Um item do laudo como o modelo devolve: texto, motivo e certeza."""
    return types.Schema(
        type="OBJECT",
        properties={
            "texto": types.Schema(type="STRING"),
            "motivo": types.Schema(type="STRING"),
            "certeza": types.Schema(type="INTEGER", minimum=0, maximum=100),
        },
        required=["texto", "motivo", "certeza"],
        property_ordering=["texto", "motivo", "certeza"],
    )


def _schema_itens_com_certeza(categorias: list) -> types.Schema:
    """Schema da análise de um cômodo: cada categoria é uma lista de itens
    {texto, motivo, certeza}. A ordem texto -> motivo -> certeza é
    proposital: o modelo escreve o item, diz o que nele é duvidoso e só
    então dá a nota — em vez de se comprometer com um número antes."""
    item = _schema_item_com_certeza()
    return types.Schema(
        type="OBJECT",
        properties={
            categoria: types.Schema(type="ARRAY", items=item, min_items=1)
            for categoria in categorias
        },
        required=categorias,
        property_ordering=categorias,
    )


def _registros(itens) -> list:
    """Converte a lista de itens devolvida pelo modelo em
    [(linha, certeza, motivo)], uma tupla por linha do laudo. Um "texto" com
    várias linhas vira várias linhas com a mesma certeza."""
    registros = []
    if not isinstance(itens, list):
        return registros
    for item in itens:
        if not isinstance(item, dict):
            continue
        try:
            certeza = max(0, min(100, int(item.get("certeza", 0))))
        except (TypeError, ValueError):
            certeza = 0
        motivo = " ".join(str(item.get("motivo", "")).split())
        for bruta in str(item.get("texto", "")).splitlines():
            linha = normalizar_linha(bruta)
            if linha:
                registros.append((linha, certeza, motivo))
    return registros


def _tem_itens_repetidos(linhas: list) -> bool:
    """A regra ITENS REPETIDOS foi violada: linha "Mais um/uma..." ou o
    mesmo tipo de item em mais de uma linha."""
    return any(linha_com_mais_um(linha) for linha in linhas) or bool(grupos_de_itens_repetidos(linhas))


def _consolidar_repetidos(cliente: genai.Client, categoria: str, registros: list) -> list:
    """Conserta uma categoria que violou a regra ITENS REPETIDOS ("Mais
    um/uma", ou o mesmo item em linhas separadas): UMA chamada de texto puro
    (sem fotos — custa uma fração de centavo) que junta os itens repetidos
    numa linha só. Só roda quando o modelo desobedece.

    Linhas que não mudaram mantêm a certeza original; linhas novas (as
    consolidadas) herdam a MENOR certeza entre as que sumiram. Se a chamada
    falhar, devolve os registros originais — a trava de _montar_categoria
    manda o que sobrar para validação."""
    if not _tem_itens_repetidos([linha for linha, _, _ in registros]):
        return registros

    rotulo = ROTULOS_CATEGORIA[categoria]
    texto = "\n".join(linha for linha, _, _ in registros)
    schema = types.Schema(
        type="OBJECT",
        properties={"linhas": types.Schema(type="ARRAY", items=types.Schema(type="STRING"), min_items=1)},
        required=["linhas"],
    )
    try:
        bruto = _gerar_com_retry(
            cliente,
            [montar_prompt_consolidacao(rotulo, texto)],
            response_schema=schema,
            max_output_tokens=4096,
            descricao_erro=f"a correção de itens repetidos ({rotulo})",
        )
        novas = [normalizar_linha(str(linha)) for linha in _extrair_json(bruto).get("linhas", [])]
        novas = [linha for linha in novas if linha]
    except Exception as erro:
        print(f"  Não consegui juntar os itens repetidos em {rotulo} automaticamente ({erro.__class__.__name__}).", flush=True)
        return registros
    if not novas:
        return registros

    print(f"  Corrigido automaticamente: itens repetidos em {rotulo}.", flush=True)
    originais = {linha: (certeza, motivo) for linha, certeza, motivo in registros}
    sumiram = [registro for registro in registros if registro[0] not in novas]
    menos_certa = min(sumiram or registros, key=lambda registro: registro[1])
    herdada = (menos_certa[1], menos_certa[2])
    return [(linha, *originais.get(linha, herdada)) for linha in novas]


def _schema_inventario() -> types.Schema:
    item = types.Schema(
        type="OBJECT",
        properties={
            "categoria": types.Schema(type="STRING", enum=list(CATEGORIAS)),
            "item": types.Schema(type="STRING"),
            "certeza": types.Schema(type="INTEGER", minimum=0, maximum=100),
        },
        required=["categoria", "item", "certeza"],
        property_ordering=["categoria", "item", "certeza"],
    )
    return types.Schema(
        type="OBJECT",
        properties={"inventario": types.Schema(type="ARRAY", items=item, min_items=1)},
        required=["inventario"],
    )


def _schema_divergencias() -> types.Schema:
    item = types.Schema(
        type="OBJECT",
        properties={
            "categoria": types.Schema(type="STRING", enum=list(CATEGORIAS)),
            "tipo": types.Schema(type="STRING", enum=["falta", "errado"]),
            "linha_atual": types.Schema(type="STRING"),
            "linha_sugerida": types.Schema(type="STRING"),
            "o_que_vi": types.Schema(type="STRING"),
            "certeza": types.Schema(type="INTEGER", minimum=0, maximum=100),
        },
        required=["categoria", "tipo", "linha_atual", "linha_sugerida", "o_que_vi", "certeza"],
        property_ordering=["categoria", "tipo", "linha_atual", "linha_sugerida",
                           "o_que_vi", "certeza"],
    )
    return types.Schema(
        type="OBJECT",
        properties={"divergencias": types.Schema(type="ARRAY", items=item)},
        required=["divergencias"],
    )


def conferir_comodo(
    cliente: genai.Client,
    mosaicos: list,
    nome_comodo: str,
    dados: dict,
    quantidade_fotos: int,
    notas_extras: str = "",
) -> list:
    """CONFERÊNCIA de um cômodo já escrito, em DOIS passos:

    1. com as fotos (em mosaico, barato), o modelo faz o INVENTÁRIO do que
       vê — sem ver o laudo;
    2. numa chamada de TEXTO PURO, compara o inventário com o laudo e
       devolve o que não bate.

    A ordem importa. Mandar fotos + laudo juntos e pedir "aponte as
    divergências" foi testado em 22/09/2026 e devolveu lista VAZIA em dois
    cômodos, um deles com erro grosseiro no teto: lendo o texto, o modelo
    concorda com o texto. Listando o que vê, ele acha.

    Devolve pendências prontas para validacao.salvar_pendencias:
    - "falta" vira pendência tipo="falta" (a linha sugerida ainda não está
      no laudo; o vistoriador aceita com OK);
    - "errado" vira pendência normal, ancorada na linha atual, com a
      sugestão já preenchida em CORREÇÃO.

    Descarta o que vier com certeza abaixo de config.LIMIAR_CONFERENCIA e o
    que citar uma linha que não existe no laudo — pendência que não bate com
    o texto só atrapalha na hora de aplicar."""
    texto_laudo = montar_texto_comodo(nome_comodo, dados)

    bruto = _gerar_com_retry(
        cliente,
        list(mosaicos) + [montar_prompt_inventario(
            nome_comodo, quantidade_fotos, len(mosaicos), notas_extras)],
        response_schema=_schema_inventario(),
        max_output_tokens=8192,
        descricao_erro=f"o inventário do cômodo '{nome_comodo}'",
    )
    inventario = [
        item for item in _extrair_json(bruto).get("inventario", [])
        if isinstance(item, dict) and str(item.get("item", "")).strip()
    ]
    if not inventario:
        print("  Conferência: inventário vazio, nada a comparar.", flush=True)
        return []

    bruto = _gerar_com_retry(
        cliente,
        [montar_prompt_divergencias(nome_comodo, texto_laudo, inventario, notas_extras)],
        response_schema=_schema_divergencias(),
        max_output_tokens=8192,
        descricao_erro=f"a comparação do inventário de '{nome_comodo}'",
    )
    divergencias = _extrair_json(bruto).get("divergencias", [])

    pendencias, descartadas = [], 0
    for divergencia in divergencias:
        categoria = divergencia.get("categoria")
        if categoria not in CATEGORIAS:
            descartadas += 1
            continue
        try:
            certeza = int(divergencia.get("certeza", 0))
        except (TypeError, ValueError):
            certeza = 0
        if certeza < LIMIAR_CONFERENCIA:
            descartadas += 1
            continue

        # A sugestão passa pelas mesmas travas do laudo: ela entra no texto
        # se o vistoriador aceitar, então não pode chegar com "paredes
        # testadas e em funcionamento" (aconteceu na primeira rodada).
        sugerida = limpar_testes_indevidos(
            categoria, normalizar_linha(str(divergencia.get("linha_sugerida", "")))
        )
        visto = " ".join(str(divergencia.get("o_que_vi", "")).split())
        # "O inventário não menciona X" não é divergência: o inventário é
        # uma lista mais pobre que o laudo, e silêncio dele não prova
        # ausência. Mesmo com a regra no prompt, o modelo insiste — na
        # R. Correia de Freitas quis tirar a "chave fixa" da porta do
        # banheiro (que o vistoriador tinha confirmado) com esse argumento.
        if _ARGUMENTO_DE_AUSENCIA.search(visto):
            descartadas += 1
            continue
        linhas_laudo = [l for l in dados.get(categoria, "").split("\n") if l.strip()]

        if divergencia.get("tipo") == "falta":
            if not sugerida or sugerida in linhas_laudo:
                descartadas += 1
                continue
            pendencias.append({
                "comodo": nome_comodo, "categoria": categoria, "tipo": "falta",
                "texto": sugerida, "certeza": certeza,
                "motivo": f"CONFERÊNCIA — a foto mostra e o laudo não tem: {visto}",
            })
            continue

        atual = normalizar_linha(str(divergencia.get("linha_atual", "")))
        if atual not in linhas_laudo:
            descartadas += 1
            continue
        # A conferência não encurta o laudo. O inventário é uma lista mais
        # pobre que o texto, e o modelo tentou usar o silêncio dele como
        # prova de ausência: na R. Correia de Freitas sugeriu apagar a
        # trinca e o estufamento que o vistoriador tinha confirmado, e
        # trocar linhas detalhadas por versões curtas. Sugestão que remove
        # ou empobrece a linha é descartada aqui, não vai nem a pendência.
        if (not sugerida
                or sugerida in (TEXTO_NAO_SE_APLICA, TEXTO_SEM_OBSERVACOES)
                or len(sugerida) < 0.75 * len(atual)):
            descartadas += 1
            continue
        pendencias.append({
            "comodo": nome_comodo, "categoria": categoria,
            "texto": atual, "certeza": certeza,
            "motivo": f"CONFERÊNCIA — o laudo não bate com a foto: {visto}",
            "correcao": sugerida if sugerida != atual else "",
        })

    print(f"  Conferência: {len(inventario)} itens vistos, {len(pendencias)} divergência(s)"
          + (f", {descartadas} descartada(s)" if descartadas else ""), flush=True)
    return pendencias


def _corrigir_itens_incertos(
    cliente: genai.Client,
    blocos_imagem: list,
    nome_comodo: str,
    registros_por_categoria: dict,
    notas_extras: str = "",
) -> dict:
    """Segunda olhada nas fotos, só nos itens com certeza até
    config.LIMIAR_CORRECAO_AUTOMATICA. Devolve os registros com esses itens
    substituídos pelo texto/certeza da nova análise.

    É UMA chamada por cômodo, e só acontece quando algum item sai lá
    embaixo — na maioria dos cômodos não roda nenhuma vez. Na primeira
    passada o modelo divide a atenção entre 8 categorias e todas as fotos;
    aqui ele olha as mesmas fotos sabendo qual era a dúvida, que é quando
    ele costuma resolver. Se a chamada falhar, devolve tudo como estava —
    o item segue para pendência, como antes."""
    alvos = [
        (categoria, indice)
        for categoria, registros in registros_por_categoria.items()
        for indice, (_, certeza, _) in enumerate(registros)
        if certeza <= LIMIAR_CORRECAO_AUTOMATICA
    ]
    if not alvos:
        return registros_por_categoria

    itens = [
        {
            "rotulo": ROTULOS_CATEGORIA[categoria],
            "texto": registros_por_categoria[categoria][indice][0],
            "motivo": registros_por_categoria[categoria][indice][2],
        }
        for categoria, indice in alvos
    ]
    schema = types.Schema(
        type="OBJECT",
        properties={
            "itens": types.Schema(
                type="ARRAY", items=_schema_item_com_certeza(), min_items=1
            )
        },
        required=["itens"],
    )

    print(f"  Segunda olhada nas fotos: {len(alvos)} item(ns) com certeza baixa...", flush=True)
    try:
        bruto = _gerar_com_retry(
            cliente,
            list(blocos_imagem) + [montar_prompt_correcao(nome_comodo, itens, notas_extras)],
            response_schema=schema,
            max_output_tokens=4096,
            descricao_erro=f"a segunda olhada nos itens duvidosos de '{nome_comodo}'",
        )
        novos = _extrair_json(bruto).get("itens", [])
    except Exception as erro:
        print(f"  Não consegui reanalisar os itens duvidosos ({erro.__class__.__name__}) — vão para validação.", flush=True)
        return registros_por_categoria

    if len(novos) != len(alvos):
        print(f"  A segunda olhada devolveu {len(novos)} item(ns) para {len(alvos)} pedido(s) — mantendo os originais.", flush=True)
        return registros_por_categoria

    corrigidos = {categoria: list(registros) for categoria, registros in registros_por_categoria.items()}
    for (categoria, indice), novo in zip(alvos, novos):
        linha = normalizar_linha(str(novo.get("texto", "")))
        if not linha:
            continue
        certeza = novo.get("certeza", 0)
        certeza = certeza if isinstance(certeza, int) else 0
        motivo = str(novo.get("motivo", "")).strip()
        if certeza < LIMIAR_CERTEZA:
            # Continua duvidoso: o vistoriador precisa saber que este item
            # já teve uma segunda chance e ainda assim não fechou.
            motivo = f"{motivo + '; ' if motivo else ''}{MOTIVO_REANALISADO}"
        corrigidos[categoria][indice] = (linha, certeza, motivo)
    return corrigidos


def _montar_categoria(categoria: str, registros: list) -> tuple:
    """Junta as linhas de uma categoria no texto do laudo e separa as
    pendências. Devolve (texto, pendencias). Vira pendência:

    - linha com certeza abaixo de LIMIAR_CERTEZA;
    - violação da regra ITENS REPETIDOS que sobreviveu à correção
      automática — o mesmo item em várias linhas, ou "Mais um/uma..." (que
      leva junto a linha anterior, o item que ela "continua"). Vira UMA
      pendência de certeza 0 com todas as linhas envolvidas, para o
      vistoriador trocar por uma linha só.

    O "texto" de uma pendência pode ter mais de uma linha."""
    vazio = texto_vazio_da_categoria(categoria)
    if not registros:
        # O schema pede pelo menos 1 item; se mesmo assim vier vazio, não dá
        # para afirmar nada sobre a categoria — vai para validação.
        return vazio, [{
            "categoria": categoria,
            "texto": vazio,
            "certeza": 0,
            "motivo": "o modelo não devolveu nenhum item para esta categoria",
        }]

    # "Não se aplica."/"Sem observações." não convivem com itens reais; e,
    # sem itens reais, a categoria fica com o texto vazio certo para ela
    # ("Sem observações." no OBS, "Não se aplica." no resto).
    reais = [r for r in registros if r[0] not in (TEXTO_NAO_SE_APLICA, TEXTO_SEM_OBSERVACOES)]
    if not reais:
        menos_certo = min(registros, key=lambda registro: registro[1])
        if menos_certo[1] >= LIMIAR_CERTEZA:
            return vazio, []
        return vazio, [{
            "categoria": categoria,
            "texto": vazio,
            "certeza": menos_certo[1],
            "motivo": menos_certo[2] or SEM_MOTIVO,
        }]

    # "Testado e em funcionamento" onde não cabe (parede, piso, teto, porta,
    # janela, mobília sem função elétrica/hidráulica) sai aqui — ver a regra
    # TESTES em style_guide.REGRAS_GERAIS.
    reais = [(limpar_testes_indevidos(categoria, linha), certeza, motivo)
             for linha, certeza, motivo in reais]
    linhas = [linha for linha, _, _ in reais]

    # Cada "Mais um/uma" vira pendência junto com a linha anterior, que é o
    # item que ela continua. Conjuntos que se tocam viram um só (ex.: "*Um
    # armário" + "*Mais um armário" + "*Mais um armário").
    #
    # O mesmo substantivo em linhas separadas NÃO vira pendência: isso é
    # palpite de heurística e errou feio na Cozinha da R. Correia de
    # Freitas, onde juntou "*Uma bancada em granito com cuba..." com "*Uma
    # bancada de apoio...", que são móveis diferentes. Ele continua
    # disparando a correção automática (_tem_itens_repetidos), que é o
    # modelo julgando com o texto na mão; o que o modelo decidir manter
    # separado, fica separado (regra do vistoriador, 22/09/2026).
    problemas = [{i - 1, i} if i > 0 else {i} for i, linha in enumerate(linhas) if linha_com_mais_um(linha)]
    unidos = []
    for conjunto in problemas:
        for outro in [u for u in unidos if u & conjunto]:
            conjunto |= outro
            unidos.remove(outro)
        unidos.append(conjunto)

    pendencias, cobertas = [], set()
    for conjunto in unidos:
        indices = sorted(conjunto)
        cobertas |= conjunto
        # Se alguma dessas linhas também era duvidosa, o motivo vai junto.
        extras = list(dict.fromkeys(
            reais[i][2] for i in indices if reais[i][1] < LIMIAR_CERTEZA and reais[i][2]
        ))
        motivo = MOTIVO_REPETIDOS + (f"; além disso: {'; '.join(extras)}" if extras else "")
        pendencias.append((indices[0], {
            "categoria": categoria,
            "texto": "\n".join(linhas[i] for i in indices),
            "certeza": 0,
            "motivo": motivo,
        }))

    for indice, (linha, certeza, motivo) in enumerate(reais):
        if indice not in cobertas and certeza < LIMIAR_CERTEZA:
            pendencias.append((indice, {
                "categoria": categoria,
                "texto": linha,
                "certeza": certeza,
                "motivo": motivo or SEM_MOTIVO,
            }))

    pendencias.sort(key=lambda par: par[0])
    return "\n".join(linhas), [pendencia for _, pendencia in pendencias]


def pendencias_itens_repetidos(categoria: str, texto: str) -> list:
    """Pendências de violação da regra ITENS REPETIDOS num texto já pronto
    (sem certeza) — usado pelo revisar.py depois da revisão."""
    registros = [(linha, 100, "") for linha in texto.split("\n") if linha.strip()]
    return _montar_categoria(categoria, registros)[1] if registros else []


def _gerar_com_retry(
    cliente: genai.Client,
    conteudo: list,
    response_schema: types.Schema,
    max_output_tokens: int,
    descricao_erro: str,
) -> str:
    """Chama generate_content com retry automático em erro 503 (servidor
    sobrecarregado — transitório, a própria API pede pra tentar de novo) e
    verifica se a resposta não foi cortada por max_output_tokens. Devolve o
    texto bruto (JSON) da resposta. Compartilhado por analisar_comodo e
    revisar_laudo pra não duplicar a lógica de retry."""
    resposta = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resposta = cliente.models.generate_content(
                model=MODEL_NAME,
                contents=conteudo,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
            break
        except (errors.ServerError, httpx.TransportError) as erro:
            # TransportError cobre o tempo limite estourado e quedas de rede.
            if tentativa == MAX_TENTATIVAS:
                raise
            espera = ESPERA_BASE_SEGUNDOS * tentativa
            print(
                f"  Falha transitória no Gemini para {descricao_erro} "
                f"({erro.__class__.__name__}), tentativa {tentativa}/{MAX_TENTATIVAS}. "
                f"Aguardando {espera}s...",
                flush=True,
            )
            time.sleep(espera)

    candidato = resposta.candidates[0] if resposta.candidates else None
    if candidato is not None and candidato.finish_reason == types.FinishReason.MAX_TOKENS:
        raise RuntimeError(
            f"A resposta do modelo para {descricao_erro} foi cortada por "
            "atingir o limite de max_output_tokens antes de terminar o JSON. "
            "Aumente max_output_tokens em gemini_client.py e tente novamente."
        )

    return resposta.text


def analisar_comodo(
    cliente: genai.Client, blocos_imagem: list, nome_comodo: str, notas_extras: str = ""
) -> tuple:
    """Chama a API UMA vez para o cômodo inteiro e retorna (dados, incertos):

    - dados: {categoria: texto} para as 8 categorias de config.CATEGORIAS,
      no formato que report_writer grava;
    - incertos: itens que o modelo avaliou com certeza abaixo de
      config.LIMIAR_CERTEZA — [{categoria, texto, certeza, motivo}].

    Os itens incertos continuam no laudo; a lista serve para o vistoriador
    conferir (ver validacao.py e validar.py).

    `notas_extras` repassa informação específica deste imóvel (ex.: cor
    exata de tinta confirmada) para o prompt — ver style_guide.montar_prompt_comodo."""
    prompt = montar_prompt_comodo(nome_comodo, CATEGORIAS, notas_extras)
    conteudo = list(blocos_imagem) + [prompt]

    texto_bruto = _gerar_com_retry(
        cliente,
        conteudo,
        response_schema=_schema_itens_com_certeza(CATEGORIAS),
        # Cômodos com muitas fotos/mobília geram descrições longas — um
        # teto baixo aqui corta o JSON no meio e quebra o parsing.
        max_output_tokens=8192,
        descricao_erro=f"o cômodo '{nome_comodo}'",
    )

    try:
        dados = _extrair_json(texto_bruto)
    except (json.JSONDecodeError, ValueError) as erro:
        raise RuntimeError(
            f"Não foi possível interpretar a resposta do modelo como JSON "
            f"para o cômodo '{nome_comodo}'. Erro: {erro}\n\n"
            f"Início da resposta recebida:\n{_trecho_para_erro(texto_bruto)}"
        ) from erro

    registros_por_categoria = {
        categoria: _consolidar_repetidos(cliente, categoria, _registros(dados.get(categoria)))
        for categoria in CATEGORIAS
    }
    registros_por_categoria = _corrigir_itens_incertos(
        cliente, blocos_imagem, nome_comodo, registros_por_categoria, notas_extras
    )

    resultado, incertos = {}, []
    for categoria in CATEGORIAS:
        texto, incertos_categoria = _montar_categoria(categoria, registros_por_categoria[categoria])
        resultado[categoria] = texto
        incertos.extend(incertos_categoria)
    return resultado, incertos


def revisar_laudo(cliente: genai.Client, resultados: dict, notas_extras: str = "") -> dict:
    """Passa um laudo JÁ GERADO (todos os cômodos de um imóvel) por uma
    revisão de TEXTO PURO — sem fotos — pra padronizar terminologia e
    formatação conforme o style_guide atual. Usada por revisar.py quando o
    padrão de escrita muda depois que o laudo já foi gerado com as fotos,
    evitando reenviar as imagens (custo e tempo).

    `resultados` é {nome_comodo: {categoria: texto}}; devolve no mesmo
    formato, com o texto revisado."""
    laudo_json = json.dumps(resultados, ensure_ascii=False, indent=2)
    prompt = montar_prompt_revisao(laudo_json, CATEGORIAS, notas_extras)

    schema_laudo = types.Schema(
        type="OBJECT",
        properties={
            nome_comodo: _schema_categorias(CATEGORIAS) for nome_comodo in resultados
        },
        required=list(resultados.keys()),
    )

    texto_bruto = _gerar_com_retry(
        cliente,
        [prompt],
        response_schema=schema_laudo,
        # O laudo inteiro (todos os cômodos) de uma vez é bem mais texto
        # que um cômodo só — precisa de bastante espaço de saída.
        max_output_tokens=32768,
        descricao_erro="a revisão do laudo completo",
    )

    try:
        dados = _extrair_json(texto_bruto)
    except (json.JSONDecodeError, ValueError) as erro:
        raise RuntimeError(
            "Não foi possível interpretar a resposta da revisão como JSON. "
            f"Erro: {erro}\n\nInício da resposta recebida:\n"
            f"{_trecho_para_erro(texto_bruto)}"
        ) from erro

    revisado = {}
    for nome_comodo, dados_originais in resultados.items():
        dados_revisados = dados.get(nome_comodo, {})
        revisado[nome_comodo] = {}
        for categoria in CATEGORIAS:
            texto = str(dados_revisados.get(categoria, dados_originais.get(categoria, ""))).strip()
            # Mesma correção automática da análise com fotos, caso a revisão
            # também tenha escrito "Mais um/uma".
            registros = [(linha, 100, "") for linha in texto.split("\n") if linha.strip()]
            if _tem_itens_repetidos([linha for linha, _, _ in registros]):
                registros = _consolidar_repetidos(cliente, categoria, registros)
                texto = "\n".join(linha for linha, _, _ in registros)
            revisado[nome_comodo][categoria] = texto
    return revisado


# ==========================================================================
# ESCOPO E EVIDÊNCIAS (desde 25/09/2026)
#
# Duas funções novas, que juntas substituem o caminho de UMA chamada
# "fotos -> laudo" por "fotos -> evidências" + "evidências -> laudo".
#
# Sobre custo, que foi condição explícita do vistoriador: o Gemini cobra por
# IMAGEM (1.101 tokens por foto, medido em 22/09/2026, igual em qualquer
# resolução). As fotos continuam sendo enviadas UMA vez cada — mandá-las em
# 4 lotes de 10 custa o mesmo que num lote de 40, porque o que se repete é só
# o texto do prompt. O passo 2 é texto puro, sem imagem. O acréscimo real
# sobre o motor antigo é da ordem de um prompt repetido por lote, não de uma
# segunda leitura das fotos.
# ==========================================================================


def _schema_escopo_evidencias(quantidade_fotos: int) -> types.Schema:
    """Schema do passo 1: uma classificação por foto + as evidências cruas.

    "regiao" fica FORA de `required` de propósito: a instrução manda o modelo
    omitir o campo quando não souber onde está o item, e um schema que exige
    região obriga o modelo a inventar uma (ver regra 9 do pedido)."""
    foto = types.Schema(
        type="OBJECT",
        properties={
            "indice": types.Schema(type="INTEGER", minimum=1, maximum=quantidade_fotos),
            "escopo": types.Schema(type="STRING", enum=["valid", "partial", "out_of_scope"]),
            "relevancia": types.Schema(type="INTEGER", minimum=0, maximum=100),
            "ambiente_adjacente": types.Schema(type="BOOLEAN"),
            "reflexo": types.Schema(type="BOOLEAN"),
            "motivo": types.Schema(type="STRING"),
        },
        required=["indice", "escopo", "relevancia", "ambiente_adjacente", "reflexo", "motivo"],
        property_ordering=["indice", "escopo", "relevancia", "ambiente_adjacente",
                           "reflexo", "motivo"],
    )
    regiao = types.Schema(
        type="OBJECT",
        properties={
            "x": types.Schema(type="NUMBER"),
            "y": types.Schema(type="NUMBER"),
            "largura": types.Schema(type="NUMBER"),
            "altura": types.Schema(type="NUMBER"),
        },
    )
    evidencia = types.Schema(
        type="OBJECT",
        properties={
            "foto_indice": types.Schema(type="INTEGER", minimum=1, maximum=quantidade_fotos),
            "categoria": types.Schema(type="STRING", enum=list(CATEGORIAS)),
            "observacao": types.Schema(type="STRING"),
            # A ordem importa: o modelo descreve, depois julga se pertence ao
            # cômodo, e só então dá as notas. Mesma razão da ordem
            # texto -> motivo -> certeza no schema da análise antiga.
            "ambiente_adjacente": types.Schema(type="BOOLEAN"),
            "reflexo": types.Schema(type="BOOLEAN"),
            "confianca_percepcao": types.Schema(type="INTEGER", minimum=0, maximum=100),
            "confianca_escopo": types.Schema(type="INTEGER", minimum=0, maximum=100),
            "regiao": regiao,
        },
        required=["foto_indice", "categoria", "observacao", "ambiente_adjacente",
                  "reflexo", "confianca_percepcao", "confianca_escopo"],
        property_ordering=["foto_indice", "categoria", "observacao",
                           "ambiente_adjacente", "reflexo", "confianca_percepcao",
                           "confianca_escopo", "regiao"],
    )
    return types.Schema(
        type="OBJECT",
        properties={
            "fotos": types.Schema(type="ARRAY", items=foto, min_items=1),
            "evidencias": types.Schema(type="ARRAY", items=evidencia),
        },
        required=["fotos", "evidencias"],
    )


def analisar_escopo_e_evidencias(
    cliente: genai.Client,
    blocos_imagem: list,
    ids_fotos: list,
    nome_comodo: str,
    notas_extras: str = "",
) -> tuple:
    """Passo 1: classifica cada foto e extrai evidências cruas.

    `blocos_imagem` e `ids_fotos` são paralelos: a foto na posição i do lote é
    `ids_fotos[i]`. O modelo devolve índices de 1 a N; a tradução de índice
    para id estável acontece aqui, e índice fora da faixa é ignorado em vez de
    virar evidência órfã.

    Devolve ({foto_id: AnaliseFoto}, [Evidencia]) — ainda SEM validação de
    escopo, que é determinística e mora em core.evidencias.validar_escopo."""
    quantidade = len(blocos_imagem)
    bruto = _gerar_com_retry(
        cliente,
        list(blocos_imagem) + [montar_prompt_escopo(nome_comodo, quantidade, notas_extras)],
        response_schema=_schema_escopo_evidencias(quantidade),
        max_output_tokens=16384,
        descricao_erro=f"a análise de escopo de '{nome_comodo}'",
    )
    dados = _extrair_json(bruto)

    analises = {}
    for item in dados.get("fotos", []):
        if not isinstance(item, dict):
            continue
        indice = item.get("indice")
        if not isinstance(indice, int) or not (1 <= indice <= quantidade):
            continue
        foto_id = ids_fotos[indice - 1]
        analises[foto_id] = analise_de_dict(item, foto_id, nome_comodo)

    # Foto que o modelo não classificou não vira foto válida por omissão: sem
    # análise, a evidência dela cai em FOTO_FORA_DE_ESCOPO na validação. É a
    # regra 16 (falso positivo é pior que falso negativo) aplicada à falha.
    for posicao, foto_id in enumerate(ids_fotos, start=1):
        if foto_id not in analises:
            analises[foto_id] = AnaliseFoto(
                foto_id=foto_id, comodo_alvo=nome_comodo,
                escopo=EscopoFoto.FORA_DE_ESCOPO,
                motivo=f"o modelo não classificou a foto {posicao} deste lote",
            )

    evidencias = []
    for ordem, item in enumerate(dados.get("evidencias", []), start=1):
        if not isinstance(item, dict):
            continue
        indice = item.get("foto_indice")
        if not isinstance(indice, int) or not (1 <= indice <= quantidade):
            continue
        foto_id = ids_fotos[indice - 1]
        evidencias.append(
            evidencia_de_dict(item, f"{foto_id}#{ordem}", foto_id)
        )
    return analises, evidencias


def consolidar_evidencias(
    cliente: genai.Client,
    nome_comodo: str,
    resultado_escopo,
    blocos_imagem: list,
    notas_extras: str = "",
) -> tuple:
    """Passo 2: escreve o laudo do cômodo a partir das evidências APROVADAS.

    Chamada de texto puro — as fotos não vão junto, de propósito: com as
    imagens na mão o modelo volta a descrever o que vê, inclusive o que o
    código acabou de descartar por ser de ambiente vizinho.

    Depois da redação, o texto passa EXATAMENTE pelas mesmas travas do motor
    antigo, na mesma ordem: consolidação de itens repetidos, segunda olhada
    nos itens de certeza baixa (esta sim com as fotos, que é o ponto dela) e
    _montar_categoria, que limpa testes indevidos e separa as pendências.

    Devolve (dados, incertos), no mesmo formato de analisar_comodo."""
    prompt = montar_prompt_consolidacao_evidencias(
        nome_comodo, CATEGORIAS, resultado_escopo.por_categoria(),
        resultado_escopo.cobertura_incompleta, notas_extras,
    )
    bruto = _gerar_com_retry(
        cliente,
        [prompt],
        response_schema=_schema_itens_com_certeza(CATEGORIAS),
        max_output_tokens=8192,
        descricao_erro=f"a redação do cômodo '{nome_comodo}'",
    )

    try:
        dados = _extrair_json(bruto)
    except (json.JSONDecodeError, ValueError) as erro:
        raise RuntimeError(
            f"Não foi possível interpretar como JSON a redação do cômodo "
            f"'{nome_comodo}'. Erro: {erro}\n\nInício da resposta recebida:\n"
            f"{_trecho_para_erro(bruto)}"
        ) from erro

    registros_por_categoria = {
        categoria: _consolidar_repetidos(cliente, categoria, _registros(dados.get(categoria)))
        for categoria in CATEGORIAS
    }
    if blocos_imagem:
        registros_por_categoria = _corrigir_itens_incertos(
            cliente, blocos_imagem, nome_comodo, registros_por_categoria, notas_extras
        )

    resultado, incertos = {}, []
    for categoria in CATEGORIAS:
        texto, incertos_categoria = _montar_categoria(
            categoria, registros_por_categoria[categoria]
        )
        resultado[categoria] = texto
        incertos.extend(incertos_categoria)
    return resultado, incertos


# ==========================================================================
# MOTOR V2 (desde 25/09/2026)
#
# Custo, que foi condição explícita: o Gemini cobra por IMAGEM (1.101 tokens
# por foto, medido, igual em qualquer resolução). As fotos continuam sendo
# enviadas UMA vez cada na extração. O que a V2 acrescenta sobre a V1 é a
# segunda olhada DIRIGIDA, e só quando a checklist de cobertura aponta
# lacuna — ela reenvia as fotos, então é a parte cara e por isso é limitada
# por config.MAX_SEGUNDAS_OLHADAS_DIRIGIDAS.
# ==========================================================================

_VALORES_DE_ESCOPO = ["room_interior", "room_boundary", "adjacent_room",
                      "outside", "reflection", "ambiguous"]


def _schema_evidencia_v2(quantidade_fotos: int) -> types.Schema:
    """Uma evidência como a V2 a pede.

    "regiao" e "atributos" ficam FORA de `required` de propósito: o prompt
    manda omitir o que não se sabe, e um schema que exige o campo obriga o
    modelo a inventar (ver regra da região)."""
    regiao = types.Schema(
        type="OBJECT",
        properties={
            "x": types.Schema(type="NUMBER"),
            "y": types.Schema(type="NUMBER"),
            "largura": types.Schema(type="NUMBER"),
            "altura": types.Schema(type="NUMBER"),
        },
    )
    atributos = types.Schema(
        type="OBJECT",
        properties={
            chave: types.Schema(type="STRING")
            for chave in ("material", "cor", "acabamento", "rejunte_material",
                          "rejunte_cor", "tipo", "estado", "defeito")
        },
    )
    return types.Schema(
        type="OBJECT",
        properties={
            "foto_indice": types.Schema(type="INTEGER", minimum=1,
                                        maximum=max(1, quantidade_fotos)),
            "categoria": types.Schema(type="STRING", enum=list(CATEGORIAS)),
            "observacao": types.Schema(type="STRING"),
            # A ordem importa: descreve, decide onde aquilo está, e só então
            # dá as notas — em vez de se comprometer com um número antes.
            "escopo": types.Schema(type="STRING", enum=_VALORES_DE_ESCOPO),
            "instancia": types.Schema(type="INTEGER", minimum=1),
            "confianca_percepcao": types.Schema(type="INTEGER", minimum=0, maximum=100),
            "confianca_escopo": types.Schema(type="INTEGER", minimum=0, maximum=100),
            "atributos": atributos,
            "regiao": regiao,
        },
        required=["foto_indice", "categoria", "observacao", "escopo",
                  "confianca_percepcao", "confianca_escopo"],
        property_ordering=["foto_indice", "categoria", "observacao", "escopo",
                           "instancia", "confianca_percepcao",
                           "confianca_escopo", "atributos", "regiao"],
    )


def _schema_escopo_v2(quantidade_fotos: int) -> types.Schema:
    foto = types.Schema(
        type="OBJECT",
        properties={
            "indice": types.Schema(type="INTEGER", minimum=1, maximum=quantidade_fotos),
            "escopo": types.Schema(type="STRING",
                                   enum=["valid", "partial", "out_of_scope"]),
            "relevancia": types.Schema(type="INTEGER", minimum=0, maximum=100),
            "ambiente_adjacente": types.Schema(type="BOOLEAN"),
            "reflexo": types.Schema(type="BOOLEAN"),
            "motivo": types.Schema(type="STRING"),
        },
        required=["indice", "escopo", "relevancia", "ambiente_adjacente",
                  "reflexo", "motivo"],
        property_ordering=["indice", "escopo", "relevancia",
                           "ambiente_adjacente", "reflexo", "motivo"],
    )
    return types.Schema(
        type="OBJECT",
        properties={
            "fotos": types.Schema(type="ARRAY", items=foto, min_items=1),
            "evidencias": types.Schema(
                type="ARRAY", items=_schema_evidencia_v2(quantidade_fotos)),
        },
        required=["fotos", "evidencias"],
    )


def _evidencias_do_json(bruto: dict, ids_fotos: list, prefixo: str) -> list:
    """Traduz índice de foto para id estável e descarta evidência órfã."""
    quantidade = len(ids_fotos)
    evidencias = []
    for ordem, item in enumerate(bruto.get("evidencias", []), start=1):
        if not isinstance(item, dict):
            continue
        indice = item.get("foto_indice")
        if not isinstance(indice, int) or not (1 <= indice <= quantidade):
            continue
        foto_id = ids_fotos[indice - 1]
        evidencias.append(evidencia_de_dict(item, f"{prefixo}{foto_id}#{ordem}", foto_id))
    return evidencias


def analisar_escopo_e_evidencias_v2(
    cliente: genai.Client,
    blocos_imagem: list,
    ids_fotos: list,
    nome_comodo: str,
    notas_extras: str = "",
) -> tuple:
    """Passo 1 da V2: classifica as fotos e extrai evidências EXAUSTIVAS.

    Devolve ({foto_id: AnaliseFoto}, [Evidencia]) — ainda sem validação de
    escopo, que é determinística e mora em core.evidencias.validar_escopo."""
    quantidade = len(blocos_imagem)
    bruto = _gerar_com_retry(
        cliente,
        list(blocos_imagem) + [montar_prompt_escopo_v2(
            nome_comodo, quantidade, notas_extras)],
        response_schema=_schema_escopo_v2(quantidade),
        # Inventário exaustivo gera MUITO mais itens que o resumo da V1 —
        # um teto baixo aqui corta o JSON no meio.
        max_output_tokens=32768,
        descricao_erro=f"a análise de escopo de '{nome_comodo}'",
    )
    dados = _extrair_json(bruto)

    analises = {}
    for item in dados.get("fotos", []):
        if not isinstance(item, dict):
            continue
        indice = item.get("indice")
        if not isinstance(indice, int) or not (1 <= indice <= quantidade):
            continue
        foto_id = ids_fotos[indice - 1]
        analises[foto_id] = analise_de_dict(item, foto_id, nome_comodo)

    # Foto que o modelo não classificou não vira foto válida por omissão.
    for posicao, foto_id in enumerate(ids_fotos, start=1):
        if foto_id not in analises:
            analises[foto_id] = AnaliseFoto(
                foto_id=foto_id, comodo_alvo=nome_comodo,
                escopo=EscopoFoto.FORA_DE_ESCOPO,
                motivo=f"o modelo não classificou a foto {posicao} deste lote",
            )

    return analises, _evidencias_do_json(dados, ids_fotos, "")


def segunda_olhada_dirigida(
    cliente: genai.Client,
    blocos_imagem: list,
    ids_fotos: list,
    nome_comodo: str,
    instrucao: str,
    procurando: list,
    notas_extras: str = "",
    marca: str = "d1",
) -> list:
    """Olha as MESMAS fotos procurando só o que a cobertura apontou.

    Devolve evidências novas — nunca texto de laudo. Lista vazia é resposta
    legítima: melhor a lacuna continuar aberta do que um item inventado."""
    quantidade = len(blocos_imagem)
    schema = types.Schema(
        type="OBJECT",
        properties={
            "evidencias": types.Schema(
                type="ARRAY", items=_schema_evidencia_v2(quantidade)),
        },
        required=["evidencias"],
    )
    try:
        bruto = _gerar_com_retry(
            cliente,
            list(blocos_imagem) + [montar_prompt_segunda_olhada_dirigida(
                nome_comodo, quantidade, instrucao, procurando, notas_extras)],
            response_schema=schema,
            max_output_tokens=8192,
            descricao_erro=f"a segunda olhada dirigida em '{nome_comodo}'",
        )
        dados = _extrair_json(bruto)
    except Exception as erro:
        # Uma busca dirigida que falha não pode derrubar o cômodo: a lacuna
        # continua aberta e vira pendência, que é o comportamento seguro.
        print(f"  Segunda olhada dirigida falhou ({erro.__class__.__name__}) — "
              "a lacuna segue para pendência.", flush=True)
        return []
    return _evidencias_do_json(dados, ids_fotos, f"{marca}:")


def consolidar_evidencias_v2(
    cliente: genai.Client,
    nome_comodo: str,
    resultado_escopo,
    blocos_imagem: list,
    estado_rodape: str = "",
    notas_extras: str = "",
) -> tuple:
    """Passo final: escreve o laudo a partir das evidências APROVADAS.

    Chamada de texto puro — as fotos não vão junto, de propósito. Depois da
    redação o texto passa pelas mesmas travas de sempre: consolidação de
    itens repetidos, segunda olhada nos itens de certeza baixa e
    _montar_categoria, que limpa testes indevidos e separa as pendências."""
    # As evidências do MESMO objeto, vistas em fotos diferentes, viram UM
    # objeto antes de chegar ao redator. Sem isto, o inventário exaustivo
    # inflava a contagem: o mesmo chuveiro em duas fotos virou "dois
    # chuveiros" no benchmark real.
    grupos = agrupar_objetos(resultado_escopo.aceitas)
    por_categoria = {categoria: [] for categoria in CATEGORIAS}
    for grupo in grupos:
        por_categoria[grupo["categoria"]].append(grupo)

    tipos = tipos_eletricos_presentes(
        [g["observacao"] for g in por_categoria.get("eletrico", [])]
    )
    prompt = montar_prompt_consolidacao_v2(
        nome_comodo, CATEGORIAS, por_categoria,
        resultado_escopo.cobertura_incompleta, tipos, estado_rodape, notas_extras,
    )
    bruto = _gerar_com_retry(
        cliente,
        [prompt],
        response_schema=_schema_itens_com_certeza(CATEGORIAS),
        max_output_tokens=16384,
        descricao_erro=f"a redação do cômodo '{nome_comodo}'",
    )

    try:
        dados = _extrair_json(bruto)
    except (json.JSONDecodeError, ValueError) as erro:
        raise RuntimeError(
            f"Não foi possível interpretar como JSON a redação do cômodo "
            f"'{nome_comodo}'. Erro: {erro}\n\nInício da resposta recebida:\n"
            f"{_trecho_para_erro(bruto)}"
        ) from erro

    registros_por_categoria = {
        categoria: _consolidar_repetidos(cliente, categoria, _registros(dados.get(categoria)))
        for categoria in CATEGORIAS
    }
    if blocos_imagem:
        registros_por_categoria = _corrigir_itens_incertos(
            cliente, blocos_imagem, nome_comodo, registros_por_categoria, notas_extras
        )

    resultado, incertos = {}, []
    for categoria in CATEGORIAS:
        texto, incertos_categoria = _montar_categoria(
            categoria, registros_por_categoria[categoria]
        )
        resultado[categoria] = texto
        incertos.extend(incertos_categoria)
    return resultado, incertos
