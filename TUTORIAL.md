# TABulous in 10 Minutes

Make a small messy dataset with an answer key, hand it to your class, grade it automatically.

---

## 1. Zero-config start (no reading required)

```bash
tabulous new-dataset demo
```

That creates a `demo/` folder with a working `spec.yaml` and a generated dataset inside.
Peek at it, no files written:

```bash
tabulous preview demo/spec.yaml
```

## 2. Write your own spec

Create `spec.yaml` (or run `tabulous init` for a commented starter):

```yaml
n_rows: 100
seed: 42

columns:
  - name: student_id
    type: id
    prefix: "S"
    padding: 3            # S001, S002, ...

  - name: age
    type: int
    min: 18
    max: 30
    messiness:
      missing: 0.10       # 10% empty cells
      out_of_range: 0.05  # values like 999 or -1

  - name: height
    type: float
    min: 150
    max: 200
    decimals: 1
    unit: cm
    messiness:
      unit_suffix: 0.20   # "178.4 cm"

  - name: grade
    type: choice
    options: [A, B, C, D, F]
    messiness:
      case_variation: 0.10  # "a"
      whitespace: 0.10      # " A "

  - name: email
    type: string
    pattern: "{first}.{last}@school.edu"
    messiness:
      duplicates: 0.05    # same value as another row

row_messiness:
  duplicate_rows: 0.05    # 5 duplicated rows
```

Check it before generating:

```bash
tabulous check spec.yaml
```

## 3. Tune with preview, then generate

```bash
tabulous preview spec.yaml          # first 10 messy rows + corruption counts, no files
tabulous spec.yaml --out dataset --seed 42
```

You get:

- `dataset/messy.csv` — what students receive
- `dataset/clean.csv` — the pre-corruption original
- `dataset/truth.json` — every corrupted cell: row, column, kind, original, corrupted

Run it again with the same seed and you get **byte-identical files**. Quote the seed
to hand out the same dataset next semester. Different seed → different dataset.

Hand out only `messy.csv` — or generate a student bundle without the answer key:

```bash
tabulous spec.yaml --out students --no-answer-key
```

## 4. Grade it

```python
import json
import pandas as pd

answers = pd.read_csv("student_submission.csv", dtype=str, keep_default_na=False)
truth = json.load(open("dataset/truth.json"))["corruptions"]

score = sum(answers.at[c["row"], c["column"]] == c["original"] for c in truth)
print(f"{score}/{len(truth)} cells correctly cleaned")
```

`truth.json` also groups by column under `by_column` — build one rubric question per
messiness kind without parsing.

## Cheat sheet

```bash
tabulous init                  # commented starter spec in ./spec.yaml
tabulous kinds                 # all column types & messiness kinds + snippets
tabulous check spec.yaml       # validate, report all problems at once
tabulous preview spec.yaml     # look before you generate
tabulous spec.yaml --out DIR --seed N [--force] [--no-clean] [--no-answer-key]
```

**Guarantees:** same seed ⇒ identical output, always. One corruption per cell —
fractions never stack into an unparseable value. `clean.csv` keeps proper dtypes;
`messy.csv` is all strings (it's a CSV). Errors name the line and suggest a fix —
never a traceback.
