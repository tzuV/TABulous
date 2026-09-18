"""Spec parsing + validation. Fails with all problems at once, each with a line number when available."""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field

import yaml

class TabulousError(Exception):
    """User-facing spec/CLI error. One line per problem, no traceback."""


TYPES = ("id", "int", "float", "choice", "string", "date")

PARAMS: dict[str, set[str]] = {
    "id": {"prefix", "padding"},
    "int": {"min", "max", "unit"},
    "float": {"min", "max", "decimals", "unit"},
    "choice": {"options"},
    "string": {"pattern"},
    "date": {"start", "end", "format"},
}
COMMON_PARAMS = {"name", "type", "messiness"}

MESSINESS_KINDS = (
    "missing", "out_of_range", "unit_suffix", "case_variation",
    "whitespace", "typo", "duplicates", "inconsistent_encoding",
)

ALLOWED_KINDS: dict[str, set[str]] = {
    "id": {"missing", "duplicates", "typo"},
    "int": {"missing", "out_of_range", "unit_suffix", "typo", "duplicates"},
    "float": {"missing", "out_of_range", "unit_suffix", "typo", "duplicates"},
    "choice": {"missing", "case_variation", "whitespace", "typo", "duplicates", "inconsistent_encoding"},
    "string": {"missing", "case_variation", "whitespace", "typo", "duplicates"},
    "date": {"missing", "duplicates"},
}

BOOLEAN_LIKE = {"true", "false", "yes", "no"}

TOP_LEVEL_KEYS = {"n_rows", "seed", "columns", "row_messiness"}


@dataclass
class ColumnSpec:
    name: str
    type: str
    line: int = 0
    prefix: str = ""
    padding: int = 4
    min: float = 0
    max: float = 100
    decimals: int = 2
    options: list = field(default_factory=list)
    pattern: str = "{first} {last}"
    start: str = "2020-01-01"
    end: str = "2024-12-31"
    date_format: str = "%Y-%m-%d"
    unit: str = "units"
    messiness: dict = field(default_factory=dict)


@dataclass
class Spec:
    n_rows: int
    seed: int | None
    columns: list[ColumnSpec]
    row_messiness: dict
    source: str = "<spec>"
    warnings: list[str] = field(default_factory=list)


def _suggest(word, known) -> str:
    m = difflib.get_close_matches(str(word), [str(k) for k in known], n=1)
    return f" Did you mean '{m[0]}'?" if m else ""


def _line_map(text: str) -> dict:
    """Map (path...) -> line number of the key, via the YAML node tree."""
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        return {}
    out: dict = {}

    def walk(node, path):
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                out[path + (str(k.value),)] = k.start_mark.line + 1
                walk(v, path + (str(k.value),))
        elif isinstance(node, yaml.SequenceNode):
            for i, item in enumerate(node.value):
                walk(item, path + (i,))

    if root is not None:
        walk(root, ())
    return out


def _fail(source: str, problems: list[tuple[int | None, str]]):
    if len(problems) == 1:
        line, msg = problems[0]
        loc = f"line {line}: " if line else ""
        raise TabulousError(f"{source}: {loc}{msg}")
    lines = [f"{source}: {len(problems)} problems:"]
    for line, msg in problems:
        lines.append(f"  line {line}: {msg}" if line else f"  {msg}")
    raise TabulousError("\n".join(lines))


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _frac_problems(owner: str, mess: dict, ctype: str | None, lm: dict, path_prefix: tuple) -> list[tuple[int | None, str]]:
    probs = []
    if not isinstance(mess, dict):
        probs.append((lm.get(path_prefix), f"{owner}: 'messiness' must be a mapping of kind: fraction"))
        return probs
    for i, (kind, frac) in enumerate(mess.items()):
        p = path_prefix + (str(kind),)
        if kind not in MESSINESS_KINDS:
            probs.append((lm.get(p), f"{owner}: unknown messiness kind '{kind}'"
                          f"{_suggest(kind, MESSINESS_KINDS)}. Supported: {', '.join(MESSINESS_KINDS)}"))
            continue
        if ctype is not None and kind not in ALLOWED_KINDS[ctype]:
            allowed = ", ".join(sorted(ALLOWED_KINDS[ctype]))
            probs.append((lm.get(p), f"{owner}: messiness kind '{kind}' is not supported for type '{ctype}' (supported: {allowed})"))
        if not _num(frac) or not (0 <= frac <= 1):
            probs.append((lm.get(p), f"{owner}: messiness '{kind}' must be a fraction in [0, 1], got {frac!r}"))
    return probs


