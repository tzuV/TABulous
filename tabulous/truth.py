"""Corruption record and truth.json serialization."""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Corruption:
    row: int          # 0-based row index in messy output
    column: str
    kind: str         # "missing", "case_variation", ...
    original: Any     # value before corruption
    corrupted: Any    # value written to messy output


def truth_dict(corruptions: list[Corruption], seed: int, n_rows: int) -> dict:
    by_column: dict[str, list[dict]] = {}
    for c in corruptions:
        by_column.setdefault(c.column, []).append(dataclasses.asdict(c))
    return {
        "seed": seed,
        "n_rows": n_rows,
        "corruptions": [dataclasses.asdict(c) for c in corruptions],
        "by_column": by_column,
    }


def write_truth(path: str, corruptions: list[Corruption], seed: int, n_rows: int) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(truth_dict(corruptions, seed, n_rows), f, indent=2, sort_keys=True, default=str)
