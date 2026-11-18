"""Schema model, schema parsing and validation for ``.env`` files.

A schema file assigns a *type* to each key::

    DATABASE_URL=url
    PORT=int
    DEBUG=bool
    API_KEY=required
    SLUG=regex:^[a-z0-9-]+$
    NICKNAME?=string      # trailing '?' marks the key optional

Validation compares a parsed :class:`~envfy.parser.EnvFile` against a
:class:`Schema` and produces a :class:`Report` of pass/fail/warning issues.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Pattern, Tuple
from urllib.parse import SplitResult, urlsplit

from .parser import KEY_RE, EnvFile

__all__ = [
    "Issue",
    "Report",
    "Schema",
    "SchemaError",
    "SchemaField",
    "SIMPLE_TYPES",
    "check",
    "infer_schema",
    "load_schema",
    "parse_schema",
    "render_schema",
]

#: Type names that do not carry an inline pattern.
SIMPLE_TYPES = ("string", "int", "float", "bool", "url", "email", "required")

_REGEX_PREFIX = "regex:"
_TRAILING_COMMENT_RE = re.compile(r"[ \t]#")
_INT_RE = re.compile(r"^[+-]?\d+$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*$")


class SchemaError(ValueError):
    """Raised when a ``.env.schema`` line is malformed or unsupported."""

    def __init__(self, message: str, line: Optional[int] = None, path: Optional[Path] = None) -> None:
        self.message = message
        self.line = line
        self.path = path
        super().__init__(self._render())

    def _render(self) -> str:
        location = ""
        if self.path is not None:
            location = str(self.path)
        if self.line is not None:
            location = f"{location}:{self.line}" if location else f"line {self.line}"
        return f"{location}: {self.message}" if location else self.message


@dataclass(frozen=True)
class SchemaField:
    """One ``KEY=type`` declaration from a schema file."""

    key: str
    type: str
    line: int
    optional: bool = False
    pattern: Optional[Pattern[str]] = None
    raw: str = ""

    @property
    def spec(self) -> str:
        """Canonical type string, e.g. ``int`` or ``regex:^\\d+$``."""

        if self.type == "regex" and self.pattern is not None:
            return f"{_REGEX_PREFIX}{self.pattern.pattern}"
        return self.type

    @property
    def required(self) -> bool:
        return not self.optional


@dataclass
class Schema:
    """Ordered collection of :class:`SchemaField` objects."""

    fields: Dict[str, SchemaField] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)
    path: Optional[Path] = None

    def __len__(self) -> int:
        return len(self.order)

    def __iter__(self) -> Iterator[str]:
        return iter(self.order)

    def __contains__(self, key: object) -> bool:
        return key in self.fields

    def __getitem__(self, key: str) -> SchemaField:
        return self.fields[key]

    def get(self, key: str, default: Optional[SchemaField] = None) -> Optional[SchemaField]:
        return self.fields.get(key, default)

    def keys(self) -> List[str]:
        return list(self.order)

    def items(self) -> List[Tuple[str, SchemaField]]:
        return [(key, self.fields[key]) for key in self.order]


@dataclass(frozen=True)
class Issue:
    """A single validation result for one key."""

    level: str  # one of "ok", "warning", "error"
    key: str
    message: str
    line: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        return {"level": self.level, "key": self.key, "line": self.line, "message": self.message}


@dataclass
class Report:
    """Aggregated result of :func:`check`."""

    issues: List[Issue] = field(default_factory=list)
    env_path: Optional[str] = None
    schema_path: Optional[str] = None
    checked: int = 0

    def add(self, level: str, key: str, message: str, line: Optional[int] = None) -> None:
        self.issues.append(Issue(level=level, key=key, message=message, line=line))

    @property
    def errors(self) -> List[Issue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> List[Issue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    @property
    def oks(self) -> List[Issue]:
        return [issue for issue in self.issues if issue.level == "ok"]

    @property
    def has_errors(self) -> bool:
        return any(issue.level == "error" for issue in self.issues)

    @property
    def ok(self) -> bool:
        return not self.has_errors

    def to_dict(self) -> Dict[str, object]:
        return {
            "env": self.env_path,
            "schema": self.schema_path,
            "ok": self.ok,
            "summary": {
                "checked": self.checked,
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "passed": len(self.oks),
            },
            "issues": [issue.to_dict() for issue in self.issues],
        }


def parse_schema(text: str, path: Optional[Path] = None) -> Schema:
    """Parse schema text into a :class:`Schema`.

    Raises:
        SchemaError: On a malformed line, an unknown type, a duplicate key or an
            invalid regular expression.
    """

    schema = Schema(path=path)
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Only treat a whitespace-prefixed '#' *after* the '=' as a trailing
        # comment, so patterns such as ``regex:^#+$`` keep their '#'.
        equals_at = stripped.find("=")
        comment_match = _TRAILING_COMMENT_RE.search(
            stripped, equals_at if equals_at != -1 else 0
        )
        if comment_match:
            stripped = stripped[: comment_match.start()].strip()
        if not stripped:
            continue

        if "=" not in stripped:
            raise SchemaError(f"expected 'KEY=TYPE', got {stripped!r}", lineno, path)

        key_part, _, type_part = stripped.partition("=")
        key = key_part.strip()
        optional = key.endswith("?")
        if optional:
            key = key[:-1].strip()
        if not key:
            raise SchemaError("missing key before '='", lineno, path)
        if not KEY_RE.match(key):
            raise SchemaError(f"invalid key name {key!r}", lineno, path)
        if key in schema.fields:
            raise SchemaError(f"duplicate schema entry for {key!r}", lineno, path)

        schema.fields[key] = _build_field(key, type_part, optional, lineno, path, raw_line)
        schema.order.append(key)
    return schema


def load_schema(path: "Path | str") -> Schema:
    """Read and parse a schema file from disk (UTF-8, BOM tolerant)."""

    resolved = Path(path)
    text = resolved.read_text(encoding="utf-8-sig")
    return parse_schema(text, path=resolved)


def _build_field(
    key: str,
    type_text: str,
    optional: bool,
    lineno: int,
    path: Optional[Path],
    raw: str,
) -> SchemaField:
    spec = type_text.strip()
    if not spec:
        raise SchemaError("missing type after '='", lineno, path)

    lowered = spec.lower()
    if lowered in SIMPLE_TYPES:
        if lowered == "required" and optional:
            raise SchemaError("'required' cannot be combined with a '?' optional marker", lineno, path)
        return SchemaField(key=key, type=lowered, line=lineno, optional=optional, raw=raw)

    if lowered.startswith(_REGEX_PREFIX):
        pattern_text = spec[len(_REGEX_PREFIX):]
        if not pattern_text:
            raise SchemaError("'regex:' requires a pattern", lineno, path)
        try:
            compiled = re.compile(pattern_text)
        except re.error as exc:
            raise SchemaError(f"invalid regular expression {pattern_text!r}: {exc}", lineno, path) from exc
        return SchemaField(
            key=key, type="regex", line=lineno, optional=optional, pattern=compiled, raw=raw
        )

    allowed = ", ".join(SIMPLE_TYPES) + ", regex:<pattern>"
    raise SchemaError(f"unknown type {spec!r} (expected one of: {allowed})", lineno, path)


def check(
    env: EnvFile,
    schema: Schema,
    allow_extra: bool = False,
    *,
    env_path: Optional[str] = None,
    schema_path: Optional[str] = None,
) -> Report:
    """Validate ``env`` against ``schema``.

    Args:
        env: Parsed environment file.
        schema: Parsed schema.
        allow_extra: When true, keys that are not declared in the schema are
            ignored instead of producing a warning.
        env_path: Optional label for reports.
        schema_path: Optional label for reports.

    Returns:
        A :class:`Report`; ``report.has_errors`` tells whether the run failed.
    """

    report = Report(
        env_path=env_path if env_path is not None else (str(env.path) if env.path else None),
        schema_path=schema_path
        if schema_path is not None
        else (str(schema.path) if schema.path else None),
    )

    for key in schema.order:
        field = schema[key]
        report.checked += 1
        entry = env.get(key)
        if entry is None:
            if field.optional:
                continue
            report.add("error", key, "missing required key")
            continue
        if entry.value == "":
            if field.optional:
                continue
            report.add("error", key, "value is empty", entry.line)
            continue
        problem = _type_error(entry.value, field)
        if problem is not None:
            report.add("error", key, problem, entry.line)
        else:
            report.add("ok", key, f"valid {field.spec}", entry.line)

    if not allow_extra:
        for key in env.order:
            if key in schema:
                continue
            entry = env.entries[key]
            report.add("warning", key, "key is not declared in schema", entry.line)

    return report


def _type_error(value: str, field: SchemaField) -> Optional[str]:
    kind = field.type
    if kind in ("string", "required"):
        return None
    if kind == "int":
        if _INT_RE.match(value) is None:
            return f"expected int, got {_preview(value)}"
        return None
    if kind == "float":
        try:
            number = float(value)
        except ValueError:
            return f"expected float, got {_preview(value)}"
        if not math.isfinite(number):
            return f"expected finite float, got {_preview(value)}"
        return None
    if kind == "bool":
        if value.lower() not in _TRUE_VALUES and value.lower() not in _FALSE_VALUES:
            return f"expected bool (true/false/1/0/yes/no/on/off), got {_preview(value)}"
        return None
    if kind == "url":
        parts = _urlsplit(value)
        if (
            parts is None
            or not parts.scheme
            or _SCHEME_RE.match(parts.scheme) is None
            or not parts.netloc
            or any(char.isspace() for char in value)
        ):
            return f"expected url (e.g. https://host), got {_preview(value)}"
        return None
    if kind == "email":
        if _EMAIL_RE.match(value) is None:
            return f"expected email address, got {_preview(value)}"
        return None
    if kind == "regex":
        if field.pattern is None:
            return "invalid regex field (no compiled pattern)"
        if field.pattern.fullmatch(value) is None:
            return f"value does not match regex {field.pattern.pattern!r}: {_preview(value)}"
        return None
    return f"unsupported type {kind!r}"


def _urlsplit(value: str) -> Optional[SplitResult]:
    """Parse a URL, returning ``None`` for values the standard library rejects."""

    try:
        return urlsplit(value)
    except ValueError:
        return None


def _preview(value: str, limit: int = 40) -> str:
    shown = value if len(value) <= limit else value[:limit] + "..."
    return repr(shown)


def infer_schema(env: EnvFile) -> Schema:
    """Infer a :class:`Schema` from an example ``.env`` file.

    Keys with a non-empty value become ``string``; keys with an empty value
    become ``required`` (a non-empty string is expected).
    """

    schema = Schema()
    for key in env.order:
        entry = env.entries[key]
        field_type = "string" if entry.value != "" else "required"
        schema.fields[key] = SchemaField(key=key, type=field_type, line=entry.line)
        schema.order.append(key)
    return schema


def render_schema(schema: Schema, header: Optional[str] = None) -> str:
    """Render a :class:`Schema` back to ``.env.schema`` text."""

    lines: List[str] = []
    if header:
        for header_line in header.splitlines():
            lines.append(f"# {header_line}".rstrip())
        lines.append("")
    for key in schema.order:
        field = schema[key]
        name = f"{key}?" if field.optional else key
        lines.append(f"{name}={field.spec}")
    return "\n".join(lines) + "\n"
