"""Tests for the .env parser."""

import pytest

from envfy.parser import EnvParseError, load_env, parse_env


def test_parse_plain_assignments_and_comments():
    text = "# leading comment\n\nAPI_URL=https://example.com\nDEBUG=false\n"
    env = parse_env(text)
    assert env.as_dict() == {"API_URL": "https://example.com", "DEBUG": "false"}
    assert env.keys() == ["API_URL", "DEBUG"]
    assert len(env) == 2


def test_parse_export_prefix_and_whitespace():
    env = parse_env("export TOKEN=abc123\n  SPACED = value \n")
    assert env["TOKEN"].exported is True
    assert env["TOKEN"].value == "abc123"
    assert env["SPACED"].value == "value"
    assert env["SPACED"].exported is False


def test_parse_double_quotes_unescape_newlines():
    env = parse_env('MULTI="line1\\nline2"\nQUOTED="say \\"hi\\""\nTABBED="a\\tb"\n')
    assert env["MULTI"].value == "line1\nline2"
    assert env["QUOTED"].value == 'say "hi"'
    assert env["TABBED"].value == "a\tb"
    assert env["MULTI"].quoted == '"'


def test_parse_single_quotes_are_literal():
    env = parse_env("LITERAL='a\\nb'\n")
    assert env["LITERAL"].value == "a\\nb"
    assert env["LITERAL"].quoted == "'"


def test_parse_trailing_comments():
    text = (
        "PLAIN=value # trailing comment\n"
        "HASH=value#nospace\n"
        "EMPTY_COMMENT= # only a comment\n"
        'QUOTED="keep # this" # and drop this\n'
    )
    env = parse_env(text)
    assert env["PLAIN"].value == "value"
    assert env["HASH"].value == "value#nospace"
    assert env["EMPTY_COMMENT"].value == ""
    assert env["QUOTED"].value == "keep # this"


def test_line_numbers_are_preserved():
    text = "# header\n\nFOO=1\n# note\nBAR=2\n"
    env = parse_env(text)
    assert env["FOO"].line == 3
    assert env["BAR"].line == 5


def test_missing_equals_raises_with_line_number():
    with pytest.raises(EnvParseError) as excinfo:
        parse_env("GOOD=1\nBROKEN\n")
    assert excinfo.value.line == 2
    assert "line 2" in str(excinfo.value)


def test_unterminated_quote_raises():
    with pytest.raises(EnvParseError) as excinfo:
        parse_env('A="oops\n')
    assert "unterminated" in str(excinfo.value)
    assert excinfo.value.line == 1


def test_characters_after_closing_quote_raise():
    with pytest.raises(EnvParseError) as excinfo:
        parse_env('A="x" junk\n')
    assert "after closing quote" in str(excinfo.value)


def test_duplicate_keys_last_wins():
    env = parse_env("DUP=1\nDUP=2\n")
    assert env["DUP"].value == "2"
    assert env.duplicates == ["DUP"]
    assert env.keys() == ["DUP"]


def test_invalid_key_raises():
    with pytest.raises(EnvParseError) as excinfo:
        parse_env("1BAD=x\n")
    assert "invalid key" in str(excinfo.value)


def test_load_env_reads_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=1\nB=\"two words\"\n", encoding="utf-8")
    env = load_env(path)
    assert env.as_dict() == {"A": "1", "B": "two words"}
    assert env.path == path
