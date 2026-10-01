"""Section taxonomy, index policy and heading rules (RAG sections 1.1-1.2).

`classify` walks a heading path from its deepest element outwards and the first title that matches
a pattern decides the section id, so "Financial statements > Company accounts > Notes" is a
company statement, not a note. Excluded sections produce no chunks at all.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from finintel.locate.signals import normalise

#: Sections whose pages are not indexed in v1 (RAG section 1.2).
EXCLUDED = frozenset(
    {
        "primary_statements", "company_statements", "remuneration_report", "shareholder_information",
        "glossary_apm", "five_year_summary", "front_matter", "contents", "disclaimer",
    }
)  # fmt: skip
#: Always-present fallback for narrative that matches nothing more specific.
DEFAULT_SECTION = "narrative_other"

# (section id, pattern) tried against each normalised title, deepest first. Order is priority.
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (sid, re.compile(pattern))
    for sid, pattern in (
        ("company_statements", r"\b(?:company accounts|company (?:financial statements|balance sheet|income statement|statement)|notes to the company)\b"),
        ("primary_statements", r"^(?:consolidated |group )?(?:income statement|balance sheet|statement of (?:comprehensive income|financial position|cash flows?|changes in (?:taxpayers' )?equity|profit or loss)|cash flow statement)\b"),
        ("remuneration_report", r"\b(?:remuneration report|remuneration committee|directors' remuneration|remuneration policy)\b"),
        ("shareholder_information", r"\b(?:shareholder information|shareholders' information|investor information|shareholder services|annual general meeting|notice of (?:annual general )?meeting)\b"),
        ("glossary_apm", r"\b(?:glossary|alternative performance measures?|non-gaap measures?)\b"),
        ("five_year_summary", r"\b(?:five|ten|\d+)[- ]year (?:summary|record|review)\b"),
        ("contents", r"^(?:table of )?contents$"),
        ("disclaimer", r"\b(?:forward[- ]looking statements?|cautionary (?:statement|note))\b"),
        ("principal_risks", r"\bprincipal (?:and emerging )?risks?\b|\brisk management\b"),
        ("emerging_risks", r"\bemerging risks?\b"),
        ("viability_statement", r"\bviability statement\b|\blong-term viability\b"),
        ("going_concern", r"\bgoing concern\b"),
        ("audit_committee_report", r"\baudit committee\b"),
        ("nomination_committee_report", r"\bnomination (?:and governance )?committee\b"),
        ("directors_responsibilities", r"\bdirectors' responsibilit"),
        ("directors_report", r"\bdirectors' report\b"),
        ("corporate_governance_report", r"\b(?:corporate )?governance\b"),
        ("auditors_report", r"\b(?:independent )?auditors?'?s? report\b|\bkey audit matters?\b"),
        ("notes_critical_judgements", r"\b(?:critical (?:accounting )?(?:judg(?:e)?ments|estimates)|key sources of estimation)\b"),
        ("notes_accounting_policies", r"\baccounting (?:policies|information)\b|\bbasis of preparation\b"),
        ("s172_statement", r"\bsection 172\b|\bs172\b"),
        ("chair_statement", r"\bchair(?:man|woman|person)?(?:'s)? (?:statement|letter|review|introduction)\b"),
        ("ceo_review", r"\b(?:chief executive|ceo|group chief executive)(?:'s)? (?:officer )?(?:review|statement|report|introduction)\b"),
        ("business_model", r"\bbusiness model\b"),
        ("kpis", r"\bkey performance indicators\b|\bkpis?\b"),
        ("financial_review", r"\bfinancial review\b|\bchief financial officer\b|\bcfo\b"),
        ("segment_review", r"\bsegment(?:al)? (?:review|performance|results)\b|\bdivisional review\b|\bbusiness group\b"),
        ("market_review", r"\bmarket (?:review|overview|context)\b"),
        ("strategy", r"\bour strategy\b|^strategy\b|\bstrategic (?:priorities|framework)\b"),
        ("sustainability_tcfd", r"\b(?:tcfd|climate[- ]related|task force on climate|sustainability)\b"),
    )
)  # fmt: skip

_COMPANY = dict(_RULES)["company_statements"]
_PARENT = re.compile(r"\bparent company\b")
_AUDITORS = dict(_RULES)["auditors_report"]
_NOTE_HEADING = re.compile(
    r"^(?:(?i:note)\s+)?(?P<num>\d{1,2}[A-Z]?)(?P<sub>\.\d{1,2})?\s*[.:]?\s+(?P<title>[A-ZÀ-Þ(].*)$"
)
_NOTE_ONLY_NUMBER = re.compile(r"^(?:note\s+)?\d{1,2}[A-Z]?(?:\.\d{1,2})?\s*[.:]?$")
_CONTINUED = re.compile(r"\s*[\-\u2013:]?\s*\(?continued\)?\s*$", re.IGNORECASE)
_NOTES_SECTION = re.compile(
    r"\bnotes? to the\b|\bnotes to (?:the )?(?:consolidated )?financial statements\b"
)
HEADING_SIZE_RATIO = 1.15
MAX_HEADING_WORDS = 16


def classify(path: Sequence[str]) -> str:
    """Section id for a heading path (bookmark chain plus in-page headings)."""
    norms = [normalise(title) for title in path]
    # Parent-company material is never outvoted by a deeper title, with one exception: inside the
    # auditor's report a key audit matter may be about the parent ("4.3 Investments ... (Parent
    # company)"), and that is narrative the reader needs, not the parent's own accounts.
    in_audit_report = any(_AUDITORS.search(n) for n in norms)
    if any(_COMPANY.search(n) or (_PARENT.search(n) and not in_audit_report) for n in norms):
        return "company_statements"
    for title in reversed(path):
        norm = normalise(title)
        for section_id, pattern in _RULES:
            if pattern.search(norm):
                return section_id
    for title in reversed(path):
        if note_heading(title) is not None or _NOTES_SECTION.search(normalise(title)):
            return "notes_other"
    return DEFAULT_SECTION


def note_heading(text: str) -> tuple[str, str] | None:
    """(note number, title) if `text` is a note heading, e.g. "12. Borrowings" -> ("12", ...).

    A trailing "continued" keeps the number and is removed from the title. Letter suffixes
    ("6C.") are part of the number, as Unilever prints them.
    """
    match = _NOTE_HEADING.match(" ".join(text.split()))
    if match is None:
        return None
    title = _CONTINUED.sub("", match.group("title")).strip()
    return f"{match.group('num')}{match.group('sub') or ''}", title


_BULLET = re.compile(r"^[\s\u25a0\u25aa\u25cf\u2022\u2023\u2043\u2212\-\u2013\u2014*>]")
MAX_BOLD_ONLY_WORDS = 10  # body-size bold text is a heading only if it is short


def is_heading_text(text: str) -> bool:
    """Shape test only: styling (size, bold) is checked by the caller."""
    words = text.split()
    if (
        _BULLET.match(text)
        or text.rstrip().endswith("-")
        or not (text[:1].isupper() or text[:1].isdigit())
    ):
        return False
    return (
        bool(re.search(r"[A-Za-z]", text))
        and 1 <= len(words) <= MAX_HEADING_WORDS
        and not _NOTE_ONLY_NUMBER.match(text.strip())
        and not text.rstrip().endswith((".", ";", ","))
    ) or bool(note_heading(text) and len(words) <= MAX_HEADING_WORDS)
