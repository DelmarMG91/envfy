"""Comparison of two ``.env`` files.

:func:`compare` reports which keys appear only in the first file, which appear
only in the second, and which are present in both but carry different values.

Values are **never** exposed: a changed key is only ever rendered as
``<changed>``.  This keeps secrets out of logs and CI output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .parser import EnvFile

__all__ = ["DiffResult", "compare", "format_diff"]


@dataclass
class DiffResult:
    """The set-level difference between two environment files."""

    only_in_a: List[str] = field(default_factory=list)
    only_in_b: List[str] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)

    @property
    def identical(self) -> bool:
        return not (self.only_in_a or self.only_in_b or self.changed)

    @property
    def total(self) -> int:
        return len(self.only_in_a) + len(self.only_in_b) + len(self.changed)

    def to_dict(self) -> Dict[str, object]:
        """JSON-serialisable view; contains keys only, never values."""

        return {
            "only_in_a": self.only_in_a,
            "only_in_b": self.only_in_b,
            "changed": self.changed,
            "identical": self.identical,
        }


def compare(left: EnvFile, right: EnvFile) -> DiffResult:
    """Compare two :class:`~envfy.parser.EnvFile` objects.

    The returned lists are sorted so output is deterministic.
    """

    left_keys = set(left.keys())
    right_keys = set(right.keys())

    only_in_a = sorted(left_keys - right_keys)
    only_in_b = sorted(right_keys - left_keys)
    changed = sorted(
        key
        for key in left_keys & right_keys
        if left.entries[key].value != right.entries[key].value
    )
    return DiffResult(only_in_a=only_in_a, only_in_b=only_in_b, changed=changed)


def format_diff(result: DiffResult, label_a: str, label_b: str) -> str:
    """Render a human-readable diff.  Values are masked as ``<changed>``."""

    lines: List[str] = [f"envfy diff  {label_a} vs {label_b}"]
    if result.identical:
        lines.append("✓ files are equivalent (no key differences)")
        return "\n".join(lines)

    if result.only_in_a:
        lines.append(f"only in {label_a}:")
        lines.extend(f"  - {key}" for key in result.only_in_a)
    if result.only_in_b:
        lines.append(f"only in {label_b}:")
        lines.extend(f"  + {key}" for key in result.only_in_b)
    if result.changed:
        lines.append("changed (values hidden):")
        lines.extend(f"  ~ {key}  <changed>" for key in result.changed)

    lines.append("")
    lines.append(f"{result.total} difference(s)")
    return "\n".join(lines)
