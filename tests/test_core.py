from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest  # type: ignore[import-not-found]

from bibslim.core import slim_bibtex_string, slim_entry
from bibslim.rules import SlimRules

DATA_DIR = Path(__file__).parent / "data"


def load_text(name: str) -> str:
    return (DATA_DIR / name).read_text(encoding="utf-8")


def test_slim_bibtex_matches_golden() -> None:
    src = load_text("sample_input.bib")
    expected = load_text("sample_minimal.golden.bib").strip()
    result = slim_bibtex_string(src, SlimRules.load())
    assert result.strip() == expected


def test_plugin_hook_invoked() -> None:
    calls: Dict[str, str] = {}

    def plugin(entry: Dict[str, str]) -> Dict[str, str]:
        calls[entry.get("id", entry.get("ID", ""))] = "called"
        entry["note"] = "plugin"
        return entry

    rules = SlimRules.load()
    rules.register_plugin(plugin)

    entry = {
        "id": "plug2024",
        "entrytype": "article",
        "author": "Ada Lovelace",
        "title": "An amazing study",
        "journal": "Journal of Testing",
        "year": "2024",
    }
    slimmed = slim_entry(entry, rules)
    assert calls["plug2024"] == "called"
    assert "note" in slimmed


def test_strict_mode_detects_duplicates(tmp_path: Path) -> None:
    src = """@article{dup1, author = {A Author}, title = {One}, year = {2024}}
@article{dup1, author = {B Author}, title = {Two}, year = {2024}}"""
    rules = SlimRules.load()
    rules.strict = True
    with pytest.raises(ValueError, match="duplicate ID"):
        slim_bibtex_string(src, rules)
