# RAG Pipeline (Lite)

Быстрый и устойчивый сбор источников и PK‑параметров без OCR.  
Приоритет — скорость и воспроизводимость для хакатонного демо.

## Что делает

* Находит источники через Tavily (web search).
* Извлекает Tmax / T1/2 / CVintra из raw_content и HTML.
* При необходимости читает **текстовый слой PDF** (без OCR).
* Возвращает `evidence_docs` всегда, даже если чисел нет.

## Стек

* **Search:** Tavily API
* **PDF (text layer):** pypdf
* **LLM (опционально):** YandexGPT — только для полировки текста

## Структура

* `src/parser.py` — быстрый парсер PDF без OCR
* `src/instruction_finder.py` — поиск инструкции/SmPC + raw_content
* `src/label_extractor.py` — извлечение Tmax/T1/2
* `src/be_miner.py` — поиск BE‑источников и CV
* `src/collector.py` — сборка master JSON

## Установка

```bash
pip install -r requirements.txt
```

## Настройки (.env)

```text
TAVILY_API_KEY=your_tavily_key
YANDEX_FOLDER_ID=your_folder_id   # опционально
YANDEX_AUTH_KEY=your_auth_key     # опционально
```

## Запуск

RAG используется через API `apps/api`, прямой CLI не требуется.
