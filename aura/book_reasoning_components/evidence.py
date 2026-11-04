"""Pure lexical evidence checks; do not mistake them for semantic proof."""
from __future__ import annotations
import re
import unicodedata


def _normal(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r'[^\W\d_]{4,}', _normal(text), flags=re.UNICODE))


def _quote_valid(passage: dict, quote: str) -> bool:
    return (isinstance(quote, str) and 18 <= len(quote) <= 850
            and _normal(quote) in _normal(passage['text']))


def _plausible(statement: str, quote: str) -> bool:
    """Small lexical screen, not semantic entailment. Final state stays unverified."""
    a = _tokens(statement)
    b = _tokens(quote)
    return bool(a and b and (len(a & b) / len(a) >= 0.16))
