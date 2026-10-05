# Backup

## O que precisa ser salvo

Uma coisa só: **o diretório de dados** (`/dados` no contêiner, volume `dados`).

Dentro dele:

| Caminho | O que é | Dá para refazer? |
|---|---|---|
| `laudo.db` | Banco: vistorias, cômodos, laudo, evidências, pendências, regras, histórico | **Não.** As decisões que você tomou nas pendências só existem aqui. |
| `fotos/` | As fotos como foram enviadas | **Não.** São a prova da vistoria. |
| `exportacoes/` | ZIPs gerados | Sim, é só gerar de novo. |

O código não precisa de backup — está no Git. O `.env` precisa, ou pelo menos
a chave do Gemini e a senha, guardadas onde você recupere.

---

## Como fazer

### Quente (aplicação rodando)

O SQLite roda em modo WAL, então copiar o arquivo com a aplicação de pé pode
pegar um estado inconsistente. Use o `.backup` do próprio SQLite, que resolve
isso:

```bash
docker compose exec -T laudo sh -c 'sqlite3 /dados/laudo.db ".backup /dados/backup-banco.db"'
```

```bash
docker run --rm -v laudo_dados:/dados -v "$PWD:/saida" alpine tar czf /saida/laudo-$(date +%F).tar.gz -C /dados .
```

### Frio (mais simples e mais seguro)

Com a aplicação parada, é só copiar:

```bash
docker compose down
```

```bash
docker run --rm -v laudo_dados:/dados -v "$PWD:/saida" alpine tar czf /saida/laudo-$(date +%F).tar.gz -C /dados .
```

```bash
docker compose up -d
```

### Sem Docker

O diretório é o do `LAUDO_DIRETORIO_DADOS` (padrão: `dados/` ao lado do
projeto). Copie a pasta inteira com a aplicação parada.

---

## Como restaurar

```bash
docker compose down
```

```bash
docker run --rm -v laudo_dados:/dados -v "$PWD:/entrada" alpine sh -c "rm -rf /dados/* && tar xzf /entrada/laudo-2026-09-25.tar.gz -C /dados"
```

```bash
docker compose up -d
```

Entre na aplicação e confira: uma vistoria conhecida aparece, as fotos abrem, o
laudo está lá e as pendências que você já tinha decidido continuam decididas.

---

## Com que frequência

Depende do que dói perder. Uma vistoria são horas no imóvel e horas decidindo
pendências.

- **Diário**, se você faz vistoria quase todo dia.
- **Depois de cada vistoria entregue**, se o volume for menor. É o momento em
  que o valor acumulado é maior.

Guarde pelo menos uma cópia **fora da máquina** que roda a aplicação. Backup no
mesmo disco não protege de disco queimado nem de ransomware.

---

## Teste de restauração

Backup que nunca foi restaurado não é backup. Uma vez por trimestre, restaure
num diretório diferente e confira que a aplicação sobe:

```bash
mkdir -p /tmp/teste-restauracao && tar xzf laudo-2026-09-25.tar.gz -C /tmp/teste-restauracao
```

```bash
LAUDO_DIRETORIO_DADOS=/tmp/teste-restauracao PYTHONPATH=.:backend python -m uvicorn app.main:app --port 8123
```

Abra, entre, e veja se os dados estão lá. Depois apague o diretório de teste.

---

## O que NÃO é backup

- Exportar o `.txt` do laudo. Ele é o produto final, não o sistema: não traz
  fotos, evidências, pendências decididas nem histórico.
- O ZIP da vistoria. Traz fotos e laudo, mas não as regras adotadas, não o
  histórico de alterações e não as decisões registradas. Serve para entregar ao
  cliente ou arquivar, não para reconstruir o sistema.
