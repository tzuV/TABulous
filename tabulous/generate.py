"""Clean column generation and the top-level generate() entry point."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

import pandas as pd

from .corrupt import corrupt_column
from .spec import ColumnSpec, Spec, spec_from_data
from .truth import Corruption

FIRST = ["ava", "liam", "maya", "noah", "zoe", "ethan", "iris", "owen", "ruby", "felix"]
LAST = ["chen", "diaz", "kim", "novak", "patel", "rossi", "silva", "toure", "weber", "zhang"]
WORDS = ["alpha", "bravo", "delta", "ember", "flint", "grove", "harbor", "ivory", "jade", "kilo"]


@dataclass
class GenerationResult:
    messy: pd.DataFrame     # all strings — it's a CSV
    clean: pd.DataFrame     # dtypes match the declared types
    truth: list[Corruption]
    seed: int


def _gen_values(col: ColumnSpec, n: int, rng: random.Random) -> list:
    if col.type == "id":
        return [f"{col.prefix}{i + 1:0{col.padding}d}" for i in range(n)]
    if col.type == "int":
        return [rng.randint(int(col.min), int(col.max)) for _ in range(n)]
    if col.type == "float":
        return [round(rng.uniform(col.min, col.max), col.decimals) for _ in range(n)]
    if col.type == "choice":
        return [rng.choice(col.options) for _ in range(n)]
    if col.type == "string":
        return [col.pattern.format(first=rng.choice(FIRST), last=rng.choice(LAST),
                                   word=rng.choice(WORDS)) for _ in range(n)]
    if col.type == "date":
        d0 = date.fromisoformat(str(col.start)).toordinal()
        d1 = date.fromisoformat(str(col.end)).toordinal()
        return [date.fromordinal(rng.randint(d0, d1)) for _ in range(n)]
    raise ValueError(f"unhandled column type {col.type!r}")  # unreachable: validated in spec.py


def _canon(v, col: ColumnSpec) -> str:
    """Canonical string form of a clean value — what clean.csv would show."""
    if col.type == "float":
        return f"{v:.{col.decimals}f}"
    if col.type == "date":
        return v.strftime(col.date_format)
    return str(v)


def generate(spec, seed: int | None = None) -> GenerationResult:
    """Generate a dataset. `spec` is a Spec or a plain dict (as parsed from YAML/JSON)."""
    if isinstance(spec, dict):
        spec = spec_from_data(spec)
    assert isinstance(spec, Spec)

    if seed is None:
        seed = spec.seed if spec.seed is not None else random.SystemRandom().randrange(1, 2**31)
    rng = random.Random(seed)

    n = spec.n_rows
    names = [c.name for c in spec.columns]
    py_values = {c.name: _gen_values(c, n, rng) for c in spec.columns}
    canon = {c.name: [_canon(v, c) for v in py_values[c.name]] for c in spec.columns}

    truth: list[Corruption] = []
    messy_cols: dict[str, list[str]] = {}
    for c in spec.columns:  # file order, one Random, fixed sequence — this is the determinism contract
        messy_cols[c.name], recs = corrupt_column(c, canon[c.name], c.messiness, rng)
        truth.extend(recs)

    rows = [[messy_cols[nm][i] for nm in names] for i in range(n)]
    k = round(spec.row_messiness.get("duplicate_rows", 0) * n)
    if k > 0:
        rows.extend(list(rows[i]) for i in rng.sample(range(n), min(k, n)))

    messy = pd.DataFrame(rows, columns=names, dtype=object)
    clean = pd.DataFrame(py_values, columns=names)
    return GenerationResult(messy=messy, clean=clean, truth=truth, seed=seed)
