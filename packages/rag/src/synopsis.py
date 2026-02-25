from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List, Optional

from yandex_ai_studio_sdk import AIStudio

from .json_utils import extract_json


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (int, float, bool)):
        return str(x)
    return str(x).strip()


_RU2LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _make_code(inn: str, default: str = "DRG") -> str:
    s = (inn or "").strip()
    if not s:
        return default
    out: List[str] = []
    for ch in s.lower():
        if "a" <= ch <= "z":
            out.append(ch)
        elif "а" <= ch <= "я" or ch == "ё":
            out.append(_RU2LAT.get(ch, ""))
    code = re.sub(r"[^a-z]", "", "".join(out)).upper()
    if len(code) < 3:
        code = (code + default)[:3]
    return code[:3]


def _pct(x: Optional[float]) -> str:
    if x is None:
        return ""
    try:
        v = float(x)
    except Exception:
        return ""
    if v <= 1.5:
        v = v * 100.0
    return f"{v:.0f}%"


def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v) for v in x if str(v).strip()]
    s = str(x).strip()
    if not s:
        return []
    return [s]


def _dict_to_yaml(d: Dict[str, Any], indent: int = 0) -> str:
    """Мини-YAML без внешних зависимостей (хватает для экспорта)."""
    lines: List[str] = []

    def emit(k: str, v: Any, ind: int):
        sp = "  " * ind
        if isinstance(v, dict):
            lines.append(f"{sp}{k}:")
            for kk, vv in v.items():
                emit(str(kk), vv, ind + 1)
        elif isinstance(v, list):
            lines.append(f"{sp}{k}:")
            for item in v:
                if isinstance(item, dict):
                    lines.append(f"{sp}  -")
                    for kk, vv in item.items():
                        emit(str(kk), vv, ind + 2)
                else:
                    lines.append(f"{sp}  - {str(item)}")
        else:
            val = "" if v is None else str(v)
            if any(c in val for c in [":", "#", "\n", "{", "}", "[", "]"]):
                val = json.dumps(val, ensure_ascii=False)
            lines.append(f"{sp}{k}: {val}")

    for k, v in d.items():
        emit(str(k), v, indent)
    return "\n".join(lines).strip() + "\n"


def _to_markdown(s: Dict[str, Any]) -> str:
    def h2(title: str) -> str:
        return f"## {title}\n"

    def para(text: str) -> str:
        t = (text or "").strip()
        return (t + "\n\n") if t else ""

    def bullets(items: List[str]) -> str:
        if not items:
            return ""
        out = []
        for it in items:
            t = str(it).strip()
            if t:
                out.append(f"- {t}")
        return ("\n".join(out) + "\n\n") if out else ""

    md = []
    md.append(f"# {s.get('protocolTitle','')}\n")
    md.append(f"**Protocol ID:** {s.get('protocolNumber','')}\n\n")

    md.append(h2("Цели"))
    md.append(para(s.get("objectives", "")))
    md.append(bullets(_as_list(s.get("tasks"))))

    md.append(h2("Дизайн"))
    md.append(para(s.get("design", "")))
    md.append(para(f"Периоды: {s.get('studyPeriods','')}"))
    md.append(para(f"Длительность: {s.get('duration','')}"))

    md.append(h2("Популяция"))
    md.append(para(s.get("population", "")))
    md.append("### Критерии включения\n")
    md.append(bullets(_as_list(s.get("inclusionCriteria"))))
    md.append("### Критерии исключения\n")
    md.append(bullets(_as_list(s.get("exclusionCriteria"))))

    md.append(h2("Режим дозирования"))
    md.append(para(f"Test: {s.get('testProductRegimen','')}"))
    md.append(para(f"Reference: {s.get('referenceProductRegimen','')}"))

    md.append(h2("Отбор проб и биоаналитика"))
    md.append(para(s.get("methodology", "")))
    md.append(para(f"Аналитический метод: {s.get('analyticalMethod','')}"))

    md.append(h2("Статистический анализ"))
    md.append(para(f"PK параметры: {s.get('pkParameters','')}"))
    md.append(para(f"Критерии БЭ: {s.get('beCriteria','')}"))
    md.append(para(f"Расчёт выборки: {s.get('sampleSizeCalculation','')}"))

    md.append(h2("Безопасность и этика"))
    md.append(para(s.get("safetyAnalysis", "")))
    md.append(para(s.get("ethicalAspects", "")))

    bib = s.get("bibliography") if isinstance(s.get("bibliography"), list) else []
    if bib:
        md.append(h2("Источники"))
        for b in bib[:20]:
            if isinstance(b, dict):
                title = (b.get("title") or "").strip()
                uri = (b.get("uri") or "").strip()
                if title and uri:
                    md.append(f"- {title} — {uri}\n")
                elif title:
                    md.append(f"- {title}\n")
            else:
                md.append(f"- {str(b)}\n")
        md.append("\n")

    return "".join(md).strip() + "\n"


