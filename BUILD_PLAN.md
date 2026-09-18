# TABulous — Build Plan

Messy, Tabular and Fabulous Data On-Demand.

A small, deterministic Python package that generates synthetic tabular datasets with
**known, controlled, injectable messiness**, for teaching data cleaning.

---

## 1. Problem

Instructors need datasets whose defects they already know. Hunting for a real-world
CSV that happens to be missing values in column 3 and has unit suffixes in column 5 is
slow and non-reproducible. Generating the data means the ground truth is free:
we know exactly which cell we corrupted, so we can grade the cleaning.

## 2. Goal

Given a declarative spec (rows, columns, types, ranges, and per-column messiness
fractions), produce:

1. `messy.csv` — the dataset students receive.
2. `truth.json` — exactly which cells were corrupted and how (the answer key).
3. `clean.csv` — the dataset before corruption (optional, for reference/diffing).

Same seed ⇒ byte-identical output. That is non-negotiable: instructors must be able to
hand out the same dataset across sections and across semesters.

## 3. Non-goals (v1)

- No GUI, no web app.
- No realistic statistical modeling (correlations, distributions beyond uniform/normal/choice).
- No auto-inferred schema, no ML, no LLM generation.
- No streaming / big-data support. Datasets here are classroom-sized (≤ ~100k rows).

## 4. Deliverable

Installable package, importable and CLI-usable:

```
pip install -e .
tabulous spec.yaml --out ./dataset --seed 42
```

```python
from tabulous import generate
result = generate(spec_dict, seed=42)
result.messy        # pandas.DataFrame
result.clean        # pandas.DataFrame
result.truth        # list[Corruption]
```

Also required: `pyproject.toml`, `README.md` with a worked example, and a test suite.

## 5. Spec format

YAML (JSON also accepted, since YAML is a superset parse target — just use
`yaml.safe_load`, which handles both).

```yaml
n_rows: 200
seed: 42

columns:
  - name: student_id
    type: id
    prefix: "S"
    padding: 4
    # no messiness: keeps a reliable join key

  - name: age
    type: int
    min: 18
    max: 35
    messiness:
      missing: 0.05
      out_of_range: 0.02   # e.g. 999, -1

  - name: height_cm
    type: float
    min: 150
    max: 200
    decimals: 1
    messiness:
      missing: 0.03
      unit_suffix: 0.05    # "178.4 cm"

  - name: grade
    type: choice
    options: [A, B, C, D, F]
    messiness:
      missing: 0.04
      case_variation: 0.05  # "a", "B"
      whitespace: 0.03      # " A "

  - name: enrolled
    type: choice
    options: ["true", "false"]
    messiness:
      inconsistent_encoding: 0.05  # mixes true/false, True/False, Y/N, 1/0

  - name: email
    type: string
    pattern: "{first}.{last}@school.edu"
    messiness:
      missing: 0.02
      duplicates: 0.03

row_messiness:
  duplicate_rows: 0.02   # fraction of rows duplicated
```

### Column types (v1)

| type     | params                                   | generates                      |
|----------|------------------------------------------|--------------------------------|
| `id`     | `prefix`, `padding`                      | `S0001`, `S0002`, …            |
| `int`    | `min`, `max`                             | integers in range               |
| `float`  | `min`, `max`, `decimals`                 | floats in range                 |
| `choice` | `options`                                | one of the listed values        |
| `string` | `pattern` with `{first}`,`{last}`,`{word}` | fake text                     |
| `date`   | `start`, `end`, `format`                 | dates in range                  |

### Messiness types (v1)

Per-column: `missing`, `out_of_range`, `unit_suffix`, `case_variation`,
`whitespace`, `typo` (single-char edit), `duplicates`, `inconsistent_encoding`.
Per-row: `duplicate_rows`.

