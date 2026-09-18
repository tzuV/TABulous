"""CLI: tabulous spec.yaml --out DIR [--seed N] plus init / new-dataset / kinds / check / preview."""
from __future__ import annotations

import argparse
import os
import random
import sys

from .generate import generate
from .spec import MESSINESS_KINDS, TYPES, SPEC_TEMPLATE, TabulousError, load_spec
from .truth import write_truth

OUT_DEFAULT = "tabulous_out"

DESCRIPTION = """\
Generate messy tabular datasets with a known answer key for teaching data cleaning.

Quick start (no spec needed):
  tabulous init                 write a commented starter spec.yaml
  tabulous new-dataset demo     starter spec + generate, one command
  tabulous preview spec.yaml    peek at the messy output, no files written
  tabulous kinds                list column types and messiness kinds
Full workflow: create a spec (see above), then `tabulous spec.yaml --out DIR`.
"""


def _gen_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tabulous", description=DESCRIPTION,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("spec", help="path to a spec.yaml (create one with `tabulous init`)")
    p.add_argument("--out", default=OUT_DEFAULT,
                   help=f"output directory, created if missing (default: ./{OUT_DEFAULT}/)")
    p.add_argument("--seed", type=int, default=None,
                   help="random seed (overrides the spec's seed; a random one is used and printed if neither is set)")
    p.add_argument("--no-clean", action="store_true", help="skip writing clean.csv")
    p.add_argument("--format", choices=["csv", "parquet"], default="csv",
                   help="messy/clean file format (default: csv; parquet needs `pip install pyarrow`)")
    p.add_argument("--force", action="store_true", help="overwrite existing output files")
    p.add_argument("--answer-key", action=argparse.BooleanOptionalAction, default=True,
                   help="write truth.json, the answer key listing every corrupted cell (default: on; "
                        "--no-answer-key for a clean student bundle)")
    return p


def _export(result, spec, out: str, fmt: str, no_clean: bool, answer_key: bool) -> list[str]:
    os.makedirs(out, exist_ok=True)
    ext = "parquet" if fmt == "parquet" else "csv"
    writer = (lambda df, p: df.to_parquet(p, index=False)) if fmt == "parquet" \
        else (lambda df, p: df.to_csv(p, index=False))
    written = []
    messy_path = os.path.join(out, f"messy.{ext}")
    writer(result.messy, messy_path)
    written.append(messy_path)
    if not no_clean:
        clean_path = os.path.join(out, f"clean.{ext}")
        writer(result.clean, clean_path)
        written.append(clean_path)
    if answer_key:
        truth_path = os.path.join(out, "truth.json")
        write_truth(truth_path, result.truth, result.seed, spec.n_rows)
        written.append(truth_path)
    return written


def _summary(result, spec, out: str, spec_path: str, extra_flags: str = "") -> None:
    n_dup = len(result.messy) - spec.n_rows
    print(f"Wrote {len(result.messy)} rows ({spec.n_rows} original + {n_dup} duplicated) to {out}/")
    counts: dict[str, int] = {c.name: 0 for c in spec.columns}
    for c in result.truth:
        counts[c.column] += 1
    width = max((len(n) for n in counts), default=0)
    print("Corruptions by column:")
    for name, cnt in counts.items():
        print(f"  {name:<{width}}  {cnt}")
    print(f"Seed: {result.seed}")
    print(f"Reproduce this dataset: tabulous {spec_path} --out {out} --seed {result.seed}{extra_flags}")
    print("The answer key is truth.json — it lists exactly which cells were corrupted. "
          "Don't hand it to students.")


def _run_generate(spec_path: str, out: str, seed, no_clean: bool, fmt: str,
                  force: bool, answer_key: bool) -> int:
    spec = load_spec(spec_path)
    for w in spec.warnings:
        print(f"warning: {w}", file=sys.stderr)

    ext = "parquet" if fmt == "parquet" else "csv"
    planned = [os.path.join(out, f"messy.{ext}")]
    if not no_clean:
        planned.append(os.path.join(out, f"clean.{ext}"))
    if answer_key:
        planned.append(os.path.join(out, "truth.json"))
    existing = [p for p in planned if os.path.exists(p)]
    if existing and not force:
        raise TabulousError(f"{', '.join(existing)} already exist{'s' if len(existing) == 1 else ''}. "
                            "Not overwriting — pass --force to replace them.")

    result = generate(spec, seed=seed)
    if fmt == "parquet":
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            raise TabulousError("--format parquet needs the pyarrow package: pip install pyarrow") from None
    _export(result, spec, out, fmt, no_clean, answer_key)
    _summary(result, spec, out, spec_path,
             extra_flags="".join(f" --{f}" for f, on in
                                 (("no-clean", no_clean), ("no-answer-key", not answer_key)) if on))
    return 0


