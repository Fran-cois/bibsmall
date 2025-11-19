"""Command-line interface for bibslim."""

from __future__ import annotations

import argparse
import difflib
import pathlib
import sys
from typing import Optional

from .core import slim_bibtex_string
from .rules import SlimRules


def _read_input(path: Optional[str]) -> str:
    if path is None:
        return sys.stdin.read()
    return pathlib.Path(path).read_text(encoding="utf-8")


def _write_output(path: Optional[str], content: str) -> None:
    if path is None:
        sys.stdout.write(content)
    else:
        pathlib.Path(path).write_text(content, encoding="utf-8")


def app(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="bibslim", description="Slim down BibTeX entries.")
    parser.add_argument("input", nargs="?", help="Input .bib file (default: stdin)")
    parser.add_argument("-o", "--output", help="Output .bib file (default: stdout)")
    parser.add_argument("-r", "--rules", help="YAML rules file (optional)")
    parser.add_argument("--preset", choices=["minimal", "conference", "journal"], help="Override preset")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate only")
    parser.add_argument("--diff", action="store_true", help="Show unified diff instead of writing")
    parser.add_argument("--inplace", action="store_true", help="Write back to input file")
    parser.add_argument("--strict", action="store_true", help="Fail on malformed records")
    args = parser.parse_args(argv)

    text = _read_input(args.input)

    rules = SlimRules.load(args.rules) if args.rules else SlimRules.load()
    if args.preset:
        rules.preset = args.preset
    if args.strict:
        rules.strict = True

    output = slim_bibtex_string(text, rules)

    if args.dry_run and not args.diff:
        return

    if args.diff:
        diff = difflib.unified_diff(
            text.splitlines(True),
            output.splitlines(True),
            fromfile="before",
            tofile="after",
        )
        sys.stdout.writelines(diff)
        return

    if args.inplace and args.input:
        _write_output(args.input, output)
        return

    _write_output(args.output, output)


if __name__ == "__main__":
    app()
