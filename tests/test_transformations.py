from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


from bibslim.cli import app
from bibslim.core import slim_entry
from bibslim.rules import SlimRules

DATA_DIR = Path(__file__).parent / "data"


def load_fixture(name: str) -> str:
    return (DATA_DIR / name).read_text(encoding="utf-8")


def test_title_sentence_case_preserves_acronyms() -> None:
    rules = SlimRules.load()
    rules.title_drop_subtitle = False

    entry = {
        "ID": "sample2024",
        "ENTRYTYPE": "inproceedings",
        "author": "John Smith",
        "title": "{SQL} Joins in NLP: Lessons from {AMIE} and Real-World Datasets",
        "booktitle": "Proceedings of the ACM SIGMOD International Conference on Management of Data",
        "year": "2024",
    }

    slimmed = slim_entry(entry, rules)
    assert (
        slimmed["title"]
        == "SQL joins in NLP: Lessons from AMIE and Real-world Datasets"
    )


def test_author_abbreviation_and_others() -> None:
    rules = SlimRules.load()
    rules.max_authors = 2
    rules.use_and_others = True

    entry = {
        "ID": "authors2024",
        "ENTRYTYPE": "article",
        "author": "John Smith and Jane Doe and Alan Turing",
        "title": "Three authors",
        "journal": "Journal",
        "year": "2024",
    }

    slimmed = slim_entry(entry, rules)
    assert slimmed["author"] == "J. Smith and J. Doe and others"


def test_arxiv_fields_respected_by_keep_arxiv_flag() -> None:
    base_entry = {
        "ID": "arxiv42",
        "ENTRYTYPE": "article",
        "author": "Ada Lovelace",
        "title": "ArXiv experiments",
        "journal": "Journal",
        "year": "2024",
        "eprint": "1234.56789",
        "archiveprefix": "arXiv",
        "primaryclass": "cs.LG",
    }

    without_arxiv = SlimRules.load()
    slimmed = slim_entry(deepcopy(base_entry), without_arxiv)
    assert "eprint" not in slimmed
    assert "archiveprefix" not in slimmed
    assert "primaryclass" not in slimmed

    with_arxiv = SlimRules.load()
    with_arxiv.keep_arxiv = True
    slimmed_with_arxiv = slim_entry(deepcopy(base_entry), with_arxiv)
    assert "eprint" in slimmed_with_arxiv
    assert "archiveprefix" in slimmed_with_arxiv
    assert "primaryclass" in slimmed_with_arxiv


def test_cli_diff_outputs_unified_diff(tmp_path: Path, capsys: Any) -> None:
    src = tmp_path / "refs.bib"
    src.write_text(load_fixture("sample_input.bib"), encoding="utf-8")

    app([str(src), "--diff"])
    captured = capsys.readouterr().out
    assert "--- before" in captured
    assert "+++ after" in captured


def test_cli_inplace_updates_file(tmp_path: Path) -> None:
    src = tmp_path / "refs.bib"
    src.write_text(load_fixture("sample_input.bib"), encoding="utf-8")

    app([str(src), "--inplace"])
    updated = src.read_text(encoding="utf-8")
    assert "others" in updated