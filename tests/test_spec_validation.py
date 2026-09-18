import pytest

from tabulous import TabulousError, load_spec
from tabulous.spec import spec_from_data


def test_min_greater_than_max(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("n_rows: 10\ncolumns:\n  - name: age\n    type: int\n    min: 40\n    max: 30\n")
    with pytest.raises(TabulousError) as e:
        load_spec(str(p))
    assert "'min' (40) is greater than 'max' (30)" in str(e.value)
    assert "swap" in str(e.value)


def test_unknown_type_suggests():
    with pytest.raises(TabulousError) as e:
        spec_from_data({"n_rows": 5, "columns": [{"name": "a", "type": "integr"}]})
    assert "Did you mean 'int'?" in str(e.value)


def test_unknown_messiness_kind_suggests():
    with pytest.raises(TabulousError) as e:
        spec_from_data({"n_rows": 5, "columns": [{"name": "a", "type": "int", "min": 0, "max": 1,
                                                  "messiness": {"missingg": 0.5}}]})
    assert "Did you mean 'missing'?" in str(e.value)


def test_unknown_top_level_key_suggests():
    with pytest.raises(TabulousError) as e:
        spec_from_data({"n_rows": 5, "columns": [], "seeed": 1})
    assert "Did you mean 'seed'?" in str(e.value)


def test_fraction_out_of_range():
    with pytest.raises(TabulousError) as e:
        spec_from_data({"n_rows": 5, "columns": [{"name": "a", "type": "int", "min": 0, "max": 1,
                                                  "messiness": {"missing": 1.5}}]})
    assert "in [0, 1]" in str(e.value)


def test_duplicate_column_names():
    with pytest.raises(TabulousError) as e:
        spec_from_data({"n_rows": 5, "columns": [{"name": "a", "type": "int"},
                                                 {"name": "a", "type": "int"}]})
    assert "duplicate column name 'a'" in str(e.value)


def test_n_rows_required_not_guessed():
    with pytest.raises(TabulousError) as e:
        spec_from_data({"columns": [{"name": "a", "type": "int"}]})
    assert "'n_rows' is required" in str(e.value)


def test_choice_requires_options():
    with pytest.raises(TabulousError) as e:
        spec_from_data({"n_rows": 5, "columns": [{"name": "a", "type": "choice"}]})
    assert "'options'" in str(e.value)


def test_all_problems_reported_at_once_with_lines(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(
        "n_rows: 10\n"                       # 1
        "columns:\n"                          # 2
        "  - name: a\n"                       # 3
        "    type: integr\n"                  # 4
        "    min: 40\n"                       # 5
        "    max: 30\n"                       # 6
        "    messiness:\n"                    # 7
        "      missingg: 0.5\n"               # 8
        "  - name: a\n"                       # 9
        "    type: nope\n"                    # 10
    )
    with pytest.raises(TabulousError) as e:
        load_spec(str(p))
    msg = str(e.value)
    assert "5 problems" in msg
    assert "line 4" in msg and "unknown type" in msg
    assert "line 5" in msg and "greater than 'max'" in msg
    assert "line 8" in msg and "missingg" in msg
    assert "line 9" in msg and "duplicate column name" in msg
    assert "line 10" in msg and "unknown type" in msg


def test_malformed_yaml_no_traceback_text(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("n_rows: [unclosed\n")
    with pytest.raises(TabulousError) as e:
        load_spec(str(p))
    assert "invalid YAML" in str(e.value)


def test_kind_wrong_for_type():
    with pytest.raises(TabulousError) as e:
        spec_from_data({"n_rows": 5, "columns": [{"name": "a", "type": "id",
                                                  "messiness": {"out_of_range": 0.1}}]})
    assert "not supported for type 'id'" in str(e.value)


def test_inconsistent_encoding_needs_boolean_options():
    with pytest.raises(TabulousError) as e:
        spec_from_data({"n_rows": 5, "columns": [{"name": "a", "type": "choice", "options": ["A", "B"],
                                                  "messiness": {"inconsistent_encoding": 0.1}}]})
    assert "boolean-like" in str(e.value)


def test_starter_template_validates():
    import yaml
    from tabulous.spec import SPEC_TEMPLATE
    spec = spec_from_data(yaml.safe_load(SPEC_TEMPLATE))
    assert len(spec.columns) == 7
