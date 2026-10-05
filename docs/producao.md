# Produção

A aplicação guarda fotos do interior de imóveis de clientes. Isso é dado
pessoal, e o que vale aqui é a LGPD — não só boa prática de servidor.

---

## Antes de expor para fora da máquina

Três coisas, nesta ordem. Nenhuma é opcional.

### 1. HTTPS

Sem TLS, a senha e o cookie de sessão trafegam em texto claro. Ponha um proxy
na frente — Caddy é o caminho mais curto porque cuida do certificado sozinho:

```
laudo.seudominio.com.br {
    reverse_proxy 127.0.0.1:8000
    request_body {
        max_size 520MB
    }
}
```

O `max_size` precisa ser maior que o `LAUDO_MAX_ZIP_MB`, senão o proxy corta o
upload antes de a aplicação ver.

Com nginx, o equivalente é `client_max_body_size 520M;` — o padrão dele é 1 MB
e derruba qualquer envio de fotos.

### 2. Ligar o cookie seguro

No `.env`:

```
LAUDO_COOKIE_SEGURO=1
```

Isso marca o cookie como `Secure`: ele deixa de ser enviado em conexão não
cifrada. **Só ligue depois que o HTTPS estiver funcionando**, senão você não
consegue mais entrar.

### 3. Fechar a porta direta

No `docker-compose.yml`, mantenha:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

Assim só o proxy alcança a aplicação. Se publicar `8000:8000`, qualquer um na
rede fala com ela sem passar pelo TLS.

---

## Conferência antes de abrir

- [ ] `LAUDO_COOKIE_SEGURO=1` e HTTPS respondendo
- [ ] `LAUDO_DOCS` desligado (o `/docs` entrega a superfície inteira da API)
- [ ] `LAUDO_ADMIN_SENHA` com senha longa e única — ela vira o único acesso
- [ ] O `.env` fora do repositório (já está no `.gitignore`)
- [ ] Backup do volume `dados` agendado ([guia](backup.md))
- [ ] Chave do Gemini num projeto com faturamento ativo
- [ ] Se usar GLM ou Claude: política de dados do provedor conferida (fotos de cliente) e `CLAUDE_MODEL` definido
- [ ] `docker compose logs` sem erro na subida

---

## O que já vem resolvido

Não precisa configurar nada disso — está no código:

| Risco | Como está tratado |
|---|---|
| Senha no banco | `scrypt` com sal por usuário. O banco nunca vê a senha. |
| Sessão roubada | O banco guarda o *hash* do token, não o token. O logout apaga a linha: o token para de valer no servidor, não só no navegador. |
| XSS pegando a sessão | Cookie `HttpOnly` — o JavaScript da página não lê. |
| CSRF | Cookie `SameSite=Lax`. |
| Upload malicioso | O arquivo é decodificado antes de ser aceito. Extensão não participa da decisão. |
| Path traversal | O caminho no disco é derivado de UUID, nunca de texto do usuário; e há uma segunda checagem na hora de servir. |
| Zip Slip | Entradas com `..`, caminho absoluto ou letra de unidade são recusadas. |
| Zip bomb | Limite de entradas, de tamanho por entrada e de total descompactado — checado no cabeçalho e de novo durante a extração. |
| Chaves de modelo (Gemini, GLM, Claude) | Lidas só pelo processo do servidor. Nenhuma rota as devolve (`/api/saude` diz só SE cada uma existe; há teste). Erro de provedor leva o status HTTP, nunca a chave. O navegador nunca chama modelo nenhum. |
| Foto em log | Nenhum log registra bytes de imagem nem prompt completo. A telemetria de custo guarda só provedor, modelo, tokens, tempo e identificadores. |

---

## Operação

### Reinício no meio de um processamento

Pode reiniciar. O estado é gravado **por cômodo**: os que terminaram continuam
prontos e não são refeitos. O job interrompido é marcado como falho na subida
seguinte, e o cômodo que estava no meio volta para "a processar". Clique em
Processar de novo e ele continua de onde parou.

### Custo

O Gemini cobra por **imagem**, não por pixel — 1.101 tokens por foto, igual em
1568px ou em 256px (medido em 22/09/2026). Cada foto é enviada uma vez só por
processamento. Reprocessar um cômodo custa de novo; reprocessar a vistoria
inteira custa tudo de novo. Por isso o botão "Processar" pula os cômodos já
concluídos, e refazer tudo é um botão separado.

Cada chamada a modelo fica registrada (tabela `chamada_modelo`): provedor,
modelo, tipo, tokens, tempo e custo estimado. O total por vistoria sai em
`GET /api/vistorias/{id}/custos`. Custo `null` = algum modelo usado não tem
preço registrado (`core/config.PRECOS_POR_MILHAO` ou `LAUDO_PRECOS_MODELOS`) —
o sistema não chuta preço.

### Se a cota estourar

No Gemini, erro `429` não tem nova tentativa automática, de propósito: é a
cota diária, e insistir só piora. O cômodo é marcado como falho, os outros
seguem, e você reprocessa depois. No GLM e no Claude o `429` é limite por
minuto: o sistema espera o `Retry-After` do servidor (até 60 s) e tenta de
novo, no máximo 4 vezes.

### Trocar de modelo

O Gemini é o padrão (`core/config.py`, `MODEL_NAME`). Os outros entram por
`VISION_PROVIDER` / `VALIDATOR_PROVIDER` no `.env` (ver `.env.example`). Antes
de trocar o modelo que gera os laudos, rode uma vistoria real de ponta a ponta
e compare com `benchmark.py --provedores` — um `models.list()` respondendo não
diz nada sobre a qualidade da leitura das fotos. E o envio de fotos de cliente
a um provedor novo é uma decisão de LGPD, não só técnica.

---

## Mudança de esquema do banco

A primeira subida cria as tabelas sozinha. Quando o esquema mudar **com dados
dentro**, use o Alembic:

```bash
PYTHONPATH=.:backend python -m alembic -c backend/alembic.ini revision --autogenerate -m "o que mudou"
```

```bash
PYTHONPATH=.:backend python -m alembic -c backend/alembic.ini upgrade head
```

Faça backup antes de aplicar migração em banco com vistoria dentro.

A migração `7c41e2b9a0d5` (multimodelo, 05/10/2026) só cria as tabelas
`validacao_evidencia` e `chamada_modelo`. Ela não é obrigatória para subir: a
aplicação cria tabela que falta na subida. Mas quem acompanha o esquema pelo
Alembic deve aplicá-la, para o `alembic_version` não ficar para trás. O
`downgrade -1` remove só essas duas tabelas.
