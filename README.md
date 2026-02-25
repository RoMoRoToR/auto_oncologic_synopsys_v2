# BioEquiv AI + RAG Parser

Полноценное приложение, объединяющее генерацию синопсиса БЭ, RAG‑парсер и заполнение шаблона DOCX.

## Быстрый запуск через Docker

1. Создайте `.env` в корне проекта по шаблону `.env.example`.
2. Запуск:
   ```bash
   docker compose up --build
   ```
3. Откройте интерфейс: `http://localhost:8000`.

Шаблон DOCX должен лежать в корне: `Шаблон Синопсиса Протокола.docx`.

## Локальная разработка

Backend:
```bash
cd /Users/taniyashuba/PycharmProjects/auto_oncologic_synopsys
pip install -r apps/api/requirements.txt
pip install -r packages/rag/requirements.txt
uvicorn apps.api.api:app --host 0.0.0.0 --port 8000 --reload
```

Frontend:
```bash
cd apps/web
npm install
npm run dev
```
