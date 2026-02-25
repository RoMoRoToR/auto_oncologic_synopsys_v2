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
