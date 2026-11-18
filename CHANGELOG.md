# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-01

### Added

- `.env` parser with support for `export`, quoted values, trailing comments,
  line numbers and escape sequences.
- `.env.schema` parser with `string`, `int`, `float`, `bool`, `url`, `email`,
  `regex:<pattern>` and `required` types plus optional (`?`) keys.
- `envfy check` command with human-readable and JSON reports, `--allow-extra`
  support and meaningful exit codes.
- `envfy diff` command that compares two `.env` files without exposing values.
- `envfy init` command that infers a schema from an example `.env` file.
- Test suite covering the parser, validator, diff engine and CLI.

[Unreleased]: https://github.com/DelmarMG91/envfy/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DelmarMG91/envfy/releases/tag/v0.1.0
