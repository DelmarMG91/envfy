"""envfy — validate and diff .env files against a schema.

The public API mirrors the CLI::

    from envfy import parse_env, parse_schema, check, compare

    env = parse_env("PORT=8080\\n")
    schema = parse_schema("PORT=int\\n")
    report = check(env, schema)
"""

from .diff import DiffResult, compare, format_diff
from .parser import EnvEntry, EnvFile, EnvParseError, load_env, parse_env
from .validator import (
    Issue,
    Report,
    Schema,
    SchemaError,
    SchemaField,
    check,
    infer_schema,
    load_schema,
    parse_schema,
    render_schema,
)

__version__ = "0.1.0"

__all__ = [
    "DiffResult",
    "EnvEntry",
    "EnvFile",
    "EnvParseError",
    "Issue",
    "Report",
    "Schema",
    "SchemaError",
    "SchemaField",
    "__version__",
    "check",
    "compare",
    "format_diff",
    "infer_schema",
    "load_env",
    "load_schema",
    "parse_env",
    "parse_schema",
    "render_schema",
]
