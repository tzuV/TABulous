"""Messiness injectors: one function per kind."""
from __future__ import annotations

import random
from typing import Callable

from .spec import ColumnSpec
from .truth import Corruption

# injector(value: str, col: ColumnSpec, rng: random.Random, values: list[str]) -> str
Injector = Callable[[str, ColumnSpec, random.Random, list[str]], str]

ENCODINGS = {
    "true": ["True", "TRUE", "t", "Y", "yes", "1"],
    "false": ["False", "FALSE", "f", "N", "no", "0"],
    "yes": ["true", "Yes", "Y", "1"],
    "no": ["false", "No", "N", "0"],
}


def _missing(v: str, col: ColumnSpec, rng: random.Random, values: list[str]) -> str:
    return ""


def _out_of_range(v: str, col: ColumnSpec, rng: random.Random, values: list[str]) -> str:
    above = rng.random() < 0.5
    if col.type == "int":
        off = rng.randint(1, 10)
        return str(int(col.max) + off) if above else str(int(col.min) - off)
    off = round(rng.uniform(1, 10), col.decimals)
    return f"{col.max + off:.{col.decimals}f}" if above else f"{col.min - off:.{col.decimals}f}"


def _unit_suffix(v: str, col: ColumnSpec, rng: random.Random, values: list[str]) -> str:
    return f"{v} {col.unit}"


def _case_variation(v: str, col: ColumnSpec, rng: random.Random, values: list[str]) -> str:
    return v.lower() if v != v.lower() else v.upper()


def _whitespace(v: str, col: ColumnSpec, rng: random.Random, values: list[str]) -> str:
    return rng.choice([v + " ", " " + v, " " + v + " ", v + "\t"])


def _typo(v: str, col: ColumnSpec, rng: random.Random, values: list[str]) -> str:
    if len(v) < 2:
        return v + v
    i = rng.randrange(len(v) - 1)
    op = rng.choice(["swap", "delete", "dup", "replace"])
    if op == "swap":
        return v[:i] + v[i + 1] + v[i] + v[i + 2:]
    if op == "delete":
        return v[:i] + v[i + 1:]
    if op == "dup":
        return v[:i] + v[i] * 2 + v[i + 1:]
    letters = "abcdefghijklmnopqrstuvwxyz"
    c = rng.choice([ch for ch in letters if ch != v[i].lower()] or letters)
    return v[:i] + c + v[i + 1:]


def _duplicates(v: str, col: ColumnSpec, rng: random.Random, values: list[str]) -> str:
    others = [x for x in values if x != v]
    return rng.choice(others) if others else v


def _inconsistent_encoding(v: str, col: ColumnSpec, rng: random.Random, values: list[str]) -> str:
    alts = [e for e in ENCODINGS.get(v.lower(), []) if e != v]
    return rng.choice(alts) if alts else v


INJECTORS: dict[str, Injector] = {
    "missing": _missing,
    "out_of_range": _out_of_range,
    "unit_suffix": _unit_suffix,
    "case_variation": _case_variation,
    "whitespace": _whitespace,
    "typo": _typo,
    "duplicates": _duplicates,
    "inconsistent_encoding": _inconsistent_encoding,
}


def corrupt_column(col: ColumnSpec, values: list[str], messiness: dict, rng: random.Random):
    """Apply each messiness kind to round(frac * eligible) cells. One corruption per cell."""
    messy = list(values)
    done: set[int] = set()
    records: list[Corruption] = []
    for kind, frac in messiness.items():
        eligible = [i for i in range(len(values)) if i not in done]
        k = min(round(frac * len(eligible)), len(eligible))
        if k <= 0:
            continue
        for i in rng.sample(eligible, k):
            new = INJECTORS[kind](messy[i], col, rng, values)
            if new == messy[i]:
                continue  # ponytail: only possible when a column has one distinct value; cell stays clean
            records.append(Corruption(row=i, column=col.name, kind=kind,
                                      original=messy[i], corrupted=new))
            messy[i] = new
            done.add(i)
    return messy, records