class YandexSynopsisGenerator:
    """
    Нормальный (воспроизводимый) синопсис:
    - базовый JSON строим детерминированно (decision/stats/timeline фиксируют числа)
    - LLM используем только как "редактора формулировок" без права менять числа/дизайн
    """

    LOCKED_KEYS = {
        "protocolNumber",
        "activeSubstance",
        "dosageForm",
        "design",
        "studyPeriods",
        "sampleSizeCalculation",
        "pkParameters",
        "beCriteria",
        "versionDate",
    }

    def __init__(self, folder_id: str, auth_key: str):
        sdk = AIStudio(folder_id=folder_id, auth=auth_key)
        self.model = sdk.models.completions("yandexgpt").configure(temperature=0.2)

    def generate(self, params: Dict[str, Any], rag_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        base = self._build_base(params, rag_context or {})

        try:
            edited = self._llm_polish(base, rag_context or {})
            merged = self._merge_locked(base, edited)
        except Exception:
            merged = base

        merged["markdown"] = _to_markdown(merged)
        merged["yaml"] = _dict_to_yaml({k: merged.get(k) for k in merged.keys() if k != "markdown"})

        merged["tasks"] = _as_list(merged.get("tasks"))
        merged["inclusionCriteria"] = _as_list(merged.get("inclusionCriteria"))
        merged["exclusionCriteria"] = _as_list(merged.get("exclusionCriteria"))
        merged["withdrawalCriteria"] = _as_list(merged.get("withdrawalCriteria"))

        if not isinstance(merged.get("bibliography"), list):
            merged["bibliography"] = []

        return merged

    def _build_base(self, params: Dict[str, Any], rag_ctx: Dict[str, Any]) -> Dict[str, Any]:
        inn = _safe_str(params.get("inn"))
        form = _safe_str(params.get("form"))
        dosage = _safe_str(params.get("dosage"))
        regimen = _safe_str(params.get("regimen"))
        study_type = _safe_str(params.get("studyType"))
        constraints = _safe_str(params.get("constraints"))

        decision = rag_ctx.get("decision") or {}
        stats = rag_ctx.get("stats") or {}
        timeline = rag_ctx.get("timeline") or {}
        rag_summary = rag_ctx.get("ragSummary") or {}
        rag = rag_ctx.get("rag") or {}

        code = _make_code(inn)
        today = date.today().isoformat()

        design_code = decision.get("design") or _safe_str(params.get("design")) or "2x2"
        washout_days = decision.get("washout_days")
        periods = decision.get("periods")
        sequences = decision.get("sequences")

        if design_code == "replicate":
            design_text = (
                "Рандомизированное, открытое, перекрёстное исследование с повторным введением "
                "(replicate design). Применимо при высокой внутрииндивидуальной вариабельности и/или RSABE."
            )
        elif design_code in {"2x2", "2×2"}:
            design_text = (
                "Рандомизированное, открытое, двухпериодное, двухпоследовательностное перекрёстное "
                "исследование (2×2 cross-over)."
            )
        else:
            design_text = _safe_str(design_code)

        wash = f"{washout_days} дней" if washout_days else "не задан"
        study_periods = f"{periods or ''} период(а/ов), {sequences or ''} последовательности(ей), washout {wash}".strip(", ").strip()

        n_required = stats.get("n_required")
        n_screening = stats.get("n_screening")
        cv_used = stats.get("assumptions", {}).get("cv_intra")
        alpha = stats.get("assumptions", {}).get("alpha", 0.05)
        power = stats.get("assumptions", {}).get("power", 0.8)

        sample_calc = (
            f"Расчёт выполнен для 90% ДИ (α={alpha}) и мощности {int(round(power*100))}%. "
            f"Использован CVintra={_pct(cv_used) or '—'}. "
            f"Требуется завершивших: {n_required or '—'}; к скринингу: {n_screening or '—'} "
            f"(с учётом drop-out/screen-fail из входных параметров)."
        )

        tmax = rag_summary.get("tmax_h")
        t12 = rag_summary.get("t12_h")
        horizon = timeline.get("sampling_horizon_h")
        tpoints = timeline.get("timepoints_h") if isinstance(timeline.get("timepoints_h"), list) else []
        tpoints_str = ", ".join([str(x) for x in tpoints[:30]]) + ("…" if len(tpoints) > 30 else "")

        methodology = (
            f"Отбор проб крови проводится в каждом периоде до {horizon or '—'} ч после дозирования "
            f"(плотнее вокруг Tmax={tmax if tmax is not None else '—'} ч; t1/2={t12 if t12 is not None else '—'} ч). "
            f"Предлагаемая сетка точек (ч): {tpoints_str}."
        )

        objectives = (
            f"Оценить биоэквивалентность тестируемого и референтного препаратов {inn} "
            f"по параметрам Cmax и AUC при приёме {regimen.lower() if regimen else 'в заданных условиях'}."
        )

        tasks = [
            "Сравнить Cmax и AUC0-t (и при возможности AUC0-∞) после лог-трансформации.",
            "Оценить Tmax описательно.",
            "Оценить безопасность и переносимость (НЯ, жизненные показатели, лабораторные показатели).",
        ]

        population = "Здоровые добровольцы (мужчины и/или женщины) согласно критериям включения/исключения."
        if constraints:
            population += f" Дополнительные ограничения: {constraints}"

        inclusion = [
            "Подписанное информированное согласие.",
            "Возраст 18–55 лет.",
            "ИМТ 18.5–30.0 кг/м².",
            "Отсутствие клинически значимых отклонений по обследованиям и анализам.",
        ]
        exclusion = [
            "Гиперчувствительность к действующему веществу или компонентам препарата.",
            "Приём лекарств, влияющих на фармакокинетику, в период скрининга/отмывки.",
            "Значимые хронические заболевания (печени, почек, ССС и др.).",
            "Участие в другом клиническом исследовании в последние 3 месяца.",
        ]
        withdrawal = [
            "Добровольный отказ участника.",
            "Развитие нежелательных явлений, требующих вывода из исследования.",
            "Нарушение протокола, влияющее на интерпретацию результатов.",
        ]

        water_ml = 240
        dose_str = dosage if dosage else "—"
        dose_form = f"{form}, {dose_str} мг".strip().strip(",")

        test_reg = f"Однократный приём тестируемого препарата {dose_str} мг {regimen.lower() if regimen else ''} с {water_ml} мл воды."
        ref_reg = f"Однократный приём референтного препарата {dose_str} мг {regimen.lower() if regimen else ''} с {water_ml} мл воды."

        pk_params = "Cmax, AUC0-t, AUC0-∞ (при наличии), Tmax (описательно)"
        be_criteria = "90% ДИ для отношения геометрических средних (T/R) по ln(Cmax) и ln(AUC0-t) в пределах 80.00–125.00%."

        analytical = "Валидационный биоаналитический метод LC-MS/MS для определения концентраций действующего вещества в плазме."
        safety = "Оценка НЯ/СНЯ, физикальные осмотры, жизненные показатели, ЭКГ, клинические и биохимические анализы крови/мочи."
        ethics = "Исследование проводится в соответствии с GCP, Хельсинкской декларацией и локальными требованиями. Обязательно информированное согласие."

        bibliography: List[Dict[str, str]] = []
        seen = set()

        def add_source(title: str, uri: str, used_for: str = "", confidence: str = "") -> None:
            key = (title.strip().lower(), uri.strip().lower())
            if key in seen:
                return
            seen.add(key)
            bibliography.append(
                {
                    "title": title.strip() or "Источник",
                    "uri": uri.strip(),
                    "used_for": used_for.strip(),
                    "confidence": confidence.strip(),
                }
            )

        if isinstance(rag.get("evidence"), list):
            for ev in rag["evidence"][:40]:
                if isinstance(ev, dict):
                    add_source(
                        _safe_str(ev.get("title")),
                        _safe_str(ev.get("uri")),
                        _safe_str(ev.get("used_for")),
                        _safe_str(ev.get("confidence")),
                    )

        be = rag.get("be") or {}
        if isinstance(be.get("be_evidence"), list):
            for ev in be["be_evidence"][:20]:
                if isinstance(ev, dict):
                    add_source(_safe_str(ev.get("title")), _safe_str(ev.get("uri")), "be_source", "")
        if isinstance(be.get("html_sources"), list):
            for ev in be["html_sources"][:20]:
                if isinstance(ev, dict):
                    add_source(_safe_str(ev.get("title")), _safe_str(ev.get("uri")), "be_html", "")
        if isinstance(be.get("excerpts_used"), list):
            for ev in be["excerpts_used"][:20]:
                if isinstance(ev, dict):
                    add_source(_safe_str(ev.get("title")), _safe_str(ev.get("uri")), "be_excerpt", "")

        label = rag.get("label") or {}
        if isinstance(label, dict) and (label.get("title") or label.get("url")):
            add_source(_safe_str(label.get("title")), _safe_str(label.get("url")), "instruction", "")

        if not bibliography and isinstance(rag.get("evidence_docs"), list):
            for ev in rag["evidence_docs"][:20]:
                if isinstance(ev, dict):
                    add_source(_safe_str(ev.get("title")), _safe_str(ev.get("uri")), "evidence_doc", "")

        protocol_title = f"Синопсис протокола исследования биоэквивалентности: {inn} {dose_str} мг ({regimen.lower() if regimen else 'условия не указаны'})"

        return {
            "protocolTitle": protocol_title,
            "protocolNumber": f"BE-{code}-2026",
            "sponsor": "",
            "clinicalCenter": "",
            "bioanalyticalLab": "",
            "clinicalPhase": "I",
            "investigationalProduct": f"Тестируемый препарат {inn} {dose_str} мг",
            "activeSubstance": inn,
            "dosageForm": dose_form,
            "objectives": objectives,
            "tasks": tasks,
            "design": design_text,
            "methodology": methodology,
            "population": population,
            "inclusionCriteria": inclusion,
            "exclusionCriteria": exclusion,
            "withdrawalCriteria": withdrawal,
            "testProductRegimen": test_reg.strip(),
            "referenceProductRegimen": ref_reg.strip(),
            "studyPeriods": study_periods,
            "duration": "Скрининг до 28 дней; периоды согласно дизайну; финальный визит после завершения отбора проб.",
            "pkParameters": pk_params,
            "analyticalMethod": analytical,
            "beCriteria": be_criteria,
            "safetyAnalysis": safety,
            "sampleSizeCalculation": sample_calc,
            "randomization": "Рандомизация 1:1 по последовательностям (TR/RT) блоками; распределение фиксируется в системе.",
            "ethicalAspects": ethics,
            "versionDate": today,
            "markdown": "",
            "yaml": "",
            "bibliography": bibliography,
            "studyType": study_type,
        }

    def _llm_polish(self, base: Dict[str, Any], rag_ctx: Dict[str, Any]) -> Dict[str, Any]:
        rag = rag_ctx.get("rag") or {}
        rag_summary = rag_ctx.get("ragSummary") or {}
        decision = rag_ctx.get("decision") or {}
        stats = rag_ctx.get("stats") or {}
        timeline = rag_ctx.get("timeline") or {}

        evidence = rag.get("evidence") if isinstance(rag.get("evidence"), list) else []
        ev_compact = []
        for ev in evidence[:8]:
            if isinstance(ev, dict):
                ev_compact.append(
                    {
                        "title": ev.get("title"),
                        "uri": ev.get("uri"),
                        "quote": ev.get("quote"),
                        "used_for": ev.get("used_for"),
                    }
                )

        prompt = f"""
Ты — редактор синопсиса протокола биоэквивалентности. Улучши формулировки.
ВАЖНО:
- НЕ МЕНЯЙ числовые значения, дизайн, расчёт выборки, таймпоинты, критерии БЭ.
- НЕ ДОБАВЛЯЙ факты.
- Если чего-то нет — оставь как есть.

Верни СТРОГО JSON с ТЕМИ ЖЕ ключами, что и в base.

Контекст:
rag_summary={json.dumps(rag_summary, ensure_ascii=False)}
decision={json.dumps(decision, ensure_ascii=False)}
stats={json.dumps(stats, ensure_ascii=False)}
timeline={json.dumps(timeline, ensure_ascii=False)}
evidence={json.dumps(ev_compact, ensure_ascii=False)}

BASE:
{json.dumps(base, ensure_ascii=False)}
"""
        result = self.model.run(prompt)
        text = result.alternatives[0].text if result and result.alternatives else ""
        parsed = extract_json(text) or {}
        return parsed if isinstance(parsed, dict) else {}

    def _merge_locked(self, base: Dict[str, Any], edited: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        if not edited:
            return merged
        for k, v in edited.items():
            if k in self.LOCKED_KEYS:
                continue
            merged[k] = v
        for k in self.LOCKED_KEYS:
            merged[k] = base.get(k)
        return merged
