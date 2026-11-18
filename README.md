# envfy

**Validate and diff your `.env` files against a schema — fast, offline, zero dependencies.**

[![CI](https://github.com/DelmarMG91/envfy/actions/workflows/ci.yml/badge.svg)](https://github.com/DelmarMG91/envfy/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/badge/pypi-v0.1.0-informational.svg)](https://pypi.org/project/envfy/)

`envfy` is a small command line tool that keeps `.env` files honest. Write down
the shape of your configuration once in a `.env.schema`, then let `envfy` catch
missing keys, unexpected keys, wrong types and empty values before they reach
production. It can also diff two `.env` files without ever printing a secret.

## Features

- **Schema validation** — declare a type for every key and fail fast on missing,
  empty or malformed values.
- **Rich type set** — `string`, `int`, `float`, `bool`, `url`, `email`,
  `regex:<pattern>` and `required`, with optional (`?`) keys.
- **Line-aware errors** — every problem points back at the exact line in the
  `.env` or `.env.schema` file.
- **Secret-safe diff** — compare two files and see which keys changed; values are
  only ever rendered as `<changed>`.
- **Schema inference** — bootstrap a schema from an existing `.env.example`
  with `envfy init`.
- **Human and JSON output** — readable report by default, `--json` for CI.
- **Standard library only** — no runtime dependencies, works on Windows and Unix.

## Install

```bash
pip install envfy
```

Or from a checkout, for development:

```bash
git clone https://github.com/DelmarMG91/envfy.git
cd envfy
pip install -e ".[dev]"
```

## Quick Start

```bash
# 1. Describe the shape of your configuration
cat > .env.schema <<'EOF'
DATABASE_URL=url
PORT=int
DEBUG=bool
API_KEY=required
NICKNAME?=string
EOF

# 2. Validate your .env against it
envfy check --env .env --schema .env.schema
```

With a matching `.env` such as:

```dotenv
DATABASE_URL=https://db.example.com
PORT=5432
DEBUG=true
API_KEY=change-me
```

If everything lines up:

```text
envfy check  .env vs .env.schema
✓ DATABASE_URL (line 1): valid url
✓ PORT (line 2): valid int
✓ DEBUG (line 3): valid bool
✓ API_KEY (line 4): valid required

✓ all 5 key(s) passed (0 warning(s))
```

If something is wrong, `envfy` tells you exactly what and where, and exits with
a non-zero status:

```text
envfy check  .env.broken vs .env.schema
✗ DATABASE_URL (line 1): expected url (e.g. https://host), got 'not a url'
✗ PORT (line 2): expected int, got 'not-a-port'
✗ DEBUG (line 3): expected bool (true/false/1/0/yes/no/on/off), got 'maybe'
✗ API_KEY: missing required key
! LEGACY_FLAG (line 4): key is not declared in schema

✗ 4 error(s), 1 warning(s), 5 key(s) checked
```

## Usage

### `envfy check` — validate a `.env` file

```bash
envfy check --env .env --schema .env.schema
envfy check --env .env.production --schema .env.schema --allow-extra
envfy check --env .env --schema .env.schema --json
```

`check` prints one line per key, using three result markers:

| Marker | Meaning |
| ------ | ------- |
| `✓` | the key is present and has the declared type |
| `✗` | a missing required key, an empty value, or a type mismatch (an **error**) |
| `!` | a key that exists in the file but not in the schema (a **warning**) |

A run exits `1` if at least one **error** was found. Warnings alone do not fail
the run. Pass `--allow-extra` to turn the "key not declared in schema" warnings
off entirely.

JSON output (with `--json`) looks like this:

```json
{
  "env": ".env",
  "schema": ".env.schema",
  "ok": false,
  "summary": {
    "checked": 5,
    "errors": 1,
    "warnings": 1,
    "passed": 3
  },
  "issues": [
    { "level": "ok", "key": "DATABASE_URL", "line": 1, "message": "valid url" },
    { "level": "error", "key": "PORT", "line": 2, "message": "expected int, got 'not-a-port'" },
    { "level": "ok", "key": "DEBUG", "line": 3, "message": "valid bool" },
    { "level": "ok", "key": "API_KEY", "line": 4, "message": "valid required" },
    { "level": "warning", "key": "LEGACY_FLAG", "line": 5, "message": "key is not declared in schema" }
  ]
}
```

### `envfy diff` — compare two `.env` files

```bash
envfy diff .env.a .env.b
```

```text
envfy diff  .env.a vs .env.b
only in .env.a:
  - API_KEY
only in .env.b:
  + API_KEY_EXAMPLE
changed (values hidden):
  ~ DATABASE_URL  <changed>

3 difference(s)
```

Values are **never** printed — a changed key is always shown as `<changed>` so
the command is safe to run in CI logs and pull requests. `diff` exits `1` when the
two files differ and `0` when they are equivalent.

### `envfy init` — infer a schema from an example file

```bash
envfy init --env .env.example --output .env.schema
```

```text
✓ wrote 5 field(s) to .env.schema
```

Each key with a non-empty value becomes `string`; each key with an empty value
becomes `required`. Review the generated file and tighten the types (`int`,
`url`, …) as needed.

## `.env` format

`envfy` understands the common dotenv subset used by configuration files:

```dotenv
# Comments and blank lines are ignored

APP_NAME=envfy                    # unquoted values may end with a comment
export DATABASE_URL=postgres://localhost:5432/app
MULTILINE="first line\nsecond line"   # \n, \r, \t, \" and \\ are expanded
LITERAL='keeps \n as-is'             # single quotes are literal
EMPTY=
```

- `export KEY=value` is accepted interchangeably with `KEY=value`.
- In an **unquoted** value, a `#` that follows whitespace starts a comment.
- Inside **double quotes**, `\n`, `\r`, `\t`, `\"` and `\\` are expanded; inside
  **single quotes** nothing is expanded.
- A key may be assigned more than once; the last assignment wins, and the
  duplicate is recorded for reference.

## `.env.schema` syntax

Each line is `KEY=TYPE`, optionally followed by a `# comment`. Append `?` to the
key to mark it optional.

```text
# .env.schema
DATABASE_URL=url
PORT=int
DEBUG=bool
RATIO=float             # any finite decimal or scientific number
CONTACT=email
SLUG=regex:^[a-z0-9-]+$
API_KEY=required
NICKNAME?=string        # optional: may be missing or empty
```

| Type | Accepts |
| ---- | ------- |
| `string` | any value (an empty value is allowed) |
| `required` | any **non-empty** value (same as `string`, but empty is an error) |
| `int` | an optional sign followed by digits, e.g. `5432`, `-7` |
| `float` | any finite number, e.g. `0.5`, `1e3`, `-2` |
| `bool` | `true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off` (case-insensitive) |
| `url` | a URL with a scheme and a host, e.g. `https://example.com` or `postgres://localhost:5432/app` |
| `email` | a value such as `dev@example.com` |
| `regex:<pattern>` | the value must **fully match** the Python regular expression `<pattern>` |

Every optional key (`NAME?`) may be absent or empty without producing an error.

## Command reference

**Global**

| Option | Description |
| ------ | ----------- |
| `-h`, `--help` | show help and exit |
| `--version` | print the version and exit |

**`envfy check`**

| Option | Default | Description |
| ------ | ------- | ----------- |
| `--env PATH` | `.env` | path to the `.env` file to validate |
| `--schema PATH` | `.env.schema` | path to the schema file |
| `--allow-extra` | off | do not warn about keys missing from the schema |
| `--json` | off | emit a machine-readable JSON report |

**`envfy diff`**

| Option | Description |
| ------ | ----------- |
| `A` | first `.env` file |
| `B` | second `.env` file |
| `--json` | emit a machine-readable JSON report (keys only, never values) |

**`envfy init`**

| Option | Default | Description |
| ------ | ------- | ----------- |
| `--env PATH` | `.env.example` | example file to infer the schema from |
| `--output PATH` | `.env.schema` | where to write the generated schema |

### Exit codes

| Code | Meaning |
| ---- | ------- |
| `0` | success — no errors (and, for `diff`, no differences) |
| `1` | `check` found validation errors, or `diff` found differences |
| `2` | usage error, missing file, or an unparseable `.env` / schema |

## CI integration

Run `envfy` as a configuration guard in GitHub Actions. Commit a `.env.schema`
next to your code and validate an example or templated `.env` on every push:

```yaml
name: Check env schema

on:
  push:
    branches: [main]
  pull_request:

jobs:
  envfy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install envfy
        run: pip install envfy
      - name: Validate .env against schema
        run: envfy check --env .env.example --schema .env.schema --allow-extra
```

`envfy` exits non-zero on the first error, so a misconfigured `.env` fails the
build like any other test.

## Development

```bash
git clone https://github.com/DelmarMG91/envfy.git
cd envfy
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# run the test suite
python -m pytest -q
```

The project has no runtime dependencies — only `pytest` for development.

## Contributing

Issues and pull requests are welcome. Please keep the standard-library-only
constraint, add tests for new behavior, and run `python -m pytest -q` before
opening a pull request.

## License

Released under the [MIT License](LICENSE).
