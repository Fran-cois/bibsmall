"""bibslim - lightweight BibTeX slimming toolkit."""

from .rules import SlimRules
from .core import slim_entry, slim_bibtex_string

__all__ = ["SlimRules", "slim_entry", "slim_bibtex_string"]

__version__ = "0.1.0"
