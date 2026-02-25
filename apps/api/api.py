import os
import sys
import json
import sqlite3
import uuid
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Callable, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

RAG_ROOT = Path(__file__).resolve().parents[2] / "packages" / "rag"
sys.path.append(str(RAG_ROOT))

from src.collector import DrugDataCollector  # type: ignore
from src.reference_resolver import ReferenceResolver  # type: ignore
from src.config import Config  # type: ignore
from src.synopsis import YandexSynopsisGenerator  # type: ignore

from apps.api.docx_export import build_synopsis_docx
from apps.api.decision_engine import (
    normalize_cv,
    choose_design,
    compute_washout_days,
    sample_size,
    generate_timeline,
    summarize_rag,
)
from apps.api.pdf_export import make_synopsis_pdf
from apps.api.jobs import create_job, get_job
from tavily import TavilyClient


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")
Config.setup_windows_env()

app = FastAPI(title="Synopsis.Assist API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.getenv("DB_PATH", "data/app.db")
ARTIFACT_DIR = Path(os.getenv("ARTIFACT_DIR", "data/artifacts"))
RAG_TIMEOUT_S = float(os.getenv("RAG_TIMEOUT_S", "25"))




def _db_connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            response TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS synopses (
            id TEXT PRIMARY KEY,
            inputs TEXT NOT NULL,
            synopsis TEXT NOT NULL,
            rag TEXT NOT NULL,
            rag_summary TEXT NOT NULL,
            decision TEXT NOT NULL,
            stats TEXT NOT NULL,
            timeline TEXT NOT NULL,
            files TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


def _history_insert(kind: str, payload: dict, response: dict) -> None:
    conn = _db_connect()
    try:
        conn.execute(
            "INSERT INTO history (kind, payload, response, created_at) VALUES (?, ?, ?, ?)",
            (
                kind,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(response, ensure_ascii=False),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _synopsis_insert(
    docx_id: str,
    inputs: dict,
    synopsis: dict,
    rag: dict,
    rag_summary: dict,
    decision: dict,
    stats: dict,
    timeline: dict,
    files: dict,
) -> None:
    conn = _db_connect()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO synopses
            (id, inputs, synopsis, rag, rag_summary, decision, stats, timeline, files, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                docx_id,
                json.dumps(inputs, ensure_ascii=False),
                json.dumps(synopsis, ensure_ascii=False),
                json.dumps(rag, ensure_ascii=False),
                json.dumps(rag_summary, ensure_ascii=False),
                json.dumps(decision, ensure_ascii=False),
                json.dumps(stats, ensure_ascii=False),
                json.dumps(timeline, ensure_ascii=False),
                json.dumps(files, ensure_ascii=False),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _synopsis_list(limit: int = 30) -> list[dict]:
    conn = _db_connect()
    try:
        rows = conn.execute(
            "SELECT id, inputs, files, created_at FROM synopses ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _synopsis_get(item_id: str) -> Optional[dict]:
    conn = _db_connect()
    try:
        row = conn.execute(
            "SELECT id, inputs, synopsis, rag, rag_summary, decision, stats, timeline, files, created_at FROM synopses WHERE id = ?",
            (item_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _history_list(limit: int = 50) -> list[dict]:
    conn = _db_connect()
    try:
        rows = conn.execute(
            "SELECT id, kind, payload, response, created_at FROM history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _history_get(item_id: int) -> Optional[dict]:
    conn = _db_connect()
    try:
        row = conn.execute(
            "SELECT id, kind, payload, response, created_at FROM history WHERE id = ?",
            (item_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()




class SynopsisRequest(BaseModel):
    inn: str
    form: str
    dosage: str
    cvIntra: str
    rsabe: bool
    design: str
    regimen: str
    studyType: str
    constraints: str = ""


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatTurn] = []


class ExportRequest(BaseModel):
    synopsis: dict
    decision: dict = {}
    stats: dict = {}
    timeline: dict = {}
    ragSummary: dict = {}
    rag: dict = {}


class ParseRequest(BaseModel):
    name: str
    dosage: str


def _get_yandex_keys() -> tuple[str, str]:
    folder_id = os.getenv("YANDEX_FOLDER_ID")
    auth_key = os.getenv("YANDEX_AUTH_KEY")
    if not folder_id or not auth_key:
        raise HTTPException(status_code=400, detail="YANDEX_FOLDER_ID and YANDEX_AUTH_KEY are required")
    return folder_id, auth_key


def _get_tavily_key() -> str:
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        raise HTTPException(status_code=400, detail="TAVILY_API_KEY is required for parser endpoints")
    return tavily_key


def _quick_sources(inn: str, dosage: str, regimen: str) -> list[dict]:
    try:
        key = _get_tavily_key()
    except HTTPException:
        return []
    client = TavilyClient(api_key=key)
    query = f"{inn} {dosage} pharmacokinetics Cmax AUC Tmax {regimen}".strip()
    try:
        res = client.search(query=query, search_depth="basic", max_results=5, include_raw_content=False)
        out = []
        for r in (res.get("results", []) or [])[:5]:
            out.append({"title": r.get("title", ""), "uri": r.get("url", ""), "used_for": ["fallback_source"], "quote": ""})
        return out
    except Exception:
        return []


def _run_with_timeout(fn: Callable[[], Any], timeout_s: float, fallback: Any) -> Any:
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        try:
            return fut.result(timeout=timeout_s)
        except TimeoutError:
            return fallback
        except Exception:
            return fallback


def _export_artifacts(
    synopsis_inputs: dict,
    synopsis: dict,
    rag_result: dict,
    rag_summary: dict,
    decision: dict,
    stats: dict,
    timeline: dict,
) -> dict:
    docx_bytes = build_synopsis_docx(
        synopsis=synopsis,
        decision=decision,
        stats=stats,
        timeline=timeline,
        rag_summary=rag_summary,
    )

    pdf_bytes = make_synopsis_pdf(
        synopsis=synopsis,
        decision=decision,
        stats=stats,
        timeline=timeline,
        rag_summary=rag_summary,
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    docx_id = uuid.uuid4().hex

    (ARTIFACT_DIR / f"{docx_id}.docx").write_bytes(docx_bytes)
    (ARTIFACT_DIR / f"{docx_id}.pdf").write_bytes(pdf_bytes)

    json_payload = {
        "inputs": synopsis_inputs,
        "synopsis": synopsis,
        "rag": rag_result,
        "ragSummary": rag_summary,
        "decision": decision,
        "stats": stats,
        "timeline": timeline,
        "docxId": docx_id,
        "files": {
            "docx": f"/api/design/{docx_id}.docx",
            "pdf": f"/api/design/{docx_id}.pdf",
            "json": f"/api/design/{docx_id}.json",
            "md": f"/api/design/{docx_id}.md",
            "yaml": f"/api/design/{docx_id}.yaml",
        },
    }
    (ARTIFACT_DIR / f"{docx_id}.json").write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / f"{docx_id}.md").write_text(synopsis.get("markdown", "") or "", encoding="utf-8")
    (ARTIFACT_DIR / f"{docx_id}.yaml").write_text(synopsis.get("yaml", "") or "", encoding="utf-8")
    return json_payload


def _run_design_pipeline(
    inn: str,
    form: str,
    dosage: str,
    cvIntra: str,
    rsabe: str,
    design: str,
    regimen: str,
    studyType: str,
    constraints: str,
    dropOut: str,
    screenFail: str,
    refTradeName: str,
    mode: str,
    file_path: str | None,
    progress_cb: Callable[[str, float, str, dict | None], None] | None = None,
) -> dict:
    def _emit(stage: str, progress: float, message: str, payload: dict | None = None) -> None:
        if progress_cb:
            progress_cb(stage, progress, message, payload)

    folder_id, auth_key = _get_yandex_keys()

    cv_manual = cvIntra.strip().lower() not in ("", "auto")
    skip_be = cv_manual
    skip_instruction = cv_manual and os.getenv("RAG_SKIP_INSTRUCTION_ON_MANUAL_CV", "1") == "1"

    cv_intra_input = normalize_cv(cvIntra)
    cv_final = cv_intra_input if cv_intra_input is not None else 0.25
    rag_result = {
        "pk": {"tmax_h": None, "t12_h": None},
        "cvintra": {"cmax": None, "auc": None},
        "evidence": [],
        "evidence_docs": [],
        "warnings": [],
        "notes": {"stage": "draft_only"},
    }
    if cv_intra_input is None:
        rag_result["warnings"].append("CVintra не найден: использован дефолт 0.25")
    rag_result["warnings"].append("T1/2 не найден: washout/horizon по умолчанию")

    drop_out = normalize_cv(dropOut) or 0.0
    screen_fail = normalize_cv(screenFail) or 0.0
    rsabe_bool = rsabe.lower() == "true"

    decision = choose_design(rsabe_bool, cv_final)
    decision["washout_days"] = 7
    stats = sample_size(cv_final, drop_out=drop_out, screen_fail=screen_fail)
    timeline = generate_timeline(None, None)

    _emit("draft", 0.2, "Fast draft")
    generator = YandexSynopsisGenerator(folder_id=folder_id, auth_key=auth_key)
    synopsis_inputs = {
        "inn": inn,
        "form": form,
        "dosage": dosage,
        "cvIntra": cv_final if cv_final is not None else cvIntra,
        "rsabe": rsabe_bool,
        "design": decision["design"] if (not design or design == "auto") else design,
        "regimen": regimen,
        "studyType": studyType,
        "constraints": constraints,
    }

    synopsis = generator.generate(
        synopsis_inputs,
        rag_context={
            "rag": rag_result,
            "ragSummary": summarize_rag(rag_result),
            "decision": decision,
            "stats": stats,
            "timeline": timeline,
        },
        use_llm=False,
    )
    if progress_cb:
        progress_cb("export", 0.35, "Формирование черновика", None)
    rag_summary_draft = summarize_rag(rag_result)
    draft_payload = _export_artifacts(
        synopsis_inputs=synopsis_inputs,
        synopsis=synopsis,
        rag_result=rag_result,
        rag_summary=rag_summary_draft,
        decision=decision,
        stats=stats,
        timeline=timeline,
    )
    _emit("draft", 0.4, "Draft ready", draft_payload)

    _synopsis_insert(
        docx_id=draft_payload["docxId"],
        inputs=synopsis_inputs,
        synopsis=synopsis,
        rag=rag_result,
        rag_summary=rag_summary_draft,
        decision=decision,
        stats=stats,
        timeline=timeline,
        files=draft_payload["files"],
    )

    _history_insert(
        "design",
        {
            "inn": inn,
            "form": form,
            "dosage": dosage,
            "cvIntra": cvIntra,
            "rsabe": rsabe,
            "design": design,
            "regimen": regimen,
            "studyType": studyType,
            "constraints": constraints,
            "dropOut": dropOut,
            "screenFail": screenFail,
            "refTradeName": refTradeName,
            "stage": "draft",
        },
        {
            "docxId": draft_payload["docxId"],
            "files": draft_payload["files"],
            "decision": decision,
            "stats": stats,
            "timeline": timeline,
            "ragSummary": rag_summary_draft,
        },
    )

    if mode != "enrich":
        return draft_payload

    rag_timeout_s = float(os.getenv("RAG_TIMEOUT_S", "25"))
    if rag_timeout_s > 60:
        rag_timeout_s = 60
    deadline_ts = time.time() + rag_timeout_s
    try:
        tavily_key = _get_tavily_key()
    except HTTPException:
        tavily_key = ""
    if not tavily_key:
        rag_result.setdefault("warnings", [])
        rag_result["warnings"].append("TAVILY_API_KEY не задан: пропущен поиск источников")
        return draft_payload

    collector = DrugDataCollector(tavily_key=tavily_key)
    _emit("discover", 0.5, "Поиск источников")
    rag_enriched = _run_with_timeout(
        lambda: collector.get_drug_info(
            drug_inn=inn,
            dosage=dosage,
            dosage_form=form,
            regimen=regimen,
            reference_trade_name=refTradeName or None,
            skip_be=skip_be,
            skip_instruction=skip_instruction,
            deadline_ts=deadline_ts,
            source_path=file_path,
        ),
        timeout_s=rag_timeout_s,
        fallback=rag_result,
    )
    if rag_enriched is rag_result:
        rag_enriched.setdefault("notes", {})
        rag_enriched["notes"]["rag_error"] = "rag_timeout_or_error"

    rag_summary = summarize_rag(rag_enriched)
    if not rag_enriched.get("evidence_docs"):
        rag_enriched.setdefault("evidence_docs", [])
        rag_enriched["evidence_docs"].extend(_quick_sources(inn, dosage, regimen))

    cv_intra_auto = None
    if rag_summary.get("cvintra_cmax") is not None:
        cv_intra_auto = normalize_cv(rag_summary.get("cvintra_cmax"))
    if rag_summary.get("cvintra_auc") is not None:
        cv_intra_auto = max(cv_intra_auto or 0, normalize_cv(rag_summary.get("cvintra_auc")) or 0)
    if cv_intra_input is not None:
        cv_final = cv_intra_input
    elif cv_intra_auto is not None:
        cv_final = cv_intra_auto
    else:
        cv_final = 0.25
        rag_enriched.setdefault("warnings", [])
        rag_enriched["warnings"].append("CVintra не найден: использован дефолт 0.25")

    decision = choose_design(rsabe_bool, cv_final)
    decision["washout_days"] = compute_washout_days(rag_summary.get("t12_h"))
    stats = sample_size(cv_final, drop_out=drop_out, screen_fail=screen_fail)
    timeline = generate_timeline(rag_summary.get("tmax_h"), rag_summary.get("t12_h"))
    if rag_summary.get("t12_h") is None:
        rag_enriched.setdefault("warnings", [])
        rag_enriched["warnings"].append("T1/2 не найден: washout/horizon по умолчанию")

    _emit("synopsis", 0.7, "Генерация синопсиса")
    synopsis = generator.generate(
        synopsis_inputs,
        rag_context={
            "rag": rag_enriched,
            "ragSummary": rag_summary,
            "decision": decision,
            "stats": stats,
            "timeline": timeline,
        },
    )

    _emit("export", 0.85, "Формирование документов")
    json_payload = _export_artifacts(
        synopsis_inputs=synopsis_inputs,
        synopsis=synopsis,
        rag_result=rag_enriched,
        rag_summary=rag_summary,
        decision=decision,
        stats=stats,
        timeline=timeline,
    )

    _synopsis_insert(
        docx_id=json_payload["docxId"],
        inputs=synopsis_inputs,
        synopsis=synopsis,
        rag=rag_enriched,
        rag_summary=rag_summary,
        decision=decision,
        stats=stats,
        timeline=timeline,
        files=json_payload["files"],
    )

    _history_insert(
        "design",
        {
            "inn": inn,
            "form": form,
            "dosage": dosage,
            "cvIntra": cvIntra,
            "rsabe": rsabe,
            "design": design,
            "regimen": regimen,
            "studyType": studyType,
            "constraints": constraints,
            "dropOut": dropOut,
            "screenFail": screenFail,
            "refTradeName": refTradeName,
        },
        {
            "docxId": json_payload["docxId"],
            "files": json_payload["files"],
            "decision": decision,
            "stats": stats,
            "timeline": timeline,
            "ragSummary": rag_summary,
        },
    )

    _emit("done", 1.0, "Done", json_payload)
    return json_payload
@app.get("/api/reference-options")
def reference_options(inn: str, dosage: str, form: str) -> dict:
    try:
        return GRLS_RESOLVER.find_reference_options(inn=inn, dosage=dosage, dosage_form=form, limit=10)
    except Exception as e:
        return {"inn": inn, "dosage": dosage, "dosage_form": form, "default_trade_name": "", "options": [], "loading": False, "warning": str(e)}

@app.get("/api/grls-search")
def grls_search(q: str, dosage: str = "", form: str = "", limit: int = 20) -> dict:
    try:
        return GRLS_RESOLVER.search(query=q, dosage=dosage, dosage_form=form, limit=limit)
    except Exception as e:
        return {"query": q, "dosage": dosage, "dosage_form": form, "items": [], "loading": False, "warning": str(e)}

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/reference-options")
def reference_options(inn: str, dosage: str, form: str) -> dict:
    return GRLS_RESOLVER.find_reference_options(inn=inn, dosage=dosage, dosage_form=form, limit=10)


@app.get("/api/grls-search")
def grls_search(q: str, dosage: str = "", form: str = "", limit: int = 20) -> dict:
    return GRLS_RESOLVER.search(query=q, dosage=dosage, dosage_form=form, limit=limit)


@app.post("/api/synopsis")
def generate_synopsis(payload: SynopsisRequest) -> dict:
    folder_id, auth_key = _get_yandex_keys()
    generator = YandexSynopsisGenerator(folder_id=folder_id, auth_key=auth_key)
    result = generator.generate(payload.model_dump())
    _history_insert("synopsis", payload.model_dump(), result)
    return result


@app.post("/api/design")
async def design(
    inn: str = Form(...),
    form: str = Form(...),
    dosage: str = Form(...),
    cvIntra: str = Form("auto"),
    rsabe: str = Form("false"),
    design: str = Form("auto"),
    regimen: str = Form("Натощак"),
    studyType: str = Form("Однофазное"),
    constraints: str = Form(""),
    dropOut: str = Form("0"),
    screenFail: str = Form("0"),
    refTradeName: str = Form(""),
    mode: str = Form("enrich"),
    file: UploadFile | None = File(None),
) -> dict:
    file_path = None
    if file:
        suffix = os.path.splitext(file.filename or "")[-1] or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            file_path = tmp.name
    try:
        return _run_design_pipeline(
            inn=inn,
            form=form,
            dosage=dosage,
            cvIntra=cvIntra,
            rsabe=rsabe,
            design=design,
            regimen=regimen,
            studyType=studyType,
            constraints=constraints,
            dropOut=dropOut,
            screenFail=screenFail,
            refTradeName=refTradeName,
            mode=mode if mode in ("fast", "enrich") else "enrich",
            file_path=file_path,
            progress_cb=None,
        )
    finally:
        if file_path:
            try:
                os.remove(file_path)
            except OSError:
                pass


@app.post("/api/design-async")
async def design_async(
    inn: str = Form(...),
    form: str = Form(...),
    dosage: str = Form(...),
    cvIntra: str = Form("auto"),
    rsabe: str = Form("false"),
    design: str = Form("auto"),
    regimen: str = Form("Натощак"),
    studyType: str = Form("Однофазное"),
    constraints: str = Form(""),
    dropOut: str = Form("0"),
    screenFail: str = Form("0"),
    refTradeName: str = Form(""),
    mode: str = Form("enrich"),
    file: UploadFile | None = File(None),
) -> dict:
    file_path = None
    if file:
        suffix = os.path.splitext(file.filename or "")[-1] or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            file_path = tmp.name

    def pipeline(update):
        try:
            return _run_design_pipeline(
                inn=inn,
                form=form,
                dosage=dosage,
                cvIntra=cvIntra,
                rsabe=rsabe,
                design=design,
                regimen=regimen,
                studyType=studyType,
                constraints=constraints,
                dropOut=dropOut,
                screenFail=screenFail,
                refTradeName=refTradeName,
                mode=mode if mode in ("fast", "enrich") else "enrich",
                file_path=file_path,
                progress_cb=update,
            )
        finally:
            if file_path:
                try:
                    os.remove(file_path)
                except OSError:
                    pass

    job = create_job("design", pipeline)
    return {"jobId": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/design/{docx_id}.docx")
def download_docx(docx_id: str):
    path = ARTIFACT_DIR / f"{docx_id}.docx"
    if not path.exists():
        raise HTTPException(status_code=404, detail="DOCX not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"bioequiv_{docx_id}.docx",
    )


@app.get("/api/design/{docx_id}.pdf")
def download_pdf(docx_id: str):
    path = ARTIFACT_DIR / f"{docx_id}.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"bioequiv_{docx_id}.pdf",
    )


@app.get("/api/design/{docx_id}.json")
def download_json(docx_id: str):
    path = ARTIFACT_DIR / f"{docx_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="JSON not found")
    return FileResponse(
        path,
        media_type="application/json",
        filename=f"bioequiv_{docx_id}.json",
    )


@app.get("/api/design/{docx_id}.md")
def download_markdown(docx_id: str):
    path = ARTIFACT_DIR / f"{docx_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Markdown not found")
    return FileResponse(path, media_type="text/markdown", filename=f"bioequiv_{docx_id}.md")


@app.get("/api/design/{docx_id}.yaml")
def download_yaml(docx_id: str):
    path = ARTIFACT_DIR / f"{docx_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="YAML not found")
    return FileResponse(path, media_type="text/yaml", filename=f"bioequiv_{docx_id}.yaml")


@app.post("/api/export")
def export_synopsis(payload: ExportRequest) -> dict:
    synopsis = payload.synopsis or {}
    decision = payload.decision or {}
    stats = payload.stats or {}
    timeline = payload.timeline or {}
    rag_summary = payload.ragSummary or {}
    rag = payload.rag or {}

    docx_bytes = build_synopsis_docx(
        synopsis=synopsis,
        decision=decision,
        stats=stats,
        timeline=timeline,
        rag_summary=rag_summary,
    )

    pdf_bytes = make_synopsis_pdf(
        synopsis=synopsis,
        decision=decision,
        stats=stats,
        timeline=timeline,
        rag_summary=rag_summary,
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    docx_id = uuid.uuid4().hex

    (ARTIFACT_DIR / f"{docx_id}.docx").write_bytes(docx_bytes)
    (ARTIFACT_DIR / f"{docx_id}.pdf").write_bytes(pdf_bytes)

    json_payload = {
        "inputs": {},
        "synopsis": synopsis,
        "rag": rag,
        "ragSummary": rag_summary,
        "decision": decision,
        "stats": stats,
        "timeline": timeline,
        "docxId": docx_id,
        "files": {
            "docx": f"/api/design/{docx_id}.docx",
            "pdf": f"/api/design/{docx_id}.pdf",
            "json": f"/api/design/{docx_id}.json",
            "md": f"/api/design/{docx_id}.md",
            "yaml": f"/api/design/{docx_id}.yaml",
        },
    }
    (ARTIFACT_DIR / f"{docx_id}.json").write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ARTIFACT_DIR / f"{docx_id}.md").write_text(synopsis.get("markdown", "") or "", encoding="utf-8")
    (ARTIFACT_DIR / f"{docx_id}.yaml").write_text(synopsis.get("yaml", "") or "", encoding="utf-8")

    _synopsis_insert(
        docx_id=docx_id,
        inputs={},
        synopsis=synopsis,
        rag=rag,
        rag_summary=rag_summary,
        decision=decision,
        stats=stats,
        timeline=timeline,
        files=json_payload["files"],
    )

    return json_payload


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict:
    folder_id, auth_key = _get_yandex_keys()
    generator = YandexSynopsisGenerator(folder_id=folder_id, auth_key=auth_key)

    history_lines = []
    for turn in payload.history[-8:]:
        role = "Пользователь" if turn.role == "user" else "Ассистент"
        history_lines.append(f"{role}: {turn.content}")

    prompt = "\n".join(
        [
            "Ты — эксперт по планированию БЭ исследований и Решению №85 ЕЭК.",
            "Отвечай кратко и по делу.",
            "История:",
            *history_lines,
            f"Пользователь: {payload.message}",
            "Ассистент:",
        ]
    )

    result = generator.model.run(prompt)
    text = result.alternatives[0].text if result and result.alternatives else ""
    result_obj = {"text": text or "Нет ответа."}
    _history_insert("chat", payload.model_dump(), result_obj)
    return result_obj


@app.post("/api/parse-drug")
def parse_drug(payload: ParseRequest) -> dict:
    tavily_key = _get_tavily_key()

    collector = DrugDataCollector(tavily_key=tavily_key)
    result = collector.get_drug_info(
        drug_inn=payload.name,
        dosage=payload.dosage,
        dosage_form="",
        regimen="",
        reference_trade_name=None,
    )
    _history_insert("parse-drug", payload.model_dump(), result)
    return result


@app.post("/api/parse-pdf")
async def parse_pdf(
    name: str = Form(...),
    dosage: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    tavily_key = _get_tavily_key()
    collector = DrugDataCollector(tavily_key=tavily_key)
    result = collector.get_drug_info(
        drug_inn=name,
        dosage=dosage,
        dosage_form="",
        regimen="",
        reference_trade_name=None,
    )
    _history_insert("parse-pdf", {"name": name, "dosage": dosage, "file": file.filename}, result)
    return result


@app.get("/api/history")
def history(limit: int = 50) -> dict:
    return {"items": _history_list(limit=limit)}


@app.get("/api/history/{item_id}")
def history_item(item_id: int) -> dict:
    item = _history_get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item


@app.get("/api/synopses")
def synopses(limit: int = 30) -> dict:
    return {"items": _synopsis_list(limit=limit)}


@app.get("/api/synopses/{item_id}")
def synopses_item(item_id: str) -> dict:
    item = _synopsis_get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item


frontend_dist = os.getenv("FRONTEND_DIST")
if frontend_dist:
    dist_path = Path(frontend_dist)
    index_file = dist_path / "index.html"
    assets_dir = dist_path / "assets"

    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    if index_file.exists():
        @app.get("/", include_in_schema=False)
        def serve_index():
            return FileResponse(index_file)

        @app.get("/{path:path}", include_in_schema=False)
        def serve_spa(path: str):
            if path.startswith("api"):
                raise HTTPException(status_code=404, detail="Not found")
            candidate = dist_path / path
            if candidate.exists() and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_file)
GRLS_RESOLVER = ReferenceResolver()