Each messiness key maps to a fraction in `[0, 1]`, applied independently per column.
Fractions are applied to the *cells eligible for that corruption* in that column, and
a single cell may receive at most one corruption (so fractions cannot "stack" and
produce an unparseable cell).

## 6. Ground truth / answer key

Every corruption appends a record:

```python
@dataclass(frozen=True)
class Corruption:
    row: int          # 0-based row index in messy output
    column: str
    kind: str         # "missing", "case_variation", ...
    original: Any     # value before corruption
    corrupted: Any    # value written to messy.csv
```

Written to `truth.json`, grouped by column as well as listed flat, so the instructor
can build a per-question rubric without parsing.

## 7. Determinism rules

- One `random.Random(seed)` (or `np.random.default_rng(seed)`) created once and threaded
  through all generation, in a fixed order: columns → rows → corruption.
- No use of global `random`, no `numpy` legacy global seed, no dict-iteration-order
  dependence (iterate `columns` as a list, in file order).
- `truth.json` keys sorted; export uses fixed float formatting (`decimals`).
- A test asserts identical output for the same seed and different output for a different seed.

## 8. Architecture (keep it small)

```
tabulous/
  __init__.py      # exports generate, load_spec
  spec.py          # spec parsing + validation (dataclasses)
  generate.py      # clean column generation
  corrupt.py       # messiness injectors, one function per kind
  truth.py         # Corruption dataclass, serialization
  cli.py           # argparse entry point
tests/
  test_determinism.py
  test_corruption_fractions.py
  test_spec_validation.py
  test_cli.py
pyproject.toml
README.md
```

Rules for the implementer:

- **Stdlib first.** `argparse`, `dataclasses`, `json`, `random`, `csv` are all you need.
  Add `pyyaml` (for specs) and `pandas` (for the frame + CSV export) — those two are the
  entire dependency budget, plus `pytest` as a dev dependency. Do not add `faker`,
  `pydantic`, `click`, `typer`, or a schema library.
- **One module per concern**, functions over classes. No base classes, no plugin registry
  for messiness kinds in v1 — a `dict[str, Callable]` dispatch table is enough, and only
  if it actually saves code versus an `if/elif` chain.
- **Fractions must be empirically checkable.** For a column of 200 rows with
  `missing: 0.05`, the corrupted count must be within ±2 of 10 (rounding), not
  a probabilistic coin flip per cell. Use `rng.sample(eligible, k)` with
  `k = round(frac * len(eligible))`. Instructors need reproducibility, not realism.
- Validate aggressively at the spec boundary: unknown column type, unknown messiness
  kind, fraction outside `[0,1]`, `min > max`, duplicate column names → fail with a
  clear message naming the offending key. This is a trust boundary; do not skip it.
- Corruptions that would make a cell empty *and* malformed at once must not happen —
  see the one-corruption-per-cell rule above.

## 9. CLI

```
tabulous spec.yaml --out DIR [--seed N] [--no-clean] [--format csv|parquet]
```

- `--seed` overrides the spec's `seed`.
- `--out DIR` creates the directory if missing.
- Prints a short summary: rows written, per-column corruption counts.
- Exit code 1 with a readable error on invalid spec; never a raw traceback for user error.

## 10. Tests (acceptance criteria)

1. Same seed → identical `messy.csv`, `truth.json`, `clean.csv` across two runs and two processes.
2. Different seed → different data.
3. Each messiness kind produces ≥1 corruption when its fraction > 0, and the observed
   count matches `round(frac * n)` within tolerance.