def _kinds() -> int:
    print("""\
Column types (params in parentheses are optional):
  id      (prefix, padding)          prefix: "S", padding: 4           -> S0001, S0002, ...
  int     (min, max)                 min: 18, max: 35                  -> 27
  float   (min, max, decimals)       min: 150, max: 200, decimals: 1   -> 178.4
  choice  (options)                  options: [A, B, C, D, F]          -> B
  string  (pattern)                  pattern: "{first}.{last}@school.edu"
          placeholders: {first} {last} {word}
  date    (start, end, format)       start: 2023-09-01, end: 2024-06-30, format: "%Y-%m-%d"

Messiness kinds — per column, each a fraction in [0, 1]:
  missing                 empty cells
  out_of_range            values outside min/max (int/float only)
  unit_suffix             appends the column's `unit`, e.g. "178.4 cm"
  case_variation          "a" instead of "A"
  whitespace              leading/trailing spaces or a tab
  typo                    single-character edit
  duplicates              same value as another row
  inconsistent_encoding   boolean choices only: mixes true/True/Y/1/...

Per row:
  row_messiness:
    duplicate_rows: 0.02  fraction of rows duplicated

Example:
    - name: age
      type: int
      min: 18
      max: 35
      messiness:
        missing: 0.05
        out_of_range: 0.02""")
    return 0


def _init(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tabulous init",
                                description="Write a commented starter spec.yaml in the current directory.")
    p.add_argument("--force", action="store_true", help="overwrite an existing spec.yaml")
    args = p.parse_args(argv)
    if os.path.exists("spec.yaml") and not args.force:
        raise TabulousError("spec.yaml already exists here. Not overwriting — pass --force, "
                            "or edit it and run: tabulous spec.yaml")
    with open("spec.yaml", "w", encoding="utf-8") as f:
        f.write(SPEC_TEMPLATE)
    print("Wrote spec.yaml — a working example with every column type and messiness kind.")
    print("Next: tabulous preview spec.yaml   (tweak fractions, then: tabulous spec.yaml)")
    return 0


def _new_dataset(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tabulous new-dataset",
                                description="Create a directory with a starter spec and a generated dataset, "
                                            "no editing required.")
    p.add_argument("name", help="directory to create")
    p.add_argument("--force", action="store_true", help="overwrite existing output files")
    args = p.parse_args(argv)
    os.makedirs(args.name, exist_ok=True)
    spec_path = os.path.join(args.name, "spec.yaml")
    if os.path.exists(spec_path):
        print(f"Using existing {spec_path}")
    else:
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write(SPEC_TEMPLATE)
        print(f"Wrote {spec_path} (starter spec — edit it and rerun to customize)")
    return _run_generate(spec_path, out=args.name, seed=None, no_clean=False,
                         fmt="csv", force=args.force, answer_key=True)


def _check(spec_path: str) -> int:
    spec = load_spec(spec_path)
    for w in spec.warnings:
        print(f"warning: {w}", file=sys.stderr)
    print(f"spec looks good — {len(spec.columns)} columns, {spec.n_rows} rows.")
    print(f"Generate it with: tabulous {spec_path}   (or preview first: tabulous preview {spec_path})")
    return 0


def _preview(spec_path: str, seed) -> int:
    spec = load_spec(spec_path)
    for w in spec.warnings:
        print(f"warning: {w}", file=sys.stderr)
    result = generate(spec, seed=seed)
    print(f"First {min(10, len(result.messy))} messy rows (seed {result.seed}, nothing written to disk):")
    print(result.messy.head(10).to_string())
    counts: dict[str, int] = {c.name: 0 for c in spec.columns}
    for c in result.truth:
        counts[c.column] += 1
    print("Corruptions by column:")
    for name, cnt in counts.items():
        print(f"  {name}  {cnt}")
    print(f"Generate for real with: tabulous {spec_path} --seed {result.seed}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if not argv or argv[0] in ("-h", "--help"):
            _gen_parser().print_help()
            return 0
        cmd, rest = argv[0], argv[1:]
        if cmd == "kinds":
            return _kinds()
        if cmd == "init":
            return _init(rest)
        if cmd == "new-dataset":
            return _new_dataset(rest)
        if cmd in ("check", "preview"):
            p = argparse.ArgumentParser(prog=f"tabulous {cmd}")
            p.add_argument("spec")
            p.add_argument("--seed", type=int, default=None)
            a = p.parse_args(rest)
            return _check(a.spec) if cmd == "check" else _preview(a.spec, a.seed)
        args = _gen_parser().parse_args(argv)
        return _run_generate(args.spec, args.out, args.seed, args.no_clean,
                             args.format, args.force, args.answer_key)
    except TabulousError as e:
        print(e, file=sys.stderr)
        return 1
    except Exception as e:  # never show a traceback for user-facing errors
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
