# Synopsis.Assist — Bioequivalence Planning

Инструмент для автоматического планирования исследований биоэквивалентности:  
дизайн, расчёт выборки, таймпоинты, синопсис и артефакты (DOCX/PDF/JSON/MD/YAML).

## Быстрый запуск через Docker

1. Создайте `.env` в корне проекта по шаблону `.env.example`.
2. Запуск:
   ```bash
   docker compose up --build
   ```
3. Откройте интерфейс: `http://localhost:8000`.

Шаблон DOCX **не нужен** — документ генерируется программно.

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

## Переменные окружения

Скопируйте `.env.example` → `.env` и задайте ключи:

```text
TAVILY_API_KEY=...
YANDEX_FOLDER_ID=...
YANDEX_AUTH_KEY=...
```

## Режимы работы

* **Fast Draft**: генерирует результат за секунды, даже без источников.
* **Enrich**: запускается отдельной кнопкой и обновляет источники/расчёты.

## Документация для хакатона

* `docs/architecture.md`
* `docs/demo.md`
