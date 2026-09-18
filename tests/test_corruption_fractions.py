import pandas as pd

from tabulous import generate

N = 200


def spec(**col):
    base = {"n_rows": N, "seed": 1, "columns": [dict(name="col", **col)]}
    return base


def counts(result):
    out = {}
    for c in result.truth:
        out[c.kind] = out.get(c.kind, 0) + 1
    return out


def test_each_kind_produces_expected_count():
    frac = 0.10
    cases = [
        spec(type="int", min=0, max=100, messiness={"missing": frac, "out_of_range": frac, "typo": frac}),
        spec(type="float", min=0, max=100, messiness={"missing": frac, "unit_suffix": frac, "out_of_range": frac}),
        spec(type="choice", options=["A", "B", "C"],
             messiness={"missing": frac, "case_variation": frac, "whitespace": frac, "typo": frac}),
        spec(type="choice", options=["true", "false"], messiness={"inconsistent_encoding": frac}),
        spec(type="string", pattern="{word}-{word}", messiness={"missing": frac, "duplicates": frac, "typo": frac}),
        spec(type="date", messiness={"missing": frac}),
        spec(type="id", prefix="S", messiness={"missing": frac, "typo": frac, "duplicates": frac}),
    ]
    for s in cases:
        r = generate(s, seed=3)
        got = counts(r)
        assert got, s["columns"][0]
        for kind in s["columns"][0]["messiness"]:
            # k = round(frac * eligible): earlier kinds shrink the eligible pool, so the
            # observed count drifts below round(frac * n) when several kinds stack up.
            assert abs(got[kind] - round(frac * N)) <= 6, (s["columns"][0]["type"], kind, got[kind])


def test_row_duplicates():
    r = generate({"n_rows": 100, "seed": 5, "columns": [{"name": "x", "type": "int", "min": 0, "max": 9}],
                  "row_messiness": {"duplicate_rows": 0.1}}, seed=5)
    assert len(r.messy) == 110
    # duplicated rows really are duplicates of an original row
    orig = r.messy.iloc[:100].apply(tuple, axis=1).tolist()
    for _, row in r.messy.iloc[100:].iterrows():
        assert tuple(row) in orig


def test_no_double_corruption_with_overlapping_fractions():
    r = generate(spec(type="string", pattern="{word} {word}",
                      messiness={"missing": 0.3, "whitespace": 0.3, "case_variation": 0.3}), seed=9)
    cells = [(c.row, c.column) for c in r.truth]
    assert len(cells) == len(set(cells))


def test_no_cell_both_empty_and_malformed():
    """A corrupted cell is either empty (missing) or malformed — never a doubly-mangled value."""
    r = generate(spec(type="float", min=0, max=10, messiness={"missing": 0.2, "unit_suffix": 0.2}), seed=11)
    for c in r.truth:
        if c.kind == "missing":
            assert c.corrupted == ""
        else:
            assert c.corrupted != ""


def test_clean_dtypes_match_declared_types():
    r = generate({"n_rows": 20, "seed": 2, "columns": [
        {"name": "i", "type": "int", "min": 0, "max": 5},
        {"name": "f", "type": "float", "min": 0, "max": 1},
        {"name": "s", "type": "choice", "options": ["x"]},
    ]}, seed=2)
    assert r.clean["i"].dtype.kind == "i"
    assert r.clean["f"].dtype.kind == "f"
    assert pd.api.types.is_string_dtype(r.clean["s"])
