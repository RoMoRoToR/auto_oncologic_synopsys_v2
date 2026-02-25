import base64
import re
import zipfile
from pathlib import Path
from typing import List, Dict, Tuple, Any

from src.json_utils import extract_json  # type: ignore


def _xml_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _inject_placeholders(xml: str) -> Tuple[str, List[str]]:
    placeholders: List[str] = []
    pos = 0
    out = []
    idx = 0
    while True:
        fidx = xml.find("FORMTEXT", pos)
        if fidx == -1:
            break
        t_start = xml.find("<w:t", fidx)
        if t_start == -1:
            break
        t_gt = xml.find(">", t_start)
        t_end = xml.find("</w:t>", t_gt)
        if t_gt == -1 or t_end == -1:
            break
        placeholder = f"__FIELD_{idx+1:03d}__"
        placeholders.append(placeholder)
        out.append(xml[pos:t_gt + 1])
        out.append(placeholder)
        pos = t_end
        idx += 1
    out.append(xml[pos:])
    return "".join(out), placeholders


def _extract_contexts(xml: str, placeholders: List[str]) -> List[Dict[str, str]]:
    contexts: List[Dict[str, str]] = []
    paras = re.findall(r"<w:p[\s\S]*?</w:p>", xml)
    for p in paras:
        texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", p)
        if not texts:
            continue
        line = "".join(texts)
        for ph in placeholders:
            if ph in line:
                contexts.append({"field": ph, "context": line.replace(ph, "<<VALUE>>")})
    return contexts


def _apply_values(xml: str, values: Dict[str, str]) -> str:
    for key, value in values.items():
        xml = xml.replace(key, _xml_escape(value))
    return xml


def build_field_contexts(template_path: Path) -> Tuple[str, List[str], List[Dict[str, str]]]:
    with zipfile.ZipFile(template_path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    xml_with_placeholders, placeholders = _inject_placeholders(xml)
    contexts = _extract_contexts(xml_with_placeholders, placeholders)
    return xml_with_placeholders, placeholders, contexts


def fill_template_docx(template_path: Path, field_values: Dict[str, str], extra_replacements: Dict[str, str] | None = None) -> bytes:
    with zipfile.ZipFile(template_path) as z:
        data = {name: z.read(name) for name in z.namelist()}
    xml = data["word/document.xml"].decode("utf-8", errors="ignore")
    xml_filled = _apply_values(xml, field_values)
    if extra_replacements:
        for key, value in extra_replacements.items():
            xml_filled = xml_filled.replace(key, _xml_escape(value))
    data["word/document.xml"] = xml_filled.encode("utf-8")

    out_path = template_path.parent / "_filled.tmp.docx"
    with zipfile.ZipFile(out_path, "w") as z:
        for name, content in data.items():
            z.writestr(name, content)
    result = out_path.read_bytes()
    out_path.unlink(missing_ok=True)
    return result


def parse_model_field_values(model_text: str, placeholders: List[str]) -> Dict[str, str]:
    parsed = extract_json(model_text) if model_text else None
    values: Dict[str, str] = {}
    if isinstance(parsed, list):
        for idx, ph in enumerate(placeholders):
            if idx < len(parsed):
                values[ph] = str(parsed[idx] or "")
    elif isinstance(parsed, dict):
        for ph in placeholders:
            if ph in parsed:
                values[ph] = str(parsed.get(ph) or "")
    return values


def encode_docx_base64(content: bytes) -> str:
    return base64.b64encode(content).decode("utf-8")


def suggest_field_values(
    contexts: List[Dict[str, str]],
    synopsis: Dict[str, Any],
    decision: Dict[str, Any],
    stats: Dict[str, Any],
    timeline: Dict[str, Any],
    inputs: Dict[str, Any],
) -> Dict[str, str]:
    inn = str(inputs.get("inn") or "")
    dosage = str(inputs.get("dosage") or "")
    form = str(inputs.get("form") or "")
    regimen = str(inputs.get("regimen") or "")

    def norm(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def v(key: str) -> str:
        return str(synopsis.get(key) or "")

    n_required = stats.get("n_required")
    n_screening = stats.get("n_screening")
    washout = decision.get("washout_days")
    timepoints = timeline.get("timepoints_h") if isinstance(timeline.get("timepoints_h"), list) else []
    tp_str = ", ".join(str(x) for x in timepoints[:30]) + ("…" if len(timepoints) > 30 else "")

    suggestions: Dict[str, str] = {}
    for item in contexts:
        ph = item.get("field", "")
        ctx = norm(item.get("context", ""))

        if not ph:
            continue

        if any(k in ctx for k in ["мнн", "inn", "международ", "действующее вещество", "active substance"]):
            suggestions[ph] = inn or v("activeSubstance")

        elif "дозиров" in ctx or "dose" in ctx:
            suggestions[ph] = dosage

        elif "лекарствен" in ctx or "dosage form" in ctx or ("форма" in ctx and "лекар" in ctx):
            suggestions[ph] = form

        elif "protocol id" in ctx or "номер протокола" in ctx:
            suggestions[ph] = v("protocolNumber")

        elif "название" in ctx or "title" in ctx:
            suggestions[ph] = v("protocolTitle")

        elif "дизайн" in ctx or "design" in ctx:
            suggestions[ph] = v("design")

        elif "washout" in ctx or "отмывк" in ctx or "период отмыв" in ctx:
            suggestions[ph] = f"{washout} дней" if washout else ""

        elif "период" in ctx and ("исследован" in ctx or "study" in ctx):
            suggestions[ph] = v("studyPeriods")

        elif ("число" in ctx or "количеств" in ctx or "n=" in ctx) and ("добров" in ctx or "subjects" in ctx or "участник" in ctx):
            if n_required:
                suggestions[ph] = str(n_required)

        elif ("скрининг" in ctx or "screen" in ctx) and ("число" in ctx or "n=" in ctx or "количеств" in ctx):
            if n_screening:
                suggestions[ph] = str(n_screening)

        elif "натощак" in ctx or "после еды" in ctx or "fed" in ctx or "fasted" in ctx:
            suggestions[ph] = regimen

        elif "точк" in ctx or "timepoint" in ctx or "отбор" in ctx or "sampling" in ctx:
            if tp_str:
                suggestions[ph] = tp_str

        elif "биоэквивал" in ctx or "80" in ctx or "125" in ctx or "be " in ctx:
            suggestions[ph] = v("beCriteria")

        elif "cmax" in ctx or "auc" in ctx or "pk" in ctx:
            suggestions[ph] = v("pkParameters")

        elif "расчет" in ctx and ("выборк" in ctx or "sample size" in ctx):
            suggestions[ph] = v("sampleSizeCalculation")

    return {k: val for k, val in suggestions.items() if str(val).strip()}
