"""Tests for the command line interface."""

import json

import pytest

from envfy import __version__
from envfy.cli import main
from envfy.validator import parse_schema


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "check" in out
    assert "diff" in out
    assert "init" in out
    assert "Validate and diff" in out


def test_check_cli_fails_on_errors(tmp_path, capsys):
    env = _write(tmp_path, ".env", "PORT=abc\n")
    schema = _write(tmp_path, ".env.schema", "PORT=int\nAPI_KEY=required\n")
    code = main(["check", "--env", str(env), "--schema", str(schema)])
    assert code == 1
    out = capsys.readouterr().out
    assert "✗ PORT (line 1): expected int" in out
    assert "missing required key" in out
    assert "2 error(s)" in out


def test_check_cli_json_payload(tmp_path, capsys):
    env = _write(tmp_path, ".env", "PORT=8080\nAPI_KEY=abc\nEXTRA=1\n")
    schema = _write(tmp_path, ".env.schema", "PORT=int\nAPI_KEY=required\n")
    code = main(["check", "--env", str(env), "--schema", str(schema), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["summary"] == {"checked": 2, "errors": 0, "warnings": 1, "passed": 2}
    assert payload["issues"][-1]["key"] == "EXTRA"


def test_check_cli_allow_extra_silences_warning(tmp_path, capsys):
    env = _write(tmp_path, ".env", "PORT=8080\nEXTRA=1\n")
    schema = _write(tmp_path, ".env.schema", "PORT=int\n")
    code = main(["check", "--env", str(env), "--schema", str(schema), "--allow-extra"])
    out = capsys.readouterr().out
    assert code == 0
    assert "EXTRA" not in out
    assert "all 1 key(s) passed" in out


def test_diff_cli_masks_values(tmp_path, capsys):
    left = _write(tmp_path, "a.env", "TOKEN=aaa\nSHARED=1\n")
    right = _write(tmp_path, "b.env", "TOKEN=bbb\nSHARED=1\n")
    code = main(["diff", str(left), str(right), "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 1
    assert payload["changed"] == ["TOKEN"]
    assert "aaa" not in out
    assert "bbb" not in out


def test_diff_cli_identical_returns_zero(tmp_path, capsys):
    left = _write(tmp_path, "a.env", "A=1\n")
    right = _write(tmp_path, "b.env", "A=1\n")
    code = main(["diff", str(left), str(right)])
    assert code == 0
    assert "equivalent" in capsys.readouterr().out


def test_init_cli_infers_schema(tmp_path, capsys):
    example = _write(tmp_path, "example.env", "API_URL=https://api.test\nEMPTY=\n")
    output = tmp_path / "generated.schema"
    code = main(["init", "--env", str(example), "--output", str(output)])
    assert code == 0
    text = output.read_text(encoding="utf-8")
    assert "API_URL=string" in text
    assert "EMPTY=required" in text
    assert "wrote 2 field(s)" in capsys.readouterr().out
    assert parse_schema(text).keys() == ["API_URL", "EMPTY"]


def test_missing_file_returns_usage_error(tmp_path, capsys):
    code = main(
        [
            "check",
            "--env",
            str(tmp_path / "nope.env"),
            "--schema",
            str(tmp_path / "nope.schema"),
        ]
    )
    assert code == 2
    assert "error" in capsys.readouterr().err


def test_bad_schema_returns_usage_error(tmp_path, capsys):
    env = _write(tmp_path, ".env", "A=1\n")
    schema = _write(tmp_path, ".env.schema", "A=nope\n")
    assert main(["check", "--env", str(env), "--schema", str(schema)]) == 2
    assert "unknown type" in capsys.readouterr().err
