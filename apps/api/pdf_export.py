from __future__ import annotations

import io
import os
from typing import Any, Dict, List

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, Table, TableStyle
from reportlab.lib import colors

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def _register_cyrillic_font() -> str:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/ttf-dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont("CyrFont", p))
                return "CyrFont"
            except Exception:
                continue
    return "Helvetica"


def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v) for v in x if str(v).strip()]
    s = str(x).strip()
    return [s] if s else []


def make_synopsis_pdf(
    synopsis: Dict[str, Any],
    decision: Dict[str, Any] | None = None,
    stats: Dict[str, Any] | None = None,
    timeline: Dict[str, Any] | None = None,
    rag_summary: Dict[str, Any] | None = None,
) -> bytes:
    decision = decision or {}
    stats = stats or {}
    timeline = timeline or {}
    rag_summary = rag_summary or {}

    font_name = _register_cyrillic_font()
    styles = getSampleStyleSheet()

    base = ParagraphStyle(
        "Base",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10.5,
        leading=14,
        spaceAfter=6,
    )
    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=16,
        leading=20,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12.5,
        leading=16,
        spaceAfter=8,
    )
    small = ParagraphStyle(
        "Small",
        parent=base,
        fontName=font_name,
        fontSize=9.5,
        leading=12,
        textColor=colors.grey,
        spaceAfter=6,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=str(synopsis.get("protocolTitle") or "Synopsis"),
    )

    story: List[Any] = []
    story.append(Paragraph(str(synopsis.get("protocolTitle") or "Синопсис протокола"), h1))
    story.append(Paragraph(f"Protocol ID: <b>{synopsis.get('protocolNumber','')}</b>", base))
    story.append(Spacer(1, 6))

    meta_rows = [
        ["МНН", synopsis.get("activeSubstance", "")],
        ["Лекарственная форма", synopsis.get("dosageForm", "")],
        ["Тип", (synopsis.get("studyType", "") or "")],
        ["Дизайн", synopsis.get("design", "")],
        ["Периоды", synopsis.get("studyPeriods", "")],
    ]
    t = Table(meta_rows, colWidths=[42 * mm, 130 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), font_name, 9.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 10))

    def section(title: str):
        story.append(Paragraph(title, h2))

    def p(text: str):
        if text and str(text).strip():
            story.append(Paragraph(str(text), base))

    def bullets(items: List[str]):
        if not items:
            return
        lst = ListFlowable(
            [ListItem(Paragraph(str(it), base), leftIndent=12) for it in items],
            bulletType="bullet",
            start="circle",
            leftIndent=12,
        )
        story.append(lst)
        story.append(Spacer(1, 6))

    section("Цели и задачи")
    p(synopsis.get("objectives", ""))
    bullets(_as_list(synopsis.get("tasks")))

    section("Популяция")
    p(synopsis.get("population", ""))
    p("<b>Критерии включения:</b>")
    bullets(_as_list(synopsis.get("inclusionCriteria")))
    p("<b>Критерии исключения:</b>")
    bullets(_as_list(synopsis.get("exclusionCriteria")))

    section("Режим дозирования")
    p(f"<b>Test:</b> {synopsis.get('testProductRegimen','')}")
    p(f"<b>Reference:</b> {synopsis.get('referenceProductRegimen','')}")

    section("Отбор проб и биоаналитика")
    p(synopsis.get("methodology", ""))
    p(f"<b>Аналитический метод:</b> {synopsis.get('analyticalMethod','')}")

    tps = timeline.get("timepoints_h") if isinstance(timeline.get("timepoints_h"), list) else []
    if tps:
        p(f"<b>Таймпоинты (ч):</b> {', '.join(str(x) for x in tps[:40])}{'…' if len(tps) > 40 else ''}")

    section("Статистика и биоэквивалентность")
    p(f"<b>PK параметры:</b> {synopsis.get('pkParameters','')}")
    p(f"<b>Критерий БЭ:</b> {synopsis.get('beCriteria','')}")
    p(f"<b>Расчёт выборки:</b> {synopsis.get('sampleSizeCalculation','')}")

    section("Безопасность и этика")
    p(synopsis.get("safetyAnalysis", ""))
    p(synopsis.get("ethicalAspects", ""))

    if synopsis.get("evidenceSummary"):
        section("Источники и обоснование")
        p(synopsis.get("evidenceSummary", ""))

    bib = synopsis.get("bibliography") if isinstance(synopsis.get("bibliography"), list) else []
    if bib:
        section("Источники")
        items = []
        for b in bib:
            if isinstance(b, dict):
                title = (b.get("title") or "").strip()
                uri = (b.get("uri") or "").strip()
                if title and uri:
                    items.append(f"{title} — {uri}")
                elif title:
                    items.append(title)
            else:
                items.append(str(b))
        bullets(items)

    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Примечание: документ сформирован автоматически и требует экспертной валидации перед регуляторным использованием.",
            small,
        )
    )

    doc.build(story)
    return buf.getvalue()
