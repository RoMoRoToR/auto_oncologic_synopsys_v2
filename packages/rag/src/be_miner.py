from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import time

import requests
from tavily import TavilyClient
from yandex_ai_studio_sdk import AIStudio

from .parser import PDFParser
from .json_utils import extract_json


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _to_float(s: str) -> Optional[float]:
    s = s.strip().replace(",", ".").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def _norm_cv(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    if v > 1.5:
        v = v / 100.0
    if v < 0 or v > 1:
        return None
    return v


def _is_pdf_url(url: str) -> bool:
    u = (url or "").lower()
    return u.endswith(".pdf") or ".pdf?" in u or "filetype=pdf" in u


def _fetch_html_text(url: str, timeout_s: float = 18.0) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36"
        )
    }
    r = requests.get(url, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    html = r.text

    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    html = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;|&#160;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    html = re.sub(r"\s+", " ", html).strip()
    return html


def _extract_cv_candidates(text: str) -> Dict[str, List[Tuple[float, str]]]:
    low = (text or "").lower()
    out: Dict[str, List[Tuple[float, str]]] = {"cmax": [], "auc": []}

    patterns = [
        (
            r"(cmax).{0,40}(?:cv|coefficient of variation|within[-\s]?subject cv|intra[-\s]?subject cv).{0,40}([0-9]{1,2}(?:\.[0-9]+)?)\s*%",
            "cmax",
        ),
        (
            r"(auc0[-\s]?t|auc0[-\s]?inf|auc).{0,40}(?:cv|coefficient of variation|within[-\s]?subject cv|intra[-\s]?subject cv).{0,40}([0-9]{1,2}(?:\.[0-9]+)?)\s*%",
            "auc",
        ),
        (
            r"(within[-\s]?subject|intra[-\s]?subject).{0,40}cv.{0,40}([0-9]{1,2}(?:\.[0-9]+)?)\s*%",
            "any",
        ),
    ]

    for pat, kind in patterns:
        for m in re.finditer(pat, low):
            v = _norm_cv(_to_float(m.group(2)))
            if v is None:
                continue
            start = max(0, m.start() - 140)
            end = min(len(low), m.end() + 140)
            ctx = (text or "")[start:end]
            if kind == "cmax":
                out["cmax"].append((v, _clip(ctx, 220)))
            elif kind == "auc":
                out["auc"].append((v, _clip(ctx, 220)))
            else:
                out["cmax"].append((v, _clip(ctx, 220)))

    return out


class BEMiner:
    """
    Ищем BE исследования и извлекаем CV intra (Cmax/AUC) + типичные n/washout.
    """

    def __init__(self, tavily_key: str | None = None, cache_dir: str | None = None):
        tavily_key = tavily_key or os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            raise ValueError("TAVILY_API_KEY required")
        self.searcher = TavilyClient(api_key=tavily_key)

        base = Path(cache_dir or os.getenv("RAG_CACHE_DIR", "data/rag_cache"))
        self.cache_dir = base / "be_search"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.parser = PDFParser(cache_dir=str(base / "pdf_cache"))

        folder_id = os.getenv("YANDEX_FOLDER_ID")
        auth_key = os.getenv("YANDEX_AUTH_KEY")
        self.model = None
        if folder_id and auth_key:
            sdk = AIStudio(folder_id=folder_id, auth=auth_key)
            self.model = sdk.models.completions("yandexgpt").configure(temperature=0.2)

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

    def mine(self, inn: str, dosage: str, regimen: str, deadline_ts: float | None = None) -> Dict[str, Any]:
        def time_left() -> float:
            if deadline_ts is None:
                return 9999.0
            return deadline_ts - time.time()

        reg = regimen.lower()
        reg_q = "fasted" if "натощак" in reg else "fed" if "после" in reg else ""

        queries = [
            f"{inn} {dosage} bioequivalence within-subject CV Cmax AUC {reg_q}",
            f"{inn} {dosage} bioequivalence intra-subject variability coefficient of variation",
            f"{inn} {dosage} bioequivalence ANOVA within-subject variance Cmax AUC",
            f"{inn} {dosage} pharmacokinetics bioequivalence healthy volunteers Cmax AUC",
        ]

        excerpts: List[Dict[str, Any]] = []
        evidence_docs: List[Dict[str, Any]] = []
        html_docs: List[Dict[str, Any]] = []
        candidate_docs: List[Dict[str, Any]] = []
        discovered: List[Dict[str, Any]] = []

        max_pdf = 2
        max_html = 3

        for q in queries:
            if time_left() < 3.0:
                break
            data = self._search_cached(q, max_results=8)

            ans = (data.get("answer") or "").strip()
            if ans:
                excerpts.append({"title": f"Tavily summary: {q}", "uri": f"tavily://{_sha(q)[:12]}", "text": _clip(ans, 1400)})

            for r in data.get("results", []):
                if time_left() < 3.0:
                    break
                url = (r.get("url") or "").strip()
                if not url:
                    continue
                title = (r.get("title") or "").strip() or url
                if len(candidate_docs) < 10:
                    candidate_docs.append({"title": title, "uri": url})
                if len(discovered) < 12:
                    discovered.append({"title": title, "uri": url, "kind": "be_candidate"})

                raw = (r.get("raw") or r.get("raw_content") or r.get("content") or "").strip()
                if raw:
                    excerpts.append({"title": title, "uri": url, "text": _clip(raw, 8000)})

                if _is_pdf_url(url) and len(evidence_docs) < max_pdf and time_left() > 6.0:
                    try:
                        parsed = self.parser.parse(
                            url,
                            title=title,
                            uri=url,
                            keywords=[
                                "within-subject",
                                "intra-subject",
                                "cv",
                                "coefficient of variation",
                                "cmax",
                                "auc",
                                "bioequivalence",
                                "washout",
                                "subjects",
                            ],
                        )
                        excerpts.append({"title": title, "uri": url, "text": _clip(parsed.relevant_md, 12000)})
                        evidence_docs.append({"title": title, "uri": url, "sha256": parsed.sha256})
                    except Exception:
                        continue
                    continue

                if len(html_docs) < max_html and not _is_pdf_url(url) and time_left() > 4.0:
                    try:
                        txt = _fetch_html_text(url, timeout_s=10.0)
                        low = txt.lower()
                        if "cv" not in low and "coefficient of variation" not in low and "вариаб" not in low:
                            continue
                        if "cmax" not in low and "auc" not in low:
                            continue
                        excerpts.append({"title": title, "uri": url, "text": _clip(txt, 12000)})
                        html_docs.append({"title": title, "uri": url})
                    except Exception:
                        continue

            if len(evidence_docs) >= max_pdf and len(html_docs) >= max_html:
                break

        all_text = "\n\n".join([e["text"] for e in excerpts[:6]])
        cands = _extract_cv_candidates(all_text)

        cmax_guess = max([v for v, _ in cands["cmax"]], default=None)
        auc_guess = max([v for v, _ in cands["auc"]], default=None)

        result: Dict[str, Any] = {
            "cvintra": {"cmax": cmax_guess, "auc": auc_guess},
            "be_evidence": evidence_docs,
            "html_sources": html_docs,
            "evidence_docs": candidate_docs[:10],
            "discovered": discovered[:12],
            "excerpts_used": [{"title": e["title"], "uri": e["uri"]} for e in excerpts[:6]],
            "evidence": [],
            "typical": {},
            "notes": "CV извлечён из BE источников (PDF/HTML).",
        }

        if self.model and excerpts and (result["cvintra"]["cmax"] is None or result["cvintra"]["auc"] is None) and time_left() > 6.0:
            pack = "\n\n".join([f"=== {e['title']} ({e['uri']}) ===\n{e['text']}" for e in excerpts[:4]])
            prompt = f"""
Ты извлекаешь параметры из текстов по биоэквивалентности для {inn} {dosage}.
НЕ выдумывай.
Верни СТРОГО JSON:
{{
  "cvintra": {{"cmax": 0.24, "auc": 0.18}},
  "typical": {{"n_completed": 24, "washout_days": 7, "sampling_horizon_h": 72}},
  "evidence": [{{"title":"...","uri":"...","quote":"<=25 words","used_for":["cvintra.cmax"]}}]
}}
Если нет — null.
Текст:
{pack[:45000]}
"""
            llm = self.model.run(prompt)
            raw = llm.alternatives[0].text if llm and llm.alternatives else ""
            parsed = extract_json(raw) or {}
            if isinstance(parsed, dict):
                cv = parsed.get("cvintra")
                if isinstance(cv, dict):
                    if result["cvintra"]["cmax"] is None and cv.get("cmax") is not None:
                        result["cvintra"]["cmax"] = cv.get("cmax")
                    if result["cvintra"]["auc"] is None and cv.get("auc") is not None:
                        result["cvintra"]["auc"] = cv.get("auc")
                if isinstance(parsed.get("typical"), dict):
                    result["typical"] = parsed["typical"]
                if isinstance(parsed.get("evidence"), list):
                    result["evidence"] = parsed["evidence"]

        return result