def spec_from_data(data, source: str = "<spec>", text: str | None = None) -> Spec:
    lm = _line_map(text) if text is not None else {}
    problems: list[tuple[int | None, str]] = []

    if not isinstance(data, dict):
        _fail(source, [(None, f"expected a mapping at the top level, got {type(data).__name__}")])

    # --- top-level keys ---
    for key in data:
        if key not in TOP_LEVEL_KEYS:
            problems.append((lm.get((str(key),), 1), f"unknown key '{key}'{_suggest(key, TOP_LEVEL_KEYS)}. "
                             f"Known keys: {', '.join(sorted(TOP_LEVEL_KEYS))}"))

    n_rows = data.get("n_rows")
    if n_rows is None:
        problems.append((lm.get(("n_rows",), 2), "'n_rows' is required (refusing to guess how many rows you want)"))
    elif not isinstance(n_rows, int) or isinstance(n_rows, bool) or n_rows < 1:
        problems.append((lm.get(("n_rows",), 2), f"'n_rows' must be a positive integer, got {n_rows!r}"))

    seed = data.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        problems.append((lm.get(("seed",)), f"'seed' must be an integer, got {seed!r}"))

    row_messiness = data.get("row_messiness") or {}
    if not isinstance(row_messiness, dict):
        problems.append((lm.get(("row_messiness",)), "'row_messiness' must be a mapping"))
        row_messiness = {}
    else:
        for kind, frac in row_messiness.items():
            p = ("row_messiness", str(kind))
            if kind != "duplicate_rows":
                problems.append((lm.get(p), f"unknown row messiness kind '{kind}'{_suggest(kind, ['duplicate_rows'])}. "
                                 f"Supported: duplicate_rows"))
            elif not _num(frac) or not (0 <= frac <= 1):
                problems.append((lm.get(p), f"row messiness 'duplicate_rows' must be a fraction in [0, 1], got {frac!r}"))

    # --- columns ---
    columns_data = data.get("columns")
    if columns_data is None:
        problems.append((lm.get(("columns",)), "'columns' is required (a list of column specs)"))
        columns_data = []
    elif not isinstance(columns_data, list):
        problems.append((lm.get(("columns",)), "'columns' must be a list"))
        columns_data = []

    columns: list[ColumnSpec] = []
    seen_names: set[str] = set()
    messy_totals: list[tuple[str, float]] = []
    for i, cd in enumerate(columns_data):
        p = ("columns", i)
        if not isinstance(cd, dict):
            problems.append((lm.get(p), f"column #{i + 1}: expected a mapping of parameters"))
            continue
        name = cd.get("name")
        name_line = lm.get(p + ("name",), lm.get(p))
        if not isinstance(name, str) or not name:
            problems.append((name_line, f"column #{i + 1}: 'name' is required and must be a non-empty string"))
            name = f"column_{i + 1}"
        elif name in seen_names:
            problems.append((name_line, f"duplicate column name '{name}'"))
        seen_names.add(name)

        ctype = cd.get("type")
        type_line = lm.get(p + ("type",), lm.get(p))
        if ctype not in TYPES:
            problems.append((type_line, f"column '{name}': unknown type {ctype!r}{_suggest(ctype, TYPES)}. "
                             f"Supported: {', '.join(TYPES)}"))
            ctype = None  # keep validating the rest of this column so all errors surface at once

        if ctype is not None:
            allowed = PARAMS[ctype] | COMMON_PARAMS
            for key in cd:
                if key not in allowed:
                    problems.append((lm.get(p + (str(key),), lm.get(p)),
                                     f"column '{name}': unknown parameter '{key}' for type '{ctype}'"
                                     f"{_suggest(key, allowed)}. Supported: {', '.join(sorted(allowed))}"))

        col = ColumnSpec(name=name, type=ctype or "int", line=lm.get(p, 0))

        if ctype == "choice":
            options = cd.get("options")
            if not isinstance(options, list) or not options:
                problems.append((lm.get(p + ("options",), lm.get(p)),
                                 f"column '{name}': type 'choice' needs a non-empty 'options' list"))
            else:
                col.options = [str(o) for o in options]

        if ctype in ("int", "float") or "min" in cd or "max" in cd:
            lo, hi = cd.get("min", col.min), cd.get("max", col.max)
            if not _num(lo) or not _num(hi):
                problems.append((lm.get(p + ("min",), lm.get(p)),
                                 f"column '{name}': 'min' and 'max' must be numbers"))
            elif lo > hi:
                problems.append((lm.get(p + ("min",), lm.get(p + ("max",), lm.get(p))),
                                 f"column '{name}': 'min' ({lo}) is greater than 'max' ({hi}). Did you mean to swap them?"))
            else:
                col.min, col.max = lo, hi

        if "decimals" in cd:
            if not isinstance(cd["decimals"], int) or isinstance(cd["decimals"], bool) or cd["decimals"] < 0:
                problems.append((lm.get(p + ("decimals",)), f"column '{name}': 'decimals' must be a non-negative integer"))
            else:
                col.decimals = cd["decimals"]
        if "padding" in cd:
            if not isinstance(cd["padding"], int) or isinstance(cd["padding"], bool) or cd["padding"] < 1:
                problems.append((lm.get(p + ("padding",)), f"column '{name}': 'padding' must be a positive integer"))
            else:
                col.padding = cd["padding"]
        for key, attr in (("prefix", "prefix"), ("pattern", "pattern"), ("unit", "unit"), ("format", "date_format")):
            if key in cd:
                if not isinstance(cd[key], str):
                    problems.append((lm.get(p + (key,)), f"column '{name}': '{key}' must be a string"))
                else:
                    setattr(col, attr, cd[key])
        for key, attr in (("start", "start"), ("end", "end")):
            if key in cd and isinstance(cd[key], str):
                setattr(col, attr, cd[key])

        col.messiness = cd.get("messiness") or {}
        problems.extend(_frac_problems(f"column '{name}'", col.messiness, ctype, lm, p + ("messiness",)))

        if ctype is None:
            continue  # type-dependent setup below; the unknown-type error is already recorded

        if "inconsistent_encoding" in col.messiness and ctype == "choice":
            if not set(o.lower() for o in col.options) <= BOOLEAN_LIKE:
                problems.append((lm.get(p + ("messiness", "inconsistent_encoding"), lm.get(p)),
                                 f"column '{name}': 'inconsistent_encoding' needs boolean-like options "
                                 f"(true/false/yes/no), got {col.options}"))

        if isinstance(col.messiness, dict):
            fracs = [f for f in col.messiness.values() if _num(f)]
            if sum(fracs) > 0.5:
                messy_totals.append((name, sum(fracs)))

        columns.append(col)

    # date start <= end
    for col in columns:
        if col.type == "date":
            from datetime import date
            try:
                s, e = date.fromisoformat(str(col.start)), date.fromisoformat(str(col.end))
                if s > e:
                    problems.append((None, f"column '{col.name}': 'start' ({col.start}) is after 'end' ({col.end}). "
                                     "Did you mean to swap them?"))
            except ValueError:
                problems.append((None, f"column '{col.name}': 'start'/'end' must be ISO dates (YYYY-MM-DD), "
                                 f"got {col.start!r} / {col.end!r}"))

    if problems:
        _fail(source, problems)

    # --- warnings (not fatal) ---
    warnings: list[str] = []
    if not columns:
        warnings.append("'columns' is empty — the dataset will have no columns")
    if isinstance(n_rows, int) and n_rows < 10:
        warnings.append(f"n_rows is only {n_rows} — very small datasets are hard to grade")
    for col in columns:
        for kind, frac in col.messiness.items():
            if _num(frac) and frac > 0.5:
                warnings.append(f"column '{col.name}': '{kind}' fraction {frac} corrupts most of the column — is that intended?")
    for name, total in messy_totals:
        warnings.append(f"column '{name}': messiness fractions total {total:.2f} — more than half the column "
                        "will be corrupted. Is that intended?")

    return Spec(n_rows=n_rows or 0, seed=seed, columns=columns,
                row_messiness=row_messiness, source=source, warnings=warnings)


