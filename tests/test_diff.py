"""Tests for the .env diff engine."""

import json

from envfy.diff import compare, format_diff
from envfy.parser import parse_env


def test_compare_reports_all_categories():
    left = parse_env("SHARED=1\nONLY_A=x\nCHANGED=old\n")
    right = parse_env("SHARED=1\nONLY_B=y\nCHANGED=new\n")
    result = compare(left, right)
    assert result.only_in_a == ["ONLY_A"]
    assert result.only_in_b == ["ONLY_B"]
    assert result.changed == ["CHANGED"]
    assert result.total == 3
    assert result.identical is False


def test_compare_never_exposes_values():
    left = parse_env("SECRET=super-secret-a\n")
    right = parse_env("SECRET=super-secret-b\n")
    result = compare(left, right)

    payload = json.dumps(result.to_dict())
    assert "super-secret" not in payload

    rendered = format_diff(result, ".env.a", ".env.b")
    assert "super-secret" not in rendered
    assert "<changed>" in rendered
    assert "~ SECRET" in rendered


def test_compare_identical_files():
    left = parse_env("A=1\nB=2\n")
    right = parse_env("B=2\nA=1\n")
    result = compare(left, right)
    assert result.identical is True
    assert result.total == 0
    assert "equivalent" in format_diff(result, "a.env", "b.env")


def test_compare_ignores_ordering_and_comments():
    left = parse_env("# comment\nA=1\n\nB=2\n")
    right = parse_env("B=2\nA=1 # inline comment\n")
    assert compare(left, right).identical is True
