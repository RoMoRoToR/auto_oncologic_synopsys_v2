from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from tavily import TavilyClient

from .parser import PDFParser


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


@dataclass
class InstructionDoc:
    title: str
    url: str
    relevant_md: str
    sha256: str


class InstructionFinder:
    def __init__(self, tavily_key: str | None = None, cache_dir: str | None = None):
        tavily_key = tavily_key or os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            raise ValueError("TAVILY_API_KEY required")
        self.searcher = TavilyClient(api_key=tavily_key)

        base = Path(cache_dir or os.getenv("RAG_CACHE_DIR", "data/rag_cache"))
        self.cache_dir = base / "instruction_search"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.parser = PDFParser(cache_dir=str(base / "pdf_cache"))

    def _search_cached(self, query: str, max_results: int = 8) -> Dict[str, Any]:
        key = _sha(f"{query}::{max_results}")
        p = self.cache_dir / f"{key}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        res = self.searcher.search(query=query, search_depth="advanced", max_results=max_results, include_raw_content=True)
        simp = {
            "query": query,
            "answer": res.get("answer", ""),
            "results": [
                {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", ""), "raw": r.get("raw_content", "")}
                for r in (res.get("results", []) or [])
            ],
        }
        p.write_text(json.dumps(simp, ensure_ascii=False, indent=2), encoding="utf-8")
        return simp

    def _is_pdf_url(self, url: str) -> bool:
        u = (url or "").lower()
        return u.endswith(".pdf") or ".pdf?" in u or "filetype=pdf" in u

    def _dedupe_docs(self, docs: List[Dict[str, str]]) -> List[Dict[str, str]]:
        seen = set()
        out = []
        for d in docs:
            uri = (d.get("uri") or "").strip()
            if not uri or uri in seen:
                continue
            seen.add(uri)
            out.append(d)
        return out

    def find_instruction(
        self,
        trade_name: str,
        dosage: str,
        dosage_form: str,
        deadline_ts: float | None = None,
        source_path: str | None = None,
        deep_mode: bool = False,
    ) -> Dict[str, Any]:
        raw_limit = int(os.getenv("RAG_TEXT_CHARS", "20000"))
        def time_left() -> float:
            if deadline_ts is None:
                return 9999.0
            return deadline_ts - time.time()

        evidence_docs: List[Dict[str, str]] = []
        raw_hits: List[Dict[str, str]] = []
        best_doc: Optional[InstructionDoc] = None

        if source_path and time_left() > 2.0:
            try:
                parsed = self.parser.parse(
                    source_path,
                    title=f"Uploaded PDF{(': ' + trade_name) if trade_name else ''}",
                    uri="uploaded://pdf",
                    keywords=[
                        "tmax",
                        "t1/2",
                        "half-life",
                        "период полувыведения",
                        "время достижения максимальной концентрации",
                        "cmax",
                        "auc",
                        "within-subject",
                        "cv",
                    ],
                    allow_ocr=deep_mode,
                )
                best_doc = InstructionDoc(
                    title=parsed.title,
                    url=parsed.uri,
                    relevant_md=parsed.relevant_md,
                    sha256=parsed.sha256,
                )
                evidence_docs.append({"title": parsed.title, "uri": parsed.uri, "kind": "uploaded_pdf"})
            except Exception:
                evidence_docs.append({"title": "Uploaded PDF (parse failed)", "uri": "uploaded://pdf", "kind": "uploaded_pdf"})

        tn = (trade_name or "").strip()
        if not tn:
            return {"doc": best_doc, "evidence_docs": self._dedupe_docs(evidence_docs), "queries": [], "raw_hits": raw_hits}

        queries = [
            f"\"{tn}\" {dosage} {dosage_form} инструкция pdf",
            f"\"{tn}\" \"инструкция по медицинскому применению\" filetype:pdf",
            f"\"{tn}\" {dosage} mg SmPC pdf",
            f"site:grls.rosminzdrav.ru \"{tn}\" инструкция",
            f"site:ema.europa.eu {tn} SmPC pdf",
        ]

        for q in queries:
            if time_left() < 2.0:
                break
            data = self._search_cached(q, max_results=8)
            for r in data.get("results", [])[:6]:
                url = (r.get("url") or "").strip()
                title = (r.get("title") or "").strip() or url
                if not url:
                    continue
                evidence_docs.append({"title": title, "uri": url, "kind": "instruction_candidate"})

                raw = ((r.get("raw") or "") + "\n" + (r.get("content") or "")).strip()
                raw_low = raw.lower()
                if raw:
                    raw_hits.append({"title": title, "uri": url, "text": _clip(raw, raw_limit)})
                if raw and any(
                    k in raw_low
                    for k in [
                        "tmax",
                        "half-life",
                        "t1/2",
                        "период полувыведения",
                        "время достижения максимальной концентрации",
                    ]
                ):
                    best_doc = InstructionDoc(
                        title=title,
                        url=url,
                        relevant_md=_clip(raw, raw_limit),
                        sha256=_sha(url + raw),
                    )
                    break
            if best_doc:
                break

        if not best_doc and time_left() > 6.0:
            for ed in evidence_docs:
                url = ed["uri"]
                if not self._is_pdf_url(url):
                    continue
                try:
                    parsed = self.parser.parse(url, title=ed["title"], uri=url, allow_ocr=deep_mode)
                    best_doc = InstructionDoc(
                        title=parsed.title,
                        url=url,
                        relevant_md=parsed.relevant_md,
                        sha256=parsed.sha256,
                    )
                    break
                except Exception:
                    continue

        return {
            "doc": best_doc,
            "evidence_docs": self._dedupe_docs(evidence_docs),
            "queries": queries,
            "raw_hits": raw_hits[:6],
        }
