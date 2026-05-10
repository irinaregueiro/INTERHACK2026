# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY etl/ ./etl/
COPY models/ ./models/
COPY shared/ ./shared/
COPY data/ ./data/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["sh", "-c", "if [ \"${CT_RUN_ETL_ON_START:-auto}\" != \"0\" ] && [ -f data/raw/Datasets.xlsx ] && { [ ! -f data/processed/client_category_week.parquet ] || [ ! -f data/processed/sow_potencial.parquet ] || [ ! -f data/processed/precio_medio_categoria.parquet ]; }; then python -m etl.pipeline; fi; exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
