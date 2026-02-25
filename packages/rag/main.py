import os
import json

from src.config import Config
from src.collector import DrugDataCollector


def main() -> None:
    Config.setup_windows_env()

    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        raise ValueError("TAVILY_API_KEY environment variable is required")

    collector = DrugDataCollector(tavily_key=tavily_key)

    sample = {
        "inn": "Rosuvastatin",
        "dosage": "20 mg",
        "form": "таблетки",
        "regimen": "натощак",
    }

    result = collector.get_drug_info(
        drug_inn=sample["inn"],
        dosage=sample["dosage"],
        dosage_form=sample["form"],
        regimen=sample["regimen"],
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
