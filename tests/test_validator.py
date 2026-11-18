"""Tests for schema parsing and validation."""

import pytest

from envfy.parser import parse_env
from envfy.validator import (
    SchemaError,
    check,
    infer_schema,
    parse_schema,
    render_schema,
)

FULL_SCHEMA = """\
# Full example schema
DATABASE_URL=url
PORT=int
DEBUG=bool
RATIO=float
CONTACT=email
SLUG=regex:^[a-z0-9-]+$
API_KEY=required
NICKNAME?=string
"""


def test_schema_parses_all_types_and_comments():
    schema = parse_schema(FULL_SCHEMA)
    assert schema.keys() == [
        "DATABASE_URL",
        "PORT",
        "DEBUG",
        "RATIO",
        "CONTACT",
        "SLUG",
        "API_KEY",
        "NICKNAME",
    ]
    assert schema["PORT"].type == "int"
    assert schema["SLUG"].type == "regex"
    assert schema["SLUG"].pattern is not None
    assert schema["NICKNAME"].optional is True
    assert schema["API_KEY"].optional is False


def test_valid_env_passes():
    env = parse_env(
        "DATABASE_URL=https://db.example.com\n"
        "PORT=5432\n"
        "DEBUG=yes\n"
        "RATIO=0.75\n"
        "CONTACT=dev@example.com\n"
        "SLUG=my-service-1\n"
        "API_KEY=secret\n"
    )
    report = check(env, parse_schema(FULL_SCHEMA))
    assert report.errors == []
    assert report.warnings == []
    assert len(report.oks) == 7
    assert report.ok is True


def test_missing_required_key_is_reported():
    schema = parse_schema("API_KEY=required\nPORT=int\n")
    env = parse_env("PORT=8080\n")
    report = check(env, schema)
    assert [(issue.level, issue.key) for issue in report.errors] == [("error", "API_KEY")]
    assert "missing required key" in report.errors[0].message
    assert report.has_errors is True


@pytest.mark.parametrize(
    ("schema_line", "value", "expected"),
    [
        ("PORT=int", "abc", "expected int"),
        ("PORT=int", "1.5", "expected int"),
        ("DEBUG=bool", "maybe", "expected bool"),
        ("RATIO=float", "1.2.3", "expected float"),
        ("HOMEPAGE=url", "example.com", "expected url"),
        ("MAIL=email", "not-an-email", "expected email"),
        ("SLUG=regex:^[a-z]+$", "ABC", "does not match regex"),
    ],
)
def test_type_errors(schema_line, value, expected):
    schema = parse_schema(schema_line + "\n")
    key = schema_line.split("=", 1)[0]
    env = parse_env(f"{key}={value}\n")
    report = check(env, schema)
    assert len(report.errors) == 1
    assert expected in report.errors[0].message
    assert report.errors[0].line == 1


def test_url_accepts_any_scheme_with_host():
    schema = parse_schema("DB=url\nWEB=url\n")
    env = parse_env("DB=postgres://user@localhost:5432/app\nWEB=https://example.com/x\n")
    report = check(env, schema)
    assert report.errors == []
    assert len(report.oks) == 2


def test_regex_pattern_may_contain_hash_and_trailing_comment():
    schema = parse_schema("TAG=regex:^#[a-z]+$   # a leading-hash tag\n")
    assert schema["TAG"].pattern is not None
    assert schema["TAG"].pattern.pattern == "^#[a-z]+$"

    env = parse_env("TAG=#release\n")
    assert check(env, schema).errors == []


def test_optional_key_may_be_missing_or_empty():
    schema = parse_schema("NICKNAME?=string\nLIMIT?=int\n")
    env = parse_env("NICKNAME=\n")
    report = check(env, schema)
    assert report.errors == []
    assert report.warnings == []
    assert report.checked == 2


def test_empty_required_value_is_reported():
    schema = parse_schema("API_KEY=required\n")
    env = parse_env("API_KEY=\n")
    report = check(env, schema)
    assert len(report.errors) == 1
    assert report.errors[0].message == "value is empty"


def test_extra_keys_warn_unless_allowed():
    schema = parse_schema("PORT=int\n")
    env = parse_env("PORT=1\nEXTRA=x\n")
    report = check(env, schema)
    assert [issue.key for issue in report.warnings] == ["EXTRA"]
    assert report.has_errors is False

    relaxed = check(env, schema, allow_extra=True)
    assert relaxed.warnings == []
    assert relaxed.ok is True


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("PORT=integer\n", "unknown type"),
        ("PORT\n", "expected 'KEY=TYPE'"),
        ("KEY?=required\n", "cannot be combined"),
        ("SLUG=regex:[a-\n", "invalid regular expression"),
        ("SLUG=regex:\n", "requires a pattern"),
        ("PORT=\n", "missing type"),
        ("PORT=int\nPORT=string\n", "duplicate schema entry"),
    ],
)
def test_bad_schema_raises(text, needle):
    with pytest.raises(SchemaError) as excinfo:
        parse_schema(text)
    assert needle in str(excinfo.value)
    assert excinfo.value.line is not None


def test_infer_schema_and_render_round_trip():
    env = parse_env("API_URL=https://api.test\nEMPTY=\n")
    schema = infer_schema(env)
    assert schema["API_URL"].type == "string"
    assert schema["EMPTY"].type == "required"

    text = render_schema(schema, header="generated")
    assert text.startswith("# generated\n")
    assert "API_URL=string" in text
    assert "EMPTY=required" in text
    assert parse_schema(text).keys() == ["API_URL", "EMPTY"]
