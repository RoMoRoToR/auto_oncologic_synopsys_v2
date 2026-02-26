import tempfile

import openpyxl

from src.reference_resolver import ReferenceResolver


def _make_xlsx(path: str):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Действующий"
    # header rows
    for _ in range(5):
        ws.append([""] * 11)
    # data row (columns C..K)
    # C=reg_no, D=reg_date, I=trade, J=inn, K=forms
    row = ["", "", "RU-123", "01.01.2020", "", "", "", "", "Crestor", "Rosuvastatin", "таблетки 20 мг"]
    ws.append(row)
    wb.save(path)


def test_reference_resolver_basic():
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
        _make_xlsx(tmp.name)
        resolver = ReferenceResolver(xlsx_path=tmp.name)
        res = resolver.find_reference_options(inn="Rosuvastatin", dosage="20 mg", dosage_form="таблетки", limit=5)
        assert res["options"]
        assert res["options"][0]["trade_name"] == "Crestor"
