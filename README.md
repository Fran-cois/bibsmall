# bibsmall

BibTeX slimmer: abbreviates venues, shortens authors, normalizes titles/pages/DOIs, and prunes noisy fields.

## Installation

```bash
pip install bibslim
```

## Usage

```bash
bibslim input.bib --preset minimal --diff
```

Key options:

- `--preset {minimal,conference,journal}`: choose a preset for field retention.
- `--rules`: provide a custom YAML ruleset.
- `--diff`: show a unified diff.
- `--inplace`: overwrite the source file.
- `--strict`: fail on malformed entries (great for CI).

## Development

Install development dependencies and run checks:

```bash
pip install -e .[dev]
ruff check .
mypy src tests
pytest
```
