# Imagem única: o build do frontend entra estático na mesma aplicação que
# serve a API (regra 25 — nada de arquitetura de dezenas de serviços).

# --- 1. build do frontend -------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /frontend
# Copia só os manifestos primeiro: a camada de dependências só é refeita
# quando o package.json muda, não a cada alteração de código.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. aplicação ---------------------------------------------------------
FROM python:3.12-slim AS aplicacao

# libheif: sem ela o pillow-heif não decodifica, e a foto padrão do iPhone
# seria recusada no upload.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libheif1 curl \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend \
    LAUDO_DIRETORIO_DADOS=/dados \
    LAUDO_FRONTEND_DIST=/app/frontend/dist

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY core/ ./core/
COPY backend/ ./backend/
COPY regras_validadas.txt ./
COPY main.py validar.py conferir.py revisar.py ./
COPY config.py style_guide.py image_utils.py report_writer.py gemini_client.py validacao.py room_processor.py ./
COPY --from=frontend /frontend/dist ./frontend/dist

# Usuário sem privilégios: um furo na aplicação não vira root no contêiner.
RUN useradd --uid 10001 --create-home laudo \
 && mkdir -p /dados && chown -R laudo:laudo /dados /app
USER laudo

VOLUME ["/dados"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/saude || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