def load_spec(path: str) -> Spec:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise TabulousError(f"{path}: cannot read spec file ({e.strerror or e}). "
                            "Create one with `tabulous init`.") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        loc = f"line {mark.line + 1}: " if mark else ""
        raise TabulousError(f"{path}: invalid YAML — {loc}{getattr(e, 'problem', e)}") from None
    return spec_from_data(data, source=path, text=text)


SPEC_TEMPLATE = '''\
# TABulous dataset spec — edit freely, then run:
#   tabulous spec.yaml              # writes ./tabulous_out/
#   tabulous preview spec.yaml      # quick look, no files written
#   tabulous kinds                  # all column types & messiness kinds

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
      missing: 0.05        # empty cells
      out_of_range: 0.02   # e.g. 999 or -1

  - name: height_cm
    type: float
    min: 150
    max: 200
    decimals: 1
    unit: cm               # used by unit_suffix
    messiness:
      missing: 0.03
      unit_suffix: 0.05    # "178.4 cm"

  - name: grade
    type: choice
    options: [A, B, C, D, F]
    messiness:
      missing: 0.04
      case_variation: 0.05 # "a" instead of "A"
      whitespace: 0.03     # " A "
      typo: 0.02           # single-character edit

  - name: enrolled
    type: choice
    options: ["true", "false"]
    messiness:
      inconsistent_encoding: 0.10  # mixes true/True/Y/1/...

  - name: email
    type: string
    pattern: "{first}.{last}@school.edu"   # {first}, {last}, {word} available
    messiness:
      missing: 0.02
      duplicates: 0.03     # same value as another row

  - name: enrolled_date
    type: date
    start: 2023-09-01
    end: 2024-06-30
    format: "%Y-%m-%d"
    messiness:
      missing: 0.02

row_messiness:
  duplicate_rows: 0.02     # fraction of rows duplicated
'''
