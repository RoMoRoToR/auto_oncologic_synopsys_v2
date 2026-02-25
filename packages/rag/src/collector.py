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
        }

        if not skip_instruction and trade and time_left() > 2.0:
            instr_pack = self.instruction_finder.find_instruction(
                trade_name=trade,
                dosage=dosage,
                dosage_form=dosage_form,
                deadline_ts=deadline_ts,
                source_path=source_path,
            )
            out["evidence_docs"].extend(instr_pack.get("evidence_docs", []))
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

        if not skip_be and time_left() > 2.0:
            be = self.be_miner.mine(inn=drug_inn, dosage=dosage, regimen=regimen, deadline_ts=deadline_ts)
            out["be"] = be
            out["evidence_docs"].extend(be.get("discovered", []))

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

        out["notes"] = {
            "pk_source": "instruction" if out["pk"]["tmax_h"] is not None or out["pk"]["t12_h"] is not None else "none",
            "cv_source": "be_studies" if (out["cvintra"]["cmax"] is not None or out["cvintra"]["auc"] is not None) else "none",
        }
        return out
