FROM node:20-alpine AS frontend
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci
COPY apps/web/ ./
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
  && rm -rf /var/lib/apt/lists/*

COPY packages/rag/requirements.txt /app/requirements-rag.txt
COPY apps/api/requirements.txt /app/requirements-api.txt

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --timeout 120 --retries 5 -r /app/requirements-rag.txt -r /app/requirements-api.txt

COPY packages/rag /app/packages/rag
COPY apps/api /app/apps/api
COPY --from=frontend /app/dist /app/frontend_dist

ENV FRONTEND_DIST=/app/frontend_dist
ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "apps.api.api:app", "--host", "0.0.0.0", "--port", "8000"]
