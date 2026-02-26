# Architecture (Hackathon)

## Goals

* Always return a usable protocol synopsis in seconds.
* Enrichment (sources) is best‑effort and never blocks the draft.
* Deterministic calculations for design/sample size/timeline.

## High‑Level Flow

1. **Input (UI)** → `POST /api/design-async` (draft)
2. **Draft stage** (fast):
   * Default CV (0.25) if auto
   * Deterministic design/sample size/timeline
   * Generate synopsis + artifacts (DOCX/PDF/JSON/MD/YAML)
3. **Enrichment stage** (best‑effort) → `POST /api/enrich-async`:
   * Tavily discovery
   * raw_content/HTML extraction
   * PDF text layer extraction (no OCR)
   * Update PK/CV → recalc → regenerate artifacts

## Modules

* `apps/api/api.py` — API endpoints + orchestration
* `apps/api/decision_engine.py` — deterministic math
* `apps/api/jobs.py` — job state + polling contract
* `packages/rag/src/*` — RAG pipeline
* `apps/web` — UI

## Data Contract (Master JSON)

* `inputs` — user inputs
* `rag` — evidence, pk, cvintra
* `ragSummary` — summary fields (tmax/t1_2/cv)
* `decision` — design/periods/washout
* `stats` — sample size + assumptions
* `timeline` — timepoints + rationale
* `files` — docx/pdf/json/md/yaml links

## Reliability

* Draft always produced.
* Enrichment time‑bounded.
* Evidence links returned even if no numbers extracted.
