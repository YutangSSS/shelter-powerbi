"""Static checks on the Power BI semantic model (TMDL). Power BI Desktop is not available in CI, so this
checks what can be checked: every column the model reads, relates or measures exists in the export."""
import re
from pathlib import Path

from shelter.export import export

DEF = Path(__file__).resolve().parent.parent / "ShelterReporting.SemanticModel" / "definition"


def _model_columns():
    cols = {}
    for f in (DEF / "tables").glob("*.tmdl"):
        text = f.read_text()
        cols[re.search(r"^table (\w+)", text, re.M).group(1)] = set(re.findall(r"^\tcolumn (\w+)", text, re.M))
    return cols


def test_model_columns_match_exported_csvs(con, tmp_path):
    export(con, tmp_path)
    for table, cols in _model_columns().items():
        if table == "Measures":
            continue
        header = (tmp_path / f"{table}.csv").read_text().splitlines()[0].split(",")
        assert cols == set(header), table


def test_relationships_and_measures_reference_real_columns():
    cols = _model_columns()
    rel = (DEF / "relationships.tmdl").read_text()
    for t, c in re.findall(r"(?:from|to)Column: (\w+)\.(\w+)", rel):
        assert c in cols[t], f"{t}.{c}"
    measures = (DEF / "tables" / "Measures.tmdl").read_text()
    for t, c in re.findall(r"\b(\w+)\[(\w+)\]", measures):
        assert c in cols[t], f"{t}[{c}]"
    for ref in re.findall(r"(?<![\w\]])\[([^\]]+)\]", measures):
        assert f"measure '{ref}'" in measures or ref == "x", ref
    assert set(re.findall(r"^ref table (\w+)", (DEF / "model.tmdl").read_text(), re.M)) == set(cols)
