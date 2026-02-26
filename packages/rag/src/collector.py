import os
import time
from typing import Any, Dict

from .reference_resolver import ReferenceResolver
from .instruction_finder import InstructionFinder
from .label_extractor import LabelExtractor
from .be_miner import BEMiner


class DrugDataCollector:
    def __init__(self, tavily_key: str | None = None, grls_xlsx_path: str | None = None):
        self.resolver = ReferenceResolver(xlsx_path=grls_xlsx_path or os.getenv("GRLS_XLSX_PATH", "data/grls.xlsx"))
        self.instruction_finder = InstructionFinder(tavily_key=tavily_key)
        self.label_extractor = LabelExtractor(use_llm_fallback=True)
        self.be_miner = BEMiner(tavily_key=tavily_key)

    def get_drug_info(
        self,
        drug_inn: str,
        dosage: str,
        dosage_form: str,
        regimen: str,
        reference_trade_name: str | None = None,
        skip_be: bool = False,
        skip_instruction: bool = False,
        deadline_ts: float | None = None,
        source_path: str | None = None,
        deep_mode: bool = False,
        progress_cb=None,
    ) -> Dict[str, Any]:
        def time_left() -> float:
            if deadline_ts is None:
                return 9999.0
            return deadline_ts - time.time()

        ref = self.resolver.find_reference_options(inn=drug_inn, dosage=dosage, dosage_form=dosage_form, limit=10)
        default_trade = ref.get("default_trade_name") or ""
        trade = (reference_trade_name or "").strip() or default_trade

        out: Dict[str, Any] = {
            "reference": {
                "inn": drug_inn,
                "dosage": dosage,
                "dosage_form": dosage_form,
                "regimen": regimen,
                "trade_name": trade,
                "options": ref.get("options", []),
            },
            "pk": {"tmax_h": None, "t12_h": None},
            "cvintra": {"cmax": None, "auc": None},
            "evidence": [],
            "evidence_docs": [],
            "warnings": [],
            "label": {},
            "be": {},
            "search_queries": [],
        }
        if deep_mode and os.getenv("DOCLING_ENABLED", "0") != "1":
            out["warnings"].append("Deep OCR включён, но DOCLING_ENABLED=0 (OCR пропущен)")

        if progress_cb:
            progress_cb("discover", 0.5, "Поиск источников", None)

        raw_hits = []
        if not skip_instruction and trade and time_left() > 2.0:
            if progress_cb:
                progress_cb("instruction", 0.6, "Поиск инструкции", None)
            instr_pack = self.instruction_finder.find_instruction(
                trade_name=trade,
                dosage=dosage,
                dosage_form=dosage_form,
                deadline_ts=deadline_ts,
                source_path=source_path,
                deep_mode=deep_mode,
            )
            out["evidence_docs"].extend(instr_pack.get("evidence_docs", []))
            if instr_pack.get("queries"):
                out["search_queries"].extend(instr_pack.get("queries", []))
            raw_hits = instr_pack.get("raw_hits") or []
            instr = instr_pack.get("doc")
            if instr:
                label = self.label_extractor.extract(instr.relevant_md, source_title=instr.title, source_url=instr.url)
                out["label"] = {"title": instr.title, "url": instr.url, "sha256": instr.sha256, "extracted": label}
                if label.get("pk", {}).get("tmax_h") is not None:
                    out["pk"]["tmax_h"] = label["pk"]["tmax_h"]
                if label.get("pk", {}).get("t12_h") is not None:
                    out["pk"]["t12_h"] = label["pk"]["t12_h"]
                out["evidence"].extend(label.get("evidence", []))
            else:
                out["warnings"].append("Инструкция/SmPC не извлечена: использованы только ссылки")

            # LLM fallback on raw snippets if PK still missing
            if (out["pk"]["tmax_h"] is None or out["pk"]["t12_h"] is None) and raw_hits:
                if progress_cb:
                    progress_cb("llm", 0.68, "LLM извлечение PK", None)
                llm_pk = self.label_extractor.extract_from_texts(raw_hits)
                if out["pk"]["tmax_h"] is None and llm_pk.get("pk", {}).get("tmax_h") is not None:
                    out["pk"]["tmax_h"] = llm_pk["pk"]["tmax_h"]
                if out["pk"]["t12_h"] is None and llm_pk.get("pk", {}).get("t12_h") is not None:
                    out["pk"]["t12_h"] = llm_pk["pk"]["t12_h"]
                if isinstance(llm_pk.get("evidence"), list):
                    out["evidence"].extend(llm_pk["evidence"])

        be_raw_hits = []
        if not skip_be and time_left() > 2.0:
            if progress_cb:
                progress_cb("be", 0.72, "Поиск BE источников", None)
            be = self.be_miner.mine(
                inn=drug_inn,
                dosage=dosage,
                regimen=regimen,
                deadline_ts=deadline_ts,
                deep_mode=deep_mode,
            )
            out["be"] = be
            out["evidence_docs"].extend(be.get("discovered", []))
            if be.get("queries"):
                out["search_queries"].extend(be.get("queries", []))
            be_raw_hits = be.get("raw_hits") if isinstance(be, dict) else []

            cv = be.get("cvintra", {}) if isinstance(be.get("cvintra"), dict) else {}
            if cv.get("cmax") is not None:
                out["cvintra"]["cmax"] = cv.get("cmax")
            if cv.get("auc") is not None:
                out["cvintra"]["auc"] = cv.get("auc")

            if isinstance(be.get("evidence"), list):
                out["evidence"].extend(be["evidence"])
        elif skip_be:
            out["be"] = {"skipped": True, "reason": "cv provided by user"}

        if not out["evidence_docs"]:
            out["warnings"].append("Источники не найдены: проверьте запрос/МНН/дозу или сеть")
            out["evidence_docs"] = [{"title": f"Search: {drug_inn} {dosage}", "uri": f"search://{drug_inn}"}]

        # final LLM fallback: fill missing pk/cv from all raw hits
        missing_pk = out["pk"]["tmax_h"] is None or out["pk"]["t12_h"] is None
        missing_cv = out["cvintra"]["cmax"] is None or out["cvintra"]["auc"] is None
        if (missing_pk or missing_cv) and self.label_extractor.model:
            if progress_cb:
                progress_cb("llm", 0.78, "LLM извлечение PK/CV", None)
            all_hits = []
            if raw_hits:
                all_hits.extend(raw_hits)
            if isinstance(be_raw_hits, list):
                all_hits.extend(be_raw_hits)
            if all_hits:
                llm_all = self.label_extractor.extract_pk_cv_from_texts(all_hits, sources=out.get("evidence_docs", []))
                if out["pk"]["tmax_h"] is None and llm_all.get("pk", {}).get("tmax_h") is not None:
                    out["pk"]["tmax_h"] = llm_all["pk"]["tmax_h"]
                if out["pk"]["t12_h"] is None and llm_all.get("pk", {}).get("t12_h") is not None:
                    out["pk"]["t12_h"] = llm_all["pk"]["t12_h"]
                if out["cvintra"]["cmax"] is None and llm_all.get("cvintra", {}).get("cmax") is not None:
                    out["cvintra"]["cmax"] = llm_all["cvintra"]["cmax"]
                if out["cvintra"]["auc"] is None and llm_all.get("cvintra", {}).get("auc") is not None:
                    out["cvintra"]["auc"] = llm_all["cvintra"]["auc"]
                if llm_all.get("filled_by_llm"):
                    out.setdefault("notes", {})
                    out["notes"]["filled_by_llm"] = True
                    if isinstance(llm_all.get("used_sources"), list):
                        out["notes"]["llm_used_sources"] = llm_all.get("used_sources")
                    if llm_all.get("llm_quality"):
                        out["notes"]["llm_quality"] = llm_all.get("llm_quality")
                if isinstance(llm_all.get("evidence"), list) and llm_all.get("filled_by_llm"):
                    out["evidence"].extend(llm_all["evidence"])

        # ensure evidence is non-empty if any sources exist
        if not out["evidence"] and out.get("evidence_docs"):
            for ev in out.get("evidence_docs", [])[:5]:
                if isinstance(ev, dict):
                    out["evidence"].append(
                        {
                            "title": ev.get("title", "Source"),
                            "uri": ev.get("uri", ""),
                            "used_for": ["evidence_doc"],
                            "quote": "",
                        }
                    )

        out["notes"] = {
            "pk_source": "instruction" if out["pk"]["tmax_h"] is not None or out["pk"]["t12_h"] is not None else "none",
            "cv_source": "be_studies" if (out["cvintra"]["cmax"] is not None or out["cvintra"]["auc"] is not None) else "none",
        }
        return out
