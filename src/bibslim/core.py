"""Core transformation routines for bibslim."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence, Set, cast
import importlib
import re

from slugify import slugify
import bibtexparser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bwriter import BibTexWriter

from .rules import SlimRules

ACRONYM_RX = re.compile(r"\b([A-Z]{2,}[\dA-Z]*)\b")
BRACED_RX = re.compile(r"\{([^{}]+)\}")
MONTH_ALIASES = {
    "january": "jan",
    "february": "feb",
    "march": "mar",
    "april": "apr",
    "may": "may",
    "june": "jun",
    "july": "jul",
    "august": "aug",
    "september": "sep",
    "october": "oct",
    "november": "nov",
    "december": "dec",
}


def _compact_pages(pages: str) -> str:
    pages = re.sub(r"\s*[-–—]+\s*", "–", pages.strip())
    if re.match(r"^[eEsS]?\d+\s*–\s*[eEsS]?\d+$", pages):
        pages = re.sub(r"\s+", "", pages)
    return pages


def _strip_doi_prefix(doi: str) -> str:
    return re.sub(r"(?i)^(https?://(dx\.)?doi\.org/)", "", doi.strip())


def _sentence_case_safe(title: str, *, keep_acronyms: bool, small_words: Sequence[str]) -> str:
    if not title:
        return title

    protected: Dict[str, str] = {}

    def protect(match: re.Match[str]) -> str:
        key = f"@@{len(protected)}@@"
        protected[key] = match.group(1)
        return key

    tmp = BRACED_RX.sub(protect, title)
    tokens = re.split(r"(\s+)", tmp)
    lower_small = {w.lower() for w in small_words}

    subtitle_mode = False
    first_word_done = False
    out_parts: List[str] = []

    for token in tokens:
        if not token or token.isspace():
            out_parts.append(token)
            continue

        stripped_token = token.rstrip(",:;.!?")
        trailing = token[len(stripped_token) :]

        if re.fullmatch(r"@@\d+@@", stripped_token):
            out_parts.append(token)
            first_word_done = True
        else:
            acronym_candidate = stripped_token
            if keep_acronyms and ACRONYM_RX.fullmatch(acronym_candidate):
                rendered = acronym_candidate
            else:
                lowered = stripped_token.lower()
                if not first_word_done:
                    rendered = lowered[:1].upper() + lowered[1:]
                elif subtitle_mode:
                    if lowered in lower_small:
                        rendered = lowered
                    else:
                        rendered = lowered[:1].upper() + lowered[1:]
                else:
                    if lowered in lower_small:
                        rendered = lowered
                    else:
                        rendered = lowered
                if "-" in stripped_token and rendered:
                    head, *rest = rendered.split("-")
                    if rest:
                        rendered = "-".join([head] + [segment.lower() for segment in rest])
            out_parts.append(rendered + trailing)
            first_word_done = True

        if trailing.endswith(":"):
            subtitle_mode = True

    out = "".join(out_parts)

    for key, value in protected.items():
        out = out.replace(key, value)

    return out[:1].upper() + out[1:]


def _drop_subtitle(title: str) -> str:
    return re.split(r"[:–—-]\s+", title, maxsplit=1)[0].strip()


def _parse_person(name: str) -> Dict[str, str]:
    name = name.strip()
    if "," in name:
        last, given = [part.strip() for part in name.split(",", 1)]
        return {"given": given, "family": last}

    parts = name.split()
    if len(parts) == 1:
        return {"given": "", "family": parts[0]}

    particles = {
        "de",
        "del",
        "der",
        "van",
        "von",
        "von der",
        "da",
        "di",
        "la",
        "le",
    }

    if len(parts) >= 3 and f"{parts[-2].lower()} {parts[-1].lower()}" in particles:
        return {"given": " ".join(parts[:-2]), "family": " ".join(parts[-2:])}
    if parts[-2].lower() in particles:
        return {"given": " ".join(parts[:-2]), "family": " ".join(parts[-2:])}
    return {"given": " ".join(parts[:-1]), "family": parts[-1]}


def _initials(given: str) -> str:
    pieces = [piece for piece in re.split(r"[ \-]", given) if piece]
    return " ".join((piece[0].upper() + ".") for piece in pieces if piece[0].isalpha())


def _abbrev_given_names_field(author_field: str) -> str:
    people = [author.strip() for author in author_field.split(" and ") if author.strip()]
    compacted: List[str] = []
    for person in people:
        parsed = _parse_person(person)
        if parsed["given"]:
            compacted.append(f"{_initials(parsed['given'])} {parsed['family']}")
        else:
            compacted.append(parsed["family"])
    return " and ".join(compacted)


def _shrink_authors(author_field: str, rules: SlimRules) -> str:
    authors = [author.strip() for author in author_field.split(" and ") if author.strip()]
    transformed = author_field
    if rules.abbreviate_given_names:
        transformed = _abbrev_given_names_field(author_field)
        authors = [author.strip() for author in transformed.split(" and ") if author.strip()]
    if len(authors) > rules.max_authors and rules.use_and_others:
        authors = authors[: rules.max_authors] + ["others"]
    return " and ".join(authors)


def _normalize_venue(name: str, mapping: Dict[str, str], regex_aliases: Sequence[tuple[re.Pattern[str], str]]) -> str:
    if not name:
        return name
    collapsed = re.sub(r"\s+", " ", name).strip(" .")
    key = collapsed.lower()
    if key in mapping:
        return mapping[key]
    for pattern, replacement in regex_aliases:
        if pattern.search(collapsed):
            return replacement
    return collapsed


def _load_plugins(plugin_specs: Sequence[str]) -> List[Callable[[Dict[str, str]], Dict[str, str]]]:
    hooks: List[Callable[[Dict[str, str]], Dict[str, str]]] = []
    for spec in plugin_specs:
        module_name, _, attr = spec.partition(":")
        if not module_name or not attr:
            raise ValueError(f"Invalid plugin spec: {spec}")
        module = importlib.import_module(module_name)
        hook = getattr(module, attr)
        if not callable(hook):
            raise TypeError(f"Plugin {spec} is not callable")
        hooks.append(cast(Callable[[Dict[str, str]], Dict[str, str]], hook))
    return hooks


def slim_entry(entry: Dict[str, str], rules: SlimRules) -> Dict[str, str]:
    normalized = {key.lower(): value for key, value in entry.items()}

    for hook in _load_plugins(rules.plugins):
        normalized = hook(normalized)

    if "author" in normalized and normalized["author"].strip():
        normalized["author"] = _shrink_authors(normalized["author"], rules)

    if "title" in normalized and normalized["title"].strip():
        title = normalized["title"].strip()
        if rules.title_drop_subtitle:
            title = _drop_subtitle(title)
        if rules.title_sentence_case:
            title = _sentence_case_safe(
                title,
                keep_acronyms=rules.title_preserve_acronyms,
                small_words=rules.title_small_words,
            )
        normalized["title"] = title

    mapping = rules.load_abbrev_map() if rules.abbreviate_outlets else {}
    regex_aliases = rules.compiled_venue_aliases()
    for outlet in ("journal", "booktitle"):
        if outlet in normalized and normalized[outlet].strip():
            normalized[outlet] = _normalize_venue(normalized[outlet], mapping, regex_aliases)

    if "month" in normalized:
        if rules.normalize_month and normalized["month"].strip():
            month_raw = re.sub(r"[{}]", "", normalized["month"]).strip().lower()
            normalized["month"] = MONTH_ALIASES.get(month_raw, normalized["month"])
        if rules.keep_month == "never" or (
            rules.keep_month == "auto" and normalized.get("month") not in MONTH_ALIASES.values()
        ):
            normalized.pop("month", None)
    elif rules.keep_month == "never":
        normalized.pop("month", None)

    if "pages" in normalized and normalized["pages"].strip() and rules.pages_compact:
        normalized["pages"] = _compact_pages(normalized["pages"])

    if "doi" in normalized and normalized["doi"].strip() and rules.doi_strip_prefix:
        normalized["doi"] = _strip_doi_prefix(normalized["doi"])

    if not rules.keep_arxiv:
        for field in ("eprint", "archiveprefix", "primaryclass", "eprinttype"):
            normalized.pop(field, None)

    for field in rules.trim_fields:
        normalized.pop(field, None)

    keep_fields = {
        *rules.keep_fields_common,
        "id",
        "entrytype",
        "ID",
        "ENTRYTYPE",
    }
    if rules.keep_month != "never":
        keep_fields.add("month")
    if rules.keep_arxiv:
        keep_fields.update({"eprint", "archiveprefix", "primaryclass", "eprinttype"})
    normalized = {key: value for key, value in normalized.items() if key in keep_fields}

    if "id" in normalized and "ID" not in normalized:
        normalized["ID"] = normalized.pop("id")
    if "entrytype" in normalized and "ENTRYTYPE" not in normalized:
        normalized["ENTRYTYPE"] = normalized.pop("entrytype")

    if "ID" not in normalized:
        author_part = normalized.get("author", "")
        year_part = normalized.get("year", "")
        title_part = normalized.get("title", "")
        base_key: str = f"{author_part} {year_part} {title_part}".strip()[:64]
        safe_base: str = base_key if base_key else "ref"
        normalized["ID"] = cast(str, slugify(safe_base)).replace("-", "")  # type: ignore[redundant-cast]

    for hook in _load_plugins(rules.plugins):
        normalized = hook(normalized)

    normalized["ENTRYTYPE"] = normalized.get("ENTRYTYPE", entry.get("ENTRYTYPE", "misc"))
    return normalized


def _strict_entry_check(entry: Dict[str, str]) -> None:
    missing = [field for field in ("author", "title", "year") if not entry.get(field)]
    if missing:
        raise ValueError(f"[strict] {entry.get('ID', '<no-id>')} missing {missing}")
    if "pages" in entry and entry["pages"] and not re.search(r"\d", entry["pages"]):
        raise ValueError(f"[strict] {entry.get('ID', '<no-id>')} malformed pages: {entry['pages']}")


def slim_bibtex_string(bib_src: str, rules: SlimRules | None = None) -> str:
    rules = rules or SlimRules.load()
    parser = bibtexparser.bparser.BibTexParser(common_strings=True)  # type: ignore[attr-defined]
    db = bibtexparser.loads(bib_src, parser=parser)  # type: ignore[arg-type]

    if rules.strict:
        ids: Set[str] = set()
        for entry in db.entries:  # type: ignore[attr-defined]
            entry_dict = cast(Dict[str, str], entry)
            entry_id = entry_dict.get("ID", "")
            if entry_id in ids:
                raise ValueError(f"[strict] duplicate ID detected: {entry_id}")
            if entry_id:
                ids.add(entry_id)
            _strict_entry_check(entry_dict)

    slim_db: Any = BibDatabase()
    processed_entries: List[Dict[str, str]] = []
    for entry in db.entries:  # type: ignore[attr-defined]
        entry_dict = cast(Dict[str, str], entry)
        processed_entries.append(slim_entry(entry_dict, rules))
    slim_db.entries = processed_entries

    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = ("ID",)
    writer.comma_first = False
    writer.display_order = [
        "author",
        "title",
        "booktitle",
        "journal",
        "year",
        "month",
        "volume",
        "number",
        "pages",
        "doi",
        "publisher",
        "series",
        "organization",
        "address",
        "editor",
    ]

    result = bibtexparser.dumps(slim_db, writer)  # type: ignore[no-untyped-call]
    return cast(str, result)  # type: ignore[return-value]
