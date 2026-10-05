# Instalação

Há dois jeitos de rodar. O primeiro é o que você usa no dia a dia; o segundo,
se for mexer no código.

---

## 1. Com Docker (recomendado)

Só precisa do Docker instalado. **Não** precisa de Python, Git, ambiente
virtual nem bibliotecas na máquina — e quem usa a aplicação pelo navegador não
precisa nem do Docker.

```bash
cp .env.example .env
```

Abra o `.env` e preencha três coisas:

| Campo | O que pôr |
|---|---|
| `GEMINI_API_KEY` | A chave do Gemini. Gere em [aistudio.google.com/apikey](https://aistudio.google.com/apikey), **num projeto com faturamento ativo** — veja o porquê abaixo. |
| `LAUDO_ADMIN_EMAIL` | Seu e-mail. É com ele que você entra. |
| `LAUDO_ADMIN_SENHA` | Uma senha de no mínimo 10 caracteres. Se for menor, o usuário não é criado e o log avisa. |

Depois:

```bash
docker compose build
```

```bash
docker compose up -d
```

Abra <http://localhost:8000>. O usuário inicial é criado na primeira subida.

> **A chave tem que estar num projeto com faturamento ativo.** Os termos da
> camada gratuita permitem ao Google usar o conteúdo enviado para melhorar
> produtos, com revisão humana, e pedem para não enviar informação pessoal ou
> confidencial. Este sistema envia fotos do interior de imóveis de clientes.
> Na camada paga o Google não usa prompts nem arquivos para isso. Custo medido
> na maior vistoria até hoje (11 cômodos, 358 fotos): ~US$ 0,14.

### Usar do celular

O contêiner escuta só em `127.0.0.1` por padrão. Para abrir no celular da mesma
rede, troque em `docker-compose.yml`:

```yaml
ports:
  - "8000:8000"
```

e acesse `http://IP-DO-COMPUTADOR:8000`. Para expor fora da rede local, leia
antes o [guia de produção](producao.md) — em especial a parte de HTTPS.

### Parar, atualizar, ver o log

```bash
docker compose logs -f laudo
```

```bash
docker compose down
```

```bash
git pull && docker compose build && docker compose up -d
```

Os dados ficam no volume `dados` e sobrevivem a `down`, `build` e `up`.

---

## 2. Sem Docker (desenvolvimento)

Precisa de Python 3.11+ e Node 20+.

**Backend:**

```bash
python -m pip install -r backend/requirements.txt
```

```bash
GEMINI_API_KEY=sua-chave LAUDO_ADMIN_EMAIL=voce@exemplo.com LAUDO_ADMIN_SENHA=uma-senha-boa PYTHONPATH=.:backend python -m uvicorn app.main:app --reload --port 8000
```

No Windows (PowerShell), defina as variáveis antes:

```bash
$env:GEMINI_API_KEY="sua-chave"; $env:PYTHONPATH=".;backend"; python -m uvicorn app.main:app --reload --port 8000
```

**Frontend**, noutro terminal:

```bash
cd frontend && npm install && npm run dev
```

Abra <http://localhost:5173>. O Vite manda `/api` para a porta 8000, então o
cookie de sessão funciona sem afrouxar o `SameSite`.

---

## 3. A linha de comando continua funcionando

A evolução para web não aposentou os scripts. Eles usam o **mesmo motor**
(`core/`), então o laudo sai igual:

```bash
python main.py "C:\caminho\para\o\imovel"
```

```bash
python main.py "C:\caminho\para\o\imovel" --evidencias
```

```bash
python validar.py "C:\caminho\para\o\imovel"
```

`--evidencias` liga a validação de escopo por foto, que na web é o padrão.

---

## Testes

```bash
python -m pytest
```

Nenhum teste chama a API do Gemini — as respostas do modelo são simuladas.
Rodar não custa nada e não depende de rede.

---

## Trazer uma vistoria antiga para o sistema

Na tela inicial, **Importar antiga**. Mande um ZIP da pasta do imóvel, no
formato de sempre (uma pasta por cômodo, com as fotos e os
`<cômodo>_vistoria.txt`).

O laudo já escrito é importado como está. Ele entra **sem evidências**, porque
o arquivo antigo não tem esse rastro — inventar procedência seria pior que não
ter. Para ganhar o rastro, reprocesse a vistoria depois de importada.
