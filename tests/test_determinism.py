import json
import os

import pandas as pd

from tabulous import generate

BASE_SPEC = {
    "n_rows": 200,
    "seed": 42,
    "columns": [
        {"name": "student_id", "type": "id", "prefix": "S", "padding": 4},
        {"name": "age", "type": "int", "min": 18, "max": 35,
         "messiness": {"missing": 0.05, "out_of_range": 0.02}},
        {"name": "height_cm", "type": "float", "min": 150, "max": 200, "decimals": 1, "unit": "cm",
         "messiness": {"missing": 0.03, "unit_suffix": 0.05}},
        {"name": "grade", "type": "choice", "options": ["A", "B", "C", "D", "F"],
         "messiness": {"missing": 0.04, "case_variation": 0.05, "whitespace": 0.03, "typo": 0.02}},
        {"name": "enrolled", "type": "choice", "options": ["true", "false"],
         "messiness": {"inconsistent_encoding": 0.10}},
        {"name": "email", "type": "string", "pattern": "{first}.{last}@school.edu",
         "messiness": {"missing": 0.02, "duplicates": 0.10}},
        {"name": "joined", "type": "date", "start": "2023-01-01", "end": "2024-12-31",
         "messiness": {"missing": 0.05}},
    ],
    "row_messiness": {"duplicate_rows": 0.02},
}


def _export(result, out):
    os.makedirs(out, exist_ok=True)
    result.messy.to_csv(os.path.join(out, "messy.csv"), index=False)
    result.clean.to_csv(os.path.join(out, "clean.csv"), index=False)
    with open(os.path.join(out, "truth.json"), "w") as f:
        json.dump({"seed": result.seed, "n_rows": BASE_SPEC["n_rows"],
                   "corruptions": [c.__dict__ for c in result.truth]}, f, sort_keys=True)
    return out


def test_same_seed_identical_across_runs(tmp_path):
    a, b = _export(generate(BASE_SPEC, seed=42), str(tmp_path / "a")), _export(generate(BASE_SPEC, seed=42), str(tmp_path / "b"))
    for name in ("messy.csv", "clean.csv", "truth.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_same_seed_identical_in_memory():
    r1, r2 = generate(BASE_SPEC, seed=42), generate(BASE_SPEC, seed=42)
    pd.testing.assert_frame_equal(r1.messy, r2.messy)
    pd.testing.assert_frame_equal(r1.clean, r2.clean)
    assert r1.truth == r2.truth


def test_different_seed_different_data(tmp_path):
    a = _export(generate(BASE_SPEC, seed=42), str(tmp_path / "a"))
    b = _export(generate(BASE_SPEC, seed=123), str(tmp_path / "b"))
    assert (tmp_path / "a" / "messy.csv").read_bytes() != (tmp_path / "b" / "messy.csv").read_bytes()


def test_acceptance_suite():
    """Fractions hit, no double corruption, dtypes, row count with duplicates."""
    result = generate(BASE_SPEC, seed=7)
    n = BASE_SPEC["n_rows"]

    # observed count per (column, kind) == round(frac * n) within tolerance, and >= 1
    observed: dict[tuple[str, str], int] = {}
    for c in result.truth:
        observed[(c.column, c.kind)] = observed.get((c.column, c.kind), 0) + 1
    for col in BASE_SPEC["columns"]:
        for kind, frac in col.get("messiness", {}).items():
            got = observed.get((col["name"], kind), 0)
            assert got >= 1, (col["name"], kind)
            assert abs(got - round(frac * n)) <= 3, (col["name"], kind, got, round(frac * n))

    # a cell is never doubly corrupted
    cells = [(c.row, c.column) for c in result.truth]
    assert len(cells) == len(set(cells))

    # messy is all strings; clean dtypes match declared types
    assert all(d == object for d in result.messy.dtypes)
    assert result.clean["age"].dtype.kind == "i"
    assert result.clean["height_cm"].dtype.kind == "f"

    # row count == n_rows + duplicated rows
    k = round(BASE_SPEC["row_messiness"]["duplicate_rows"] * n)
    assert len(result.messy) == n + k
