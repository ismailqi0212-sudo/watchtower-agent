# syntax=docker/dockerfile:1

FROM node:20-alpine AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WATCHTOWER_DB=/app/data/watchtower.db
WORKDIR /app

COPY requirements.txt requirements-real.txt ./
RUN pip install --no-cache-dir -r requirements-real.txt

COPY app ./app
COPY evals ./evals
COPY data ./data
COPY scripts ./scripts
COPY --from=web /app/web/dist ./web/dist

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
