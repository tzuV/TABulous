# TABulous: Messy, Tabular and Fabulous Data On-Demand

A small, deterministic Python package that generates synthetic tabular datasets with
**known, controlled, injectable messiness** — for teaching data cleaning.

You describe the dataset in a YAML spec (rows, columns, types, and per-column
messiness fractions). TABulous produces:

- `messy.csv` — the dataset students receive
- `truth.json` — exactly which cells were corrupted and how (the answer key)
- `clean.csv` — the dataset before corruption (for reference / diffing)

Same seed ⇒ byte-identical output, always.

A step-by-step walkthrough lives in [TUTORIAL.md](TUTORIAL.md).

## Install

```bash
pip install -e .   # needs Python 3.10+; deps: pandas, pyyaml
```

## Quick start — no spec editing required

```bash
tabulous new-dataset demo    # starter spec + generated dataset, one command
tabulous kinds               # list every column type and messiness kind
tabulous --help              # everything else
```

## Worked example

`spec.yaml`:

```yaml
n_rows: 200
seed: 42

columns:
  - name: student_id
    type: id
    prefix: "S"
    padding: 4

  - name: age
    type: int
    min: 18
    max: 35
    messiness:
      missing: 0.05
      out_of_range: 0.02   # e.g. 999 or -1

  - name: grade
    type: choice
    options: [A, B, C, D, F]
    messiness:
      missing: 0.04
      case_variation: 0.05 # "a" instead of "A"
      whitespace: 0.03     # " A "

row_messiness:
  duplicate_rows: 0.02     # fraction of rows duplicated
```

Run it:

```bash
tabulous spec.yaml --out ./dataset --seed 42
```

```
Wrote 200 rows (200 original + 4 duplicated) to ./dataset/
Corruptions by column:
  student_id   0
  age         14
  grade       23
Seed: 42
Reproduce this dataset: tabulous spec.yaml --out ./dataset --seed 42
```

First rows of `messy.csv`:

```
S0001,21,b
S0002,18,A
S0003,26,A
S0004,25,D
S0005,25,C
```

First entries of `truth.json`:

```json
[
  {
    "column": "age",
    "corrupted": "",
    "kind": "missing",
    "original": "19",
    "row": 78
  },
  {
    "column": "age",
    "corrupted": "",
    "kind": "missing",
    "original": "32",
    "row": 58
  }
]
```

`truth.json` also groups records by column under `by_column`, so you can build a
per-question rubric without parsing.

## Python API

```python
from tabulous import generate, load_spec

spec = load_spec("spec.yaml")          # or pass the parsed dict directly
result = generate(spec, seed=42)
result.messy        # pandas.DataFrame (all strings — it's a CSV)
result.clean        # pandas.DataFrame with the declared dtypes
result.truth        # list[Corruption(row, column, kind, original, corrupted)]
```

## Column types

| type     | params                          | generates                       |
|----------|---------------------------------|---------------------------------|
| `id`     | `prefix`, `padding`             | `S0001`, `S0002`, …             |
| `int`    | `min`, `max`                    | integers in range               |
| `float`  | `min`, `max`, `decimals`        | floats in range                 |
| `choice` | `options`                       | one of the listed values        |
| `string` | `pattern` with `{first}`,`{last}`,`{word}` | fake text            |
| `date`   | `start`, `end`, `format`        | dates in range                  |

## Messiness kinds

Per column (each a fraction in `[0, 1]`):

| kind                    | effect                                            | applies to        |
|-------------------------|---------------------------------------------------|-------------------|
| `missing`               | empty cell                                        | all types         |
| `out_of_range`          | value outside min/max, e.g. `999`, `-1`           | `int`, `float`    |
| `unit_suffix`           | appends the column's `unit`, e.g. `178.4 cm`      | `int`, `float`    |
| `case_variation`        | `"a"` instead of `"A"`                            | `choice`, `string`|
| `whitespace`            | leading/trailing spaces or a tab                  | `choice`, `string`|
| `typo`                  | single-character edit                             | all               |
| `duplicates`            | same value as another row                         | all               |
| `inconsistent_encoding` | mixes `true/True/Y/1/…`                           | boolean `choice`  |

Per row:

| kind            | effect                        |
|-----------------|-------------------------------|
| `duplicate_rows`| fraction of rows duplicated   |

## Guarantees

- **Determinism.** One seeded RNG threaded through generation in a fixed order
  (columns in spec order → rows → corruption). Same spec + same seed ⇒
  byte-identical `messy.csv`, `clean.csv` and `truth.json` — across runs,
  machines and semesters. Different seed ⇒ different data.
- **One corruption per cell.** A cell receives at most one corruption, so
  fractions never "stack" into an unparseable value. Fraction counts are exact,
  not coin flips: `k = round(frac × eligible cells)` per kind (later kinds see a
  slightly smaller eligible pool, so their counts dip accordingly).
- **`clean.csv` dtypes match the declared types.** `messy.csv` is all strings —
  it's a CSV; that is expected.

## CLI

```
tabulous spec.yaml --out DIR [--seed N] [--no-clean] [--format csv|parquet]
                  [--force] [--no-answer-key]
tabulous init                 # commented starter spec.yaml
tabulous new-dataset demo     # starter spec + generate, one command
tabulous check spec.yaml      # validate without generating
tabulous preview spec.yaml    # first ~10 messy rows + corruption summary, no files
tabulous kinds                # all types & kinds with snippets
```

- `--seed` overrides the spec's seed; if neither is set, a random seed is used **and printed**.
- Existing output is never silently overwritten — pass `--force`.
- `--no-answer-key` produces a clean student bundle (no `truth.json`).
- Invalid specs report **all** problems at once, each with its line number and a
  "Did you mean …?" suggestion. Exit code 1, never a traceback.

## Grade the students

```python
import json, pandas as pd
from tabulous import load_spec, generate

spec = load_spec("spec.yaml")
result = generate(spec, seed=42)          # same seed as the handout
truth = json.load(open("dataset/truth.json"))

answers = pd.read_csv("student_submission.csv", dtype=str, keep_default_na=False)
messy = result.messy.astype(str)

score = 0
for c in truth["corruptions"]:
    submitted = answers.at[c["row"], c["column"]]
    if submitted == c["original"]:
        score += 1
print(f"{score}/{len(truth['corruptions'])} cells correctly cleaned")
```

## Definition of done (v1)

- `pip install -e .` works on Python 3.10+; `pytest` green.
- No dependency beyond `pandas`, `pyyaml` (+ `pytest` for tests). `--format parquet`
  additionally needs `pyarrow` at runtime.
- Public API: `generate`, `load_spec`, and the CLI. Nothing else is promised.
