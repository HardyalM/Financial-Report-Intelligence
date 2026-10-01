"""Eval-time routing of list-shaped questions to the code-built bullets (EVAL 3.4).

A question about the principal risks, the key audit matters or going concern is answered from the
bullets the commentary already built and validated, not by a second model call. The routing keys on
the question's own words, never on a label. Questions that match nothing return None and take the
ordinary retrieve-and-answer path.
"""

from __future__ import annotations

import re

from finintel.commentary.qa import Answer
from finintel.contracts.commentary import Commentary, Paragraph
from finintel.retrieval.lexical import terms

_GENERIC = frozenset(
    {"audit", "auditor", "matter", "key", "say", "said", "report", "group", "company"}
)
_KAM_TITLE = re.compile(r"^Key audit matter: (?P<title>.+?)\. “")


def _topic(commentary: Commentary, name: str) -> list[Paragraph]:
    return next((t.paragraphs for t in commentary.topics if t.topic == name), [])


def list_answer(question: str, commentary: Commentary) -> Answer | None:
    q = question.lower()
    governance = _topic(commentary, "governance_and_directors")
    if "going concern" in q:
        going = [p for p in governance if p.rendered.startswith("Going concern:")]
        return Answer("ok", going) if going else None
    if re.search(r"audit matter|auditor", q):
        kams = [(m.group("title"), p) for p in governance if (m := _KAM_TITLE.match(p.rendered))]
        asked = set(terms(question)) - _GENERIC
        specific = [p for title, p in kams if asked & set(terms(title))]
        if specific:
            return Answer("ok", specific)
        return Answer("ok", [p for _, p in kams]) if kams and "audit matters" in q else None
    if re.search(r"principal risks?", q):
        risks = _topic(commentary, "strategic_risks")
        return Answer("ok", risks) if risks else None
    return None
