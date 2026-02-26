from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from yandex_ai_studio_sdk import AIStudio

from .json_utils import extract_json


def _to_float(s: str) -> Optional[float]:
    s = s.strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _hours(num: float, unit: str) -> float:
    u = unit.lower()
    if u in ("мин", "мин.", "min", "mins", "minute", "minutes"):
        return num / 60.0
    return num


def _find_first(patterns: List[str], text: str) -> Optional[Tuple[float, str, str]]:
    low = text.lower()
    for pat in patterns:
        m = re.search(pat, low, flags=re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        num = _to_float(m.group(1))
        if num is None:
            continue
        unit = m.group(2)
        start = max(0, m.start() - 160)
        end = min(len(text), m.end() + 160)
        ctx = text[start:end].strip()
        return (num, unit, ctx)
    return None


def _extract_relevant(text: str, keywords: Optional[List[str]] = None, window: int = 700, max_chunks: int = 12, fallback_chars: int = 12000) -> str:
    if not text:
        return ""
    kws = [k.lower() for k in (keywords or [
        "tmax", "t1/2", "half-life", "cmax", "auc", "within-subject", "intra-subject", "cv",
        "период полувыведения", "время достижения максимальной концентрации", "коэффициент вариации",
    ])]
    low = text.lower()
    hits: List[int] = []
    for kw in kws:
        for m in re.finditer(re.escape(kw), low):
            hits.append(m.start())
    if not hits:
        return text[:fallback_chars]

    hits = sorted(set(hits))
    chunks: List[str] = []
    used: List[Tuple[int, int]] = []
    for pos in hits:
        if len(chunks) >= max_chunks:
            break
        start = max(0, pos - window)
        end = min(len(text), pos + window)
        rng = (start, end)
        if any(not (rng[1] <= r[0] or r[1] <= rng[0]) for r in used):
            continue
        used.append(rng)
        chunks.append(text[start:end].strip())
    return "\n\n".join([f"### EXCERPT {i+1}\n{c}" for i, c in enumerate(chunks)])

class LabelExtractor:
    """
    Из инструкции достаём Tmax и T1/2 (с regex, при необходимости fallback на LLM).
    """

    def __init__(self, use_llm_fallback: bool = True):
        self.use_llm_fallback = use_llm_fallback
        self.model = None
        if use_llm_fallback:
            folder_id = os.getenv("YANDEX_FOLDER_ID")
            auth_key = os.getenv("YANDEX_AUTH_KEY")
            if folder_id and auth_key:
                sdk = AIStudio(folder_id=folder_id, auth=auth_key)
                self.model = sdk.models.completions("yandexgpt").configure(temperature=0.1)

    def extract(self, md: str, source_title: str, source_url: str) -> Dict[str, Any]:
        text = md or ""

        tmax = _find_first(
            [
                r"tmax[^0-9]{0,30}([0-9]+(?:\.[0-9]+)?)\s*(ч|час|часа|часов|h|hr|hour|hours|min|mins|minute|minutes|мин)",
                r"время достижения максимальной концентрации[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)\s*(ч|час|часа|часов|h|hr|hour|hours|min|mins|minute|minutes|мин)",
            ],
            text,
        )

        t12 = _find_first(
            [
                r"(?:t1/2|t½|half[-\s]?life)[^0-9]{0,40}([0-9]+(?:\.[0-9]+)?)\s*(ч|час|часа|часов|h|hr|hour|hours|min|mins|minute|minutes|мин)",
                r"период полувыведения[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)\s*(ч|час|часа|часов|h|hr|hour|hours|min|mins|minute|minutes|мин)",
                r"период полуэлиминации[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)\s*(ч|час|часа|часов|h|hr|hour|hours|min|mins|minute|minutes|мин)",
            ],
            text,
        )

        out = {
            "pk": {"tmax_h": None, "t12_h": None},
            "cvintra": {"cmax": None, "auc": None},
            "from_instruction": True,
            "evidence": [],
        }

        if tmax:
            num, unit, ctx = tmax
            out["pk"]["tmax_h"] = round(_hours(num, unit), 3)
            out["evidence"].append(
                {"title": source_title, "uri": source_url, "used_for": ["pk.tmax_h"], "quote": ctx[:220]}
            )

        if t12:
            num, unit, ctx = t12
            out["pk"]["t12_h"] = round(_hours(num, unit), 3)
            out["evidence"].append(
                {"title": source_title, "uri": source_url, "used_for": ["pk.t12_h"], "quote": ctx[:220]}
            )

        if self.model and (out["pk"]["tmax_h"] is None or out["pk"]["t12_h"] is None):
            prompt = f"""
Ты извлекаешь PK из инструкции/SmPC. Ничего не выдумывай.
Верни СТРОГО JSON:
{{
  "pk": {{"tmax_h": 4.0, "t12_h": 19.0}},
  "evidence": [{{"used_for":["pk.tmax_h"],"quote":"<=25 words"}}]
}}
Если значения не найдены — null.
Текст:
{text[:25000]}
"""
            res = self.model.run(prompt)
            raw = res.alternatives[0].text if res and res.alternatives else ""
            parsed = extract_json(raw) or {}
            pk = parsed.get("pk") if isinstance(parsed, dict) else None
            if isinstance(pk, dict):
                if out["pk"]["tmax_h"] is None and pk.get("tmax_h") is not None:
                    out["pk"]["tmax_h"] = pk.get("tmax_h")
                if out["pk"]["t12_h"] is None and pk.get("t12_h") is not None:
                    out["pk"]["t12_h"] = pk.get("t12_h")

        return out

    def extract_from_texts(self, items: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        LLM fallback from multiple raw snippets (Tavily/HTML).
        items: [{title, uri, text}]
        """
        chunks = []
        for i in items[:4]:
            raw = i.get("text", "")
            rel = _extract_relevant(raw)
            chunks.append(f"=== {i.get('title','')} ({i.get('uri','')}) ===\n{rel}")
        text = "\n\n".join(chunks)

        out = {
            "pk": {"tmax_h": None, "t12_h": None},
            "cvintra": {"cmax": None, "auc": None},
            "from_instruction": False,
            "evidence": [],
        }

        if not self.model or not text.strip():
            return out

        prompt = f"""
Ты извлекаешь PK из фрагментов источников. Ничего не выдумывай.
Верни СТРОГО JSON:
{{
  "pk": {{"tmax_h": 4.0, "t12_h": 19.0}},
  "evidence": [{{"title":"...","uri":"...","quote":"<=25 words","used_for":["pk.tmax_h"]}}]
}}
Если значения не найдены — null.
Текст:
{text[:35000]}
"""
        res = self.model.run(prompt)
        raw = res.alternatives[0].text if res and res.alternatives else ""
        parsed = extract_json(raw) or {}
        if isinstance(parsed, dict):
            pk = parsed.get("pk")
            if isinstance(pk, dict):
                out["pk"]["tmax_h"] = pk.get("tmax_h")
                out["pk"]["t12_h"] = pk.get("t12_h")
            if isinstance(parsed.get("evidence"), list):
                out["evidence"] = parsed.get("evidence")
        return out

    def extract_pk_cv_from_texts(self, items: List[Dict[str, str]], sources: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """
        LLM fallback for PK + CV from multiple raw snippets.
        items: [{title, uri, text}]
        """
        chunks = []
        for i in items[:6]:
            raw = i.get("text", "")
            rel = _extract_relevant(raw)
            chunks.append(f"=== {i.get('title','')} ({i.get('uri','')}) ===\n{rel}")
        text = "\n\n".join(chunks)

        out = {
            "pk": {"tmax_h": None, "t12_h": None},
            "cvintra": {"cmax": None, "auc": None},
            "evidence": [],
            "filled_by_llm": False,
            "used_sources": [],
        }

        if not self.model or not text.strip():
            return out

        src_lines = []
        for s in (sources or [])[:20]:
            title = (s.get("title") or "").strip()
            uri = (s.get("uri") or "").strip()
            if title or uri:
                src_lines.append(f"- {title} — {uri}")

        prompt = f"""
Ты извлекаешь PK и CV из фрагментов источников. Ничего не выдумывай.
Верни СТРОГО JSON:
{{
  "pk": {{"tmax_h": 4.0, "t12_h": 19.0}},
  "cvintra": {{"cmax": 0.24, "auc": 0.18}},
  "evidence": [{{"title":"...","uri":"...","quote":"<=25 words","used_for":["pk.tmax_h"]}}]
}}
Если значения не найдены — null.
Список источников (для ссылок в evidence):
{chr(10).join(src_lines)}
Текст:
{text[:42000]}
"""
        res = self.model.run(prompt)
        raw = res.alternatives[0].text if res and res.alternatives else ""
        parsed = extract_json(raw) or {}
        if isinstance(parsed, dict):
            pk = parsed.get("pk")
            if isinstance(pk, dict):
                out["pk"]["tmax_h"] = pk.get("tmax_h")
                out["pk"]["t12_h"] = pk.get("t12_h")
            cv = parsed.get("cvintra")
            if isinstance(cv, dict):
                out["cvintra"]["cmax"] = cv.get("cmax")
                out["cvintra"]["auc"] = cv.get("auc")
            if isinstance(parsed.get("evidence"), list):
                out["evidence"] = parsed.get("evidence")

        has_quote = False
        used_sources = set()
        for ev in out.get("evidence", []):
            if not isinstance(ev, dict):
                continue
            quote = (ev.get("quote") or "").strip()
            if quote:
                has_quote = True
            uri = (ev.get("uri") or "").strip()
            if uri:
                used_sources.add(uri)

        # allow fill even without quotes, but mark quality
        out["filled_by_llm"] = True
        out["used_sources"] = sorted(used_sources)
        if not has_quote:
            out["llm_quality"] = "no_quotes"
            if not out.get("evidence") and sources:
                for s in sources[:5]:
                    out["evidence"].append(
                        {
                            "title": s.get("title", "Source"),
                            "uri": s.get("uri", ""),
                            "used_for": ["llm_fallback"],
                            "quote": "",
                        }
                    )
        return out