4. A cell is never doubly corrupted.
5. `clean.csv` column dtypes are exactly the declared types; `messy.csv` is all strings
   (it's a CSV — that is fine and expected, note it in the README).
6. Invalid specs raise a clear, actionable error.
7. End-to-end CLI test on a fixture spec produces all three files.
8. Row count of `messy.csv` equals `n_rows + duplicate_rows_injected`.

## 11. README requirements

- One copy-pasteable example: spec → command → first 5 lines of messy output → first
  few entries of `truth.json`.
- A table of supported column types and messiness kinds.
- An explicit statement of the determinism guarantee and the one-corruption-per-cell rule.
- A short "grade the students" snippet showing how to diff `messy` against `truth`.

## 12. Usability (non-negotiable)

The user is an instructor with a class in an hour, not a programmer reading docs. Every
rule below is a hard requirement, not polish.

**Zero-config start.**
- `tabulous init` writes a commented `spec.yaml` with all column types and messiness
  kinds shown as working examples. `tabulous new-dataset mydata` = init + generate in
  one command, no spec editing required.
- `tabulous spec.yaml` with no `--out` writes to `./tabulous_out/` and says so.

**Errors never blame the user.**
- Never a traceback. Every failure is one line: what's wrong, where, and the fix.
  ```
  spec.yaml: column 'age': 'min' (40) is greater than 'max' (30)
  Did you mean to swap them?
  ```
  ```
  spec.yaml: column 'grade': unknown messiness kind 'missingg'
  Did you mean 'missing'? Supported: missing, out_of_range, typo, ...
  ```
- Unknown keys are typos until proven otherwise: suggest the nearest known key
  (stdlib `difflib.get_close_matches` — no dependency).
- Validation reports **all** problems at once, not the first. Fixing 6 typos should not
  take 6 runs.
- Include the offending line number from the spec file when available.

**Discoverable, not documented.**
- `tabulous --help` is enough to generate a dataset without opening the README.
- `tabulous kinds` lists every column type and messiness kind with a one-line
  description and a copy-pasteable snippet.
- `tabulous check spec.yaml` validates without generating.
- `tabulous preview spec.yaml` prints the first ~10 messy rows and the corruption
  summary to the terminal — the fast feedback loop for tuning fractions. No files written.

**Human-readable output.**
- After generating, print exactly where the files are, the row count, and per-column
  corruption counts as a small aligned table. Always print the seed used, so a dataset
  can be reproduced and shared by quoting one number.
- The summary ends with one copy-pasteable line to regenerate the same dataset.

**Safe defaults.**
- Sensible defaults for everything optional: `seed` (random, but printed), `n_rows`
  (refuses to guess — must be explicit), `decimals` (2), file `--out` (`./tabulous_out/`).
- Never overwrite existing output silently. If files exist, ask, or require `--force`.
  Losing a dataset you spent time tuning is the worst outcome here.
- Warn (don't fail) when a spec looks off: fractions above 0.5 on a column, total
  messiness > 0.5 in a column, `n_rows` under 10, empty `columns` list.

**Teaching-specific.**
- Print a one-line hint to `truth.json` after every run: instructors forget it exists.
- `--answer-key` flag (default on) makes the truth file's role explicit; suppressing it
  produces a clean "student" bundle for handing out.

## 13. Usability tests (acceptance criteria)

1. `tabulous --help` mentions how to create a spec and generate a dataset.
2. `tabulous new-dataset demo` in an empty directory produces a working dataset with
   no prior setup and no spec file.
3. A spec with 3 distinct errors reports all 3 in one run, each naming its line.
4. `missingg` produces a "Did you mean 'missing'?" message, exit code 1, no traceback.
5. `tabulous preview` writes no files.
6. Running twice into the same `--out` refuses the second run without `--force`.
7. Every generated run prints the seed and a copy-pasteable reproduce command.
8. No error path in the CLI emits a Python traceback (test by fuzzing the CLI with
   malformed specs).

## 14. Definition of done

- `pip install -e .` works on Python 3.10+.
- `pytest` green.
- The README example runs verbatim.
- No dependency beyond `pyyaml`, `pandas`, `pytest`.
- Public API is `generate`, `load_spec`, and the CLI. Nothing else is promised.
- A first-time user can go from empty directory to a dataset with `truth.json` in one
  command, without reading any documentation.