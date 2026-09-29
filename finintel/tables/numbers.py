"""Printed-number grammar (EXTRACTION section 4.2).

    [currency] ( "(" amount ")" | [minus] amount ) [footnote marker]
    amount = digits with "," or thin-space thousands separators, optional "." decimals
    a lone dash, "nil" or an en/em dash means zero

Anything else ("n/a", "see note 12", "12.5%", "£13.9bn") is unparsed: recorded, never 0.
Values are exact Decimals. Nothing is rescaled here; the unit comes from the column header (M2.3).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

_SUPERSCRIPTS = "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"
_MARKERS = "*\u2020\u2021" + _SUPERSCRIPTS
_THIN = "\u2009\u202f\u00a0"  # thin space, narrow no-break space, no-break space
_SEP = "\x00"  # placeholder for a printed thin-space separator (survives NFKC)
_MINUS = "-\u2010\u2011\u2012\u2013\u2212"
_NIL = frozenset({"-", "\u2013", "\u2014", "\u2012", "nil"})
_AMOUNT = re.compile(rf"^(?:\d{{1,3}}(?:[,{_SEP}]\d{{3}})+|\d+)(?:\.(\d+))?$")
_CURRENCY = re.compile(r"^(?:us\$|£|\$|€)", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedNumber:
    value: Decimal
    decimals: int  # digits after the point: the unit of the last printed digit is 10**-decimals
    negative_style: str | None  # "brackets", "minus" or None
    currency: str | None
    footnote: str | None
    nil: bool = False


def parse_number(raw: str | None) -> ParsedNumber | None:
    """Parse one printed cell, or None if it is not a number under the grammar."""
    if raw is None:
        return None
    text = raw.strip()
    footnote = ""
    while text and text[-1] in _MARKERS:  # before NFKC, which would turn "\u00b9" into "1"
        footnote = text[-1] + footnote
        text = text[:-1].rstrip()
    for thin in _THIN:
        text = re.sub(rf"(?<=\d){thin}(?=\d{{3}}\b)", _SEP, text)
    text = unicodedata.normalize("NFKC", text).strip()
    if text.lower() in _NIL:
        return ParsedNumber(Decimal(0), 0, None, None, footnote or None, nil=True)

    negative_style: str | None = None
    if text.startswith("(") and text.endswith(")"):
        negative_style, text = "brackets", text[1:-1].strip()
    currency = None
    if match := _CURRENCY.match(text):
        currency, text = match.group(0), text[match.end() :].strip()
    if text and text[0] in _MINUS and negative_style is None:
        negative_style, text = "minus", text[1:].strip()
    if currency is None and (match := _CURRENCY.match(text)):  # "-£1,234"
        currency, text = match.group(0), text[match.end() :].strip()

    amount = _AMOUNT.match(text)
    if amount is None:
        return None
    value = Decimal(text.replace(",", "").replace(_SEP, ""))
    return ParsedNumber(
        value=-value if negative_style else value,
        decimals=len(amount.group(1) or ""),
        negative_style=negative_style,
        currency=currency,
        footnote=footnote or None,
    )


def canonical(raw: str | None) -> str:
    """Comparison form (EXTRACTION section 5.1, EVAL section 3.1): separators and spaces removed,
    brackets and minus signs unified, dashes and nil as 0. Unparseable text: whitespace
    collapsed."""
    parsed = parse_number(raw)
    if parsed is None:
        return " ".join((raw or "").split())
    return format(parsed.value.normalize(), "f") if parsed.value else "0"
