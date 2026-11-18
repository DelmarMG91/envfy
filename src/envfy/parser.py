"""Parser for ``.env`` files.

The parser understands the practical subset of the dotenv format that matters
for configuration validation:

* ``KEY=VALUE`` assignments and ``export KEY=VALUE``
* blank lines and whole-line ``#`` comments
* single-quoted and double-quoted values
* trailing ``#`` comments on unquoted values (a ``#`` preceded by whitespace)
* ``\\n``, ``\\r``, ``\\t``, ``\\"`` and ``\\\\`` escapes inside double quotes

Every entry keeps the line number it was defined on so that later validation
can point at the offending line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

__all__ = ["EnvEntry", "EnvFile", "EnvParseError", "KEY_RE", "load_env", "parse_env"]

#: Valid key names: start with a letter or underscore, then letters, digits,
#: underscores or dots.  Dots are allowed to support namespaced keys such as
#: ``DB.HOST`` which some toolchains use.
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

_EXPORT_RE = re.compile(r"export\s+")
_TRAILING_COMMENT_RE = re.compile(r"[ \t]#")

#: Escape sequences expanded inside double-quoted values only.
_DOUBLE_QUOTE_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    '"': '"',
    "\\": "\\",
}


class EnvParseError(ValueError):
    """Raised when a ``.env`` line cannot be parsed.

    The exception carries the offending ``line`` number and, when known, the
    ``path`` of the file being parsed so callers can render a helpful message.
    """

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
class EnvEntry:
    """A single parsed ``KEY=VALUE`` assignment."""

    key: str
    value: str
    line: int
    raw: str
    quoted: Optional[str] = None
    exported: bool = False

    def __str__(self) -> str:
        return f"{self.key}={self.value!r} (line {self.line})"


@dataclass
class EnvFile:
    """An ordered collection of :class:`EnvEntry` objects.

    ``entries`` maps a key to its *last* assignment, ``order`` preserves the
    first-seen order of keys and ``duplicates`` records keys that were assigned
    more than once.
    """

    entries: Dict[str, EnvEntry] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    path: Optional[Path] = None

    def __len__(self) -> int:
        return len(self.order)

    def __iter__(self) -> Iterator[str]:
        return iter(self.order)

    def __contains__(self, key: object) -> bool:
        return key in self.entries

    def __getitem__(self, key: str) -> EnvEntry:
        return self.entries[key]

    def get(self, key: str, default: Optional[EnvEntry] = None) -> Optional[EnvEntry]:
        return self.entries.get(key, default)

    def keys(self) -> List[str]:
        return list(self.order)

    def values(self) -> List[EnvEntry]:
        return [self.entries[key] for key in self.order]

    def items(self) -> List[Tuple[str, EnvEntry]]:
        return [(key, self.entries[key]) for key in self.order]

    def as_dict(self) -> Dict[str, str]:
        """Return a plain ``{key: value}`` mapping (last assignment wins)."""

        return {key: self.entries[key].value for key in self.order}


def parse_env(text: str, path: Optional[Path] = None) -> EnvFile:
    """Parse dotenv ``text`` into an :class:`EnvFile`.

    Args:
        text: Full contents of a ``.env`` file.
        path: Optional path used only for error messages.

    Raises:
        EnvParseError: If a non-comment line is malformed.
    """

    env = EnvFile(path=path)
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        entry = _parse_line(raw_line, lineno, path)
        if entry is None:
            continue
        if entry.key in env.entries:
            if entry.key not in env.duplicates:
                env.duplicates.append(entry.key)
            env.entries[entry.key] = entry
        else:
            env.entries[entry.key] = entry
            env.order.append(entry.key)
    return env


def load_env(path: "Path | str") -> EnvFile:
    """Read and parse a ``.env`` file from disk (UTF-8, BOM tolerant)."""

    resolved = Path(path)
    text = resolved.read_text(encoding="utf-8-sig")
    return parse_env(text, path=resolved)


def _parse_line(line: str, lineno: int, path: Optional[Path]) -> Optional[EnvEntry]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    body = line.lstrip()
    exported = False
    export_match = _EXPORT_RE.match(body)
    if export_match:
        exported = True
        body = body[export_match.end():]

    if "=" not in body:
        raise EnvParseError(f"expected 'KEY=VALUE', got {body.strip()!r}", lineno, path)

    key_part, _, value_part = body.partition("=")
    key = key_part.strip()
    if not key:
        raise EnvParseError("missing key before '='", lineno, path)
    if not KEY_RE.match(key):
        raise EnvParseError(f"invalid key name {key!r}", lineno, path)

    value, quoted = _parse_value(value_part, lineno, path)
    return EnvEntry(
        key=key,
        value=value,
        line=lineno,
        raw=line,
        quoted=quoted,
        exported=exported,
    )


def _parse_value(text: str, lineno: int, path: Optional[Path]) -> Tuple[str, Optional[str]]:
    candidate = text.lstrip()

    if candidate.startswith('"'):
        value, remainder = _read_quoted(candidate, '"', lineno, path)
        _ensure_trailing(remainder, lineno, path)
        return value, '"'
    if candidate.startswith("'"):
        value, remainder = _read_quoted(candidate, "'", lineno, path)
        _ensure_trailing(remainder, lineno, path)
        return value, "'"

    match = _TRAILING_COMMENT_RE.search(text)
    if match:
        return text[: match.start()].strip(), None
    return text.strip(), None


def _read_quoted(text: str, quote: str, lineno: int, path: Optional[Path]) -> Tuple[str, str]:
    chars: List[str] = []
    index = 1
    length = len(text)
    while index < length:
        char = text[index]
        if quote == '"' and char == "\\" and index + 1 < length:
            nxt = text[index + 1]
            chars.append(_DOUBLE_QUOTE_ESCAPES.get(nxt, "\\" + nxt))
            index += 2
            continue
        if char == quote:
            return "".join(chars), text[index + 1:]
        chars.append(char)
        index += 1
    label = "double" if quote == '"' else "single"
    raise EnvParseError(f"unterminated {label}-quoted value", lineno, path)


def _ensure_trailing(remainder: str, lineno: int, path: Optional[Path]) -> None:
    tail = remainder.strip()
    if tail and not tail.startswith("#"):
        raise EnvParseError(
            f"unexpected characters after closing quote: {tail!r}", lineno, path
        )
