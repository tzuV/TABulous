import os

import pytest

from tabulous.cli import main

GOOD_SPEC = """\
n_rows: 20
seed: 3
columns:
  - name: age
    type: int
    min: 18
    max: 35
    messiness:
      missing: 0.1
"""


@pytest.fixture
def spec_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "spec.yaml").write_text(GOOD_SPEC)
    return "spec.yaml"


def _run(capsys, *argv):
    try:
        code = main(list(argv))
    except SystemExit as e:  # argparse exits with 2 on usage errors
        code = e.code if isinstance(e.code, int) else 0
    out, err = capsys.readouterr()
    return code, out + err


def test_end_to_end_cli_produces_files(tmp_path, capsys, spec_file):
    code, _ = _run(capsys, "spec.yaml", "--out", "out", "--seed", "7")
    assert code == 0
    for f in ("out/messy.csv", "out/clean.csv", "out/truth.json"):
        assert os.path.exists(f), f


def test_help_mentions_workflow(capsys):
    code, text = _run(capsys, "--help")
    assert code == 0
    assert "tabulous init" in text
    assert "tabulous spec.yaml" in text
    assert "new-dataset" in text


def test_new_dataset_in_empty_dir(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _ = _run(capsys, "new-dataset", "demo")
    assert code == 0
    for f in ("demo/spec.yaml", "demo/messy.csv", "demo/clean.csv", "demo/truth.json"):
        assert os.path.exists(f), f


def test_kinds_lists_types_and_kinds(capsys):
    code, text = _run(capsys, "kinds")
    assert code == 0
    for t in ("id", "int", "float", "choice", "string", "date"):
        assert t in text
    for k in ("missing", "out_of_range", "unit_suffix", "case_variation", "whitespace",
              "typo", "duplicates", "inconsistent_encoding", "duplicate_rows"):
        assert k in text


def test_check_validates_without_generating(capsys, spec_file, tmp_path):
    code, text = _run(capsys, "check", "spec.yaml")
    assert code == 0
    assert "spec looks good" in text
    assert not os.path.exists("tabulous_out")


def test_preview_writes_no_files(capsys, tmp_path, spec_file):
    before = set(os.listdir("."))
    code, _ = _run(capsys, "preview", "spec.yaml")
    assert code == 0
    assert set(os.listdir(".")) == before


def test_three_errors_reported_at_once_with_lines(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bad.yaml").write_text(
        "n_rows: 10\ncolumns:\n  - name: a\n    type: integr\n    min: 40\n    max: 30\n"
        "    messiness:\n      missingg: 0.5\n")
    code, text = _run(capsys, "bad.yaml")
    assert code == 1
    assert "3 problems" in text
    assert "line 4" in text and "line 5" in text and "line 8" in text
    assert "Did you mean 'missing'?" in text
    assert "Traceback" not in text


def test_rerun_refuses_without_force(capsys, spec_file):
    assert _run(capsys, "spec.yaml", "--out", "out")[0] == 0
    code, text = _run(capsys, "spec.yaml", "--out", "out")
    assert code == 1
    assert "--force" in text
    assert "Traceback" not in text
    assert _run(capsys, "spec.yaml", "--out", "out", "--force")[0] == 0


def test_no_answer_key_student_bundle(capsys, spec_file):
    code, _ = _run(capsys, "spec.yaml", "--out", "out", "--no-answer-key")
    assert code == 0
    assert not os.path.exists("out/truth.json")
    assert os.path.exists("out/messy.csv")


def test_default_out_dir_announced(capsys, spec_file):
    code, text = _run(capsys, "spec.yaml")
    assert code == 0
    assert "tabulous_out" in text
    assert os.path.exists("tabulous_out/messy.csv")


def test_seed_and_reproduce_command_printed(capsys, spec_file):
    code, text = _run(capsys, "spec.yaml", "--out", "out", "--seed", "42")
    assert code == 0
    assert "Seed: 42" in text
    assert "tabulous spec.yaml --out out --seed 42" in text


def test_truth_hint_printed(capsys, spec_file):
    _, text = _run(capsys, "spec.yaml", "--out", "out")
    assert "truth.json" in text


MALFORMED = [
    "n_rows: [unclosed\n",
    "- just\n- a\n- list\n",
    "",
    "n_rows: lots\ncolumns: []\n",
    "n_rows: 5\ncolumns: 5\n",
    "n_rows: 5\ncolumns:\n  - type: int\n",
    "n_rows: 5\ncolumns:\n  - name: a\n    type: 123\n",
    "n_rows: 5\nseed: banana\ncolumns:\n  - name: a\n    type: int\n",
    "n_rows: 5\ncolumns:\n  - name: a\n    type: int\n    messiness: 0.5\n",
    "n_rows: 5\ncolumns:\n  - name: a\n    type: int\n    min: 10\n    max: 1\n",
]


@pytest.mark.parametrize("content", MALFORMED)
def test_fuzz_no_traceback_on_malformed_specs(capsys, tmp_path, monkeypatch, content):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "fuzz.yaml").write_text(content)
    code, text = _run(capsys, "fuzz.yaml")
    assert code == 1
    assert "Traceback" not in text
    assert text.strip()  # always a readable one-line-ish error


def test_fuzz_missing_and_directory_specs(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, text = _run(capsys, "nope.yaml")
    assert code == 1 and "Traceback" not in text and "tabulous init" in text
    code, text = _run(capsys, ".")
    assert code == 1 and "Traceback" not in text
