import ast
import json
import re
from typing import Any, Dict, Optional


def _strip_code_fences(text: str) -> str:
    if not text:
        return ""
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _find_json_block(text: str) -> Optional[str]:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _soft_json_fixes(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    s = re.sub(r"\bNone\b", "null", s)

    s = re.sub(r"\bNaN\b", "null", s, flags=re.IGNORECASE)
    s = re.sub(r"\bInfinity\b", "null", s, flags=re.IGNORECASE)
    s = re.sub(r"\b-Infinity\b", "null", s, flags=re.IGNORECASE)

    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    cleaned = _strip_code_fences(text)
    candidates = [cleaned, _find_json_block(cleaned)]

    for cand in candidates:
        if not cand:
            continue
        cand = _soft_json_fixes(cand)
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        try:
            obj = ast.literal_eval(cand)
            if isinstance(obj, dict):
                return json.loads(json.dumps(obj, ensure_ascii=False))
        except Exception:
            pass

    return None
