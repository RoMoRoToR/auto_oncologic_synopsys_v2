# packages/rag/src/extractor.py

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from yandex_ai_studio_sdk import AIStudio

from .json_utils import extract_json


@dataclass(frozen=True)
class Candidate:
    kind: str
    value: float
    unit: str
    context: str


def _to_float(s: str) -> Optional[float]:
    s = s.strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _norm_cv(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        v = float(x)
    else:
        t = str(x).strip().lower().replace("%", "")
        if not t:
            return None
        v = _to_float(t)
        if v is None:
            return None
    if v > 1.5:
        v = v / 100.0
    if v < 0 or v > 1:
        return None
    return v


def _norm_hours(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        v = float(x)
    else:
        t = str(x).strip().lower()
        if not t:
            return None
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(h|hr|hour|hours|ч|час|часа|часов|min|mins|minute|minutes|мин)", t)
        if m:
            num = _to_float(m.group(1))
            if num is None:
                return None
            unit = m.group(2)
            if unit in {"min", "mins", "minute", "minutes", "мин"}:
                v = num / 60.0
            else:
                v = num
        else:
            v = _to_float(t)
            if v is None:
                return None
    if v <= 0 or v > 500:
        return None
    return v


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _extract_regex_candidates(text: str) -> List[Candidate]:
    if not text:
        return []
    low = text.lower()
    out: List[Candidate] = []

    cv_patterns = [
        r"cv\s*(?:intra|within|intra-subject|within-subject)?\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        r"coefficient of variation\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        r"within-subject\s+cv\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*%",
    ]
    for pat in cv_patterns:
        for m in re.finditer(pat, low):
            val = _to_float(m.group(1))
            if val is None:
                continue
            cv = _norm_cv(val)
            if cv is None:
                continue
            ctx = text[max(0, m.start() - 120) : min(len(text), m.end() + 120)]
            out.append(Candidate(kind="cv", value=cv, unit="fraction", context=_clip(ctx, 360)))

    for m in re.finditer(r"tmax\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(h|hr|hours|hour|ч|час|мин|min|minutes|minute)", low):
        num = _to_float(m.group(1))
        if num is None:
            continue
        unit = m.group(2)
        hours = num / 60.0 if unit in {"мин", "min", "minutes", "minute"} else num
        hours = _norm_hours(hours)
        if hours is None:
            continue
        ctx = text[max(0, m.start() - 120) : min(len(text), m.end() + 120)]
        out.append(Candidate(kind="tmax_h", value=hours, unit="h", context=_clip(ctx, 360)))

    for m in re.finditer(r"(?:t1/2|t½|half[-\s]?life)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(h|hr|hours|hour|ч|час|мин|min|minutes|minute)", low):
        num = _to_float(m.group(1))
        if num is None:
            continue
        unit = m.group(2)
        hours = num / 60.0 if unit in {"мин", "min", "minutes", "minute"} else num
        hours = _norm_hours(hours)
        if hours is None:
            continue
        ctx = text[max(0, m.start() - 120) : min(len(text), m.end() + 120)]
        out.append(Candidate(kind="t12_h", value=hours, unit="h", context=_clip(ctx, 360)))

    return out


class YandexDataExtractor:
    """Извлечение сущностей из RAG-контекста через YandexGPT."""

    def __init__(self, folder_id: str, auth_key: str):
        sdk = AIStudio(folder_id=folder_id, auth=auth_key)
        self.model = sdk.models.completions("yandexgpt").configure(temperature=0.2)

    def extract_full_data(self, context: str, drug_name: str, dosage: str) -> Dict[str, Any]:
        cands = _extract_regex_candidates(context)
        cand_payload = [
            {
                "kind": c.kind,
                "value": c.value,
                "unit": c.unit,
                "context": c.context,
            }
            for c in cands[:30]
        ]

        prompt = f"""
Ты — эксперт по клинической фармакокинетике и биоэквивалентности.
Твоя задача: извлечь ЧИСЛОВЫЕ параметры (не придумывая) по препарату: {drug_name} {dosage}.

ПРАВИЛА:
1) Если значения нет в тексте — ставь null.
2) CVintra верни в виде ДОЛИ (например 0.24), а не процентов.
3) Время (Tmax, t1/2) верни в ЧАСАХ.
4) Обязательно верни evidence: массив объектов со ссылкой/названием и короткой цитатой (<= 25 слов),
   и полем used_for (какие поля из них подтверждаются).
5) Верни СТРОГО JSON. Никакого текста вне JSON.

СХЕМА JSON (типы строгие):
{{
  "cvintra": {{"cmax": 0.24, "auc": 0.18}},
  "pk": {{"tmax_h": 4.0, "t12_h": 19.0}},
  "sampling_horizon": 72,
  "confidence": {{"cvintra_cmax": "low|medium|high", "cvintra_auc": "low|medium|high", "tmax_h": "low|medium|high", "t12_h": "low|medium|high"}},
  "evidence": [
    {{"title": "...", "uri": "...", "year": 2019, "doi": "...", "quote": "...", "used_for": ["cvintra.cmax", "pk.t12_h"]}}
  ],
  "notes": "коротко: что найдено/не найдено"
}}

КАНДИДАТЫ (подсказка, могут быть ложными):
{cand_payload}

ФРАГМЕНТЫ:
{context[:45000]}
"""

        try:
            result = self.model.run(prompt)
            raw = result.alternatives[0].text if result and result.alternatives else ""
            parsed = extract_json(raw) or {}
            out = {
                "raw_response": raw,
                "inn": drug_name,
                "dosage": dosage,
                **parsed,
            }
            return self._postprocess(out)
        except Exception as e:
            return {"error": str(e), "inn": drug_name, "dosage": dosage}

    def _postprocess(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cvintra = data.get("cvintra") if isinstance(data.get("cvintra"), dict) else {}
        pk = data.get("pk") if isinstance(data.get("pk"), dict) else {}

        cmax = _norm_cv(cvintra.get("cmax"))
        auc = _norm_cv(cvintra.get("auc"))
        tmax = _norm_hours(pk.get("tmax_h"))
        t12 = _norm_hours(pk.get("t12_h"))

        data["cvintra"] = {"cmax": cmax, "auc": auc}
        data["pk"] = {"tmax_h": tmax, "t12_h": t12}

        horizon = data.get("sampling_horizon")
        try:
            horizon_i = int(horizon) if horizon is not None else None
        except Exception:
            horizon_i = None
        if horizon_i is None:
            horizon_i = 72
        if t12 is not None:
            horizon_i = max(horizon_i, int(round(4 * t12)))
        data["sampling_horizon"] = horizon_i

        ev = data.get("evidence")
        if not isinstance(ev, list):
            data["evidence"] = []
        else:
            cleaned: List[Dict[str, Any]] = []
            for item in ev:
                if isinstance(item, dict):
                    cleaned.append(
                        {
                            "title": str(item.get("title") or ""),
                            "uri": str(item.get("uri") or ""),
                            "year": item.get("year"),
                            "doi": str(item.get("doi") or ""),
                            "quote": str(item.get("quote") or "")[:220],
                            "used_for": item.get("used_for") if isinstance(item.get("used_for"), list) else [],
                        }
                    )
            data["evidence"] = cleaned

        return data
