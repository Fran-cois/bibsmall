"""Configuration rules for bibslim transformations."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple, cast
import importlib.resources as pkg_resources
import re
import sys
import textwrap

import yaml

DEFAULT_RULES_YAML = textwrap.dedent(
        """\
preset: minimal  # minimal|conference|journal
max_authors: 3
use_and_others: true
abbreviate_given_names: true
title_drop_subtitle: true
title_sentence_case: true
title_preserve_acronyms: true
title_small_words:
    - a
    - an
    - and
    - as
    - at
    - but
    - by
    - for
    - from
    - in
    - of
    - 'on'
    - or
    - the
    - to
    - nor
keep_arxiv: false
keep_month: auto   # auto|always|never
normalize_month: true
pages_compact: true
doi_strip_prefix: true
abbreviate_outlets: true
abbrev_map: iso4_abbrev.yml
trim_fields: [url, urldate, issn, isbn, abstract, keywords, note, annote, file, language]
keep_fields_common: [author, title, booktitle, journal, year, volume, number, pages, publisher, address, editor, organization, series, doi]
strict: false
plugins: []  # e.g., ["bibslim_plugins.acl:acl_fixups"]
venue_regex_aliases: [{pattern: '(?i)^proceedings\\s+of\\s+the\\s+example\\s+data\\s+systems\\s+symposium.*', replace: 'EDSS'}]
"""
)

PRESETS: Dict[str, Dict[str, object]] = {
    "minimal": {
        "keep_fields_common": [
            "author",
            "title",
            "journal",
            "booktitle",
            "year",
            "pages",
            "doi",
        ]
    },
    "conference": {
        "keep_fields_common": [
            "author",
            "title",
            "booktitle",
            "year",
            "pages",
            "doi",
        ]
    },
    "journal": {
        "keep_fields_common": [
            "author",
            "title",
            "journal",
            "year",
            "volume",
            "number",
            "pages",
            "doi",
        ]
    },
}


@dataclass
class SlimRules:
    """Container for runtime rules controlling the slimming pipeline."""

    preset: str = "minimal"
    max_authors: int = 3
    use_and_others: bool = True
    abbreviate_given_names: bool = True
    title_drop_subtitle: bool = True
    title_sentence_case: bool = True
    title_preserve_acronyms: bool = True
    title_small_words: List[str] = field(default_factory=list)
    keep_arxiv: bool = False
    keep_month: str = "auto"
    normalize_month: bool = True
    pages_compact: bool = True
    doi_strip_prefix: bool = True
    abbreviate_outlets: bool = True
    abbrev_map: Optional[str] = "iso4_abbrev.yml"
    outlet_overrides: Dict[str, str] = field(default_factory=dict)
    trim_fields: List[str] = field(default_factory=list)
    keep_fields_common: List[str] = field(default_factory=list)
    strict: bool = False
    plugins: List[str] = field(default_factory=list)
    venue_regex_aliases: List[Dict[str, str]] = field(default_factory=list)

    @staticmethod
    def _load_yaml(path: Optional[Path]) -> Dict[str, object]:
        if path is None:
            loaded = yaml.safe_load(DEFAULT_RULES_YAML) or {}
            return dict(loaded)
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):  # pragma: no cover - defensive
            raise ValueError("Rules YAML must define a mapping")
        return dict(loaded)

    @staticmethod
    def load(yaml_path: Optional[str] = None) -> "SlimRules":
        """Load rules from YAML (or defaults when not provided)."""

        base = asdict(SlimRules())
        yaml_config = SlimRules._load_yaml(Path(yaml_path) if yaml_path else None)
        preset_name = str(yaml_config.get("preset", base.get("preset", "minimal")))

        def _preset_dict(name: str) -> Dict[str, object]:
            preset = PRESETS.get(name)
            return dict(preset) if preset else {}

        merged: Dict[str, object] = {}
        for source in (base, _preset_dict(str(base.get("preset", "minimal"))), _preset_dict(preset_name), yaml_config):
            merged.update(source)
        # ensure lists are copied to avoid shared state
        if "title_small_words" not in merged or merged["title_small_words"] is None:
            merged["title_small_words"] = []
        if "trim_fields" not in merged or merged["trim_fields"] is None:
            merged["trim_fields"] = []
        if "keep_fields_common" not in merged or merged["keep_fields_common"] is None:
            merged["keep_fields_common"] = []
        if "plugins" not in merged or merged["plugins"] is None:
            merged["plugins"] = []
        if "venue_regex_aliases" not in merged or merged["venue_regex_aliases"] is None:
            merged["venue_regex_aliases"] = []
        return SlimRules(**merged)  # type: ignore[arg-type]

    def load_abbrev_map(self) -> Dict[str, str]:
        """Load and merge the outlet abbreviation map."""

        mapping: Dict[str, str] = {}
        if self.abbrev_map:
            resource: Optional[Any]
            try:
                pkg_name = ((".".join(__package__.split("."))) if __package__ else "bibslim") + ".data"
                pkg_root = pkg_resources.files(pkg_name)
                candidate = pkg_root.joinpath(self.abbrev_map)
                resource = candidate if candidate.is_file() else None
            except (FileNotFoundError, ModuleNotFoundError, AttributeError, TypeError):
                resource = None

            if resource is None:
                fallback = Path(__file__).resolve().parent / "data" / self.abbrev_map
                resource = fallback if fallback.is_file() else None

            if resource is not None:
                with resource.open("r", encoding="utf-8") as handle:
                    raw_mapping: Any = yaml.safe_load(handle)
                    if isinstance(raw_mapping, dict):
                        for key, value in cast(Dict[object, object], raw_mapping).items():
                            mapping[str(key).lower()] = str(value)
        mapping.update({k.lower(): v for k, v in self.outlet_overrides.items()})
        return mapping

    def compiled_venue_aliases(self) -> List[Tuple[Pattern[str], str]]:
        out: List[Tuple[Pattern[str], str]] = []
        for alias in self.venue_regex_aliases:
            pattern = alias.get("pattern")
            replace = alias.get("replace")
            if not pattern or replace is None:
                continue
            out.append((re.compile(pattern), str(replace)))
        return out

    def register_plugin(self, fn: Callable[[Dict[str, str]], Dict[str, str]]) -> None:
        """Allow runtime registration of plugin functions (useful in tests)."""

        module = sys.modules.get(fn.__module__)
        if module is not None and not hasattr(module, fn.__name__):
            setattr(module, fn.__name__, fn)
        spec = f"{fn.__module__}:{fn.__name__}"
        if spec not in self.plugins:
            self.plugins.append(spec)
