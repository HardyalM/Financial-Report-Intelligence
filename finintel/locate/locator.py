"""Locate the primary statements and profile the document (EXTRACTION sections 1-2).

For each page and each statement type it names (by title, bookmark or contents entry): score the
page, classify its scope, apply the hard exclusions. Then per statement type choose the best
selectable page at or above 0.55, follow continuation pages, and refuse to choose between two
candidates within 0.05 of each other. Everything rejected is kept, with its reason, for review.

No number is read here. A wrong page choice is the most expensive error in the pipeline, so every
choice carries its evidence and every refusal says what was seen.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from finintel.locate.continuation import continues, is_spread
from finintel.locate.exclusions import exclusion_reason
from finintel.locate.folios import Folios, infer_folios
from finintel.locate.models import (
    SELECTABLE_SCOPES,
    Continuation,
    DocumentType,
    LocateResult,
    LocateWarning,
    PageCandidate,
    Scope,
    StatementLocation,
    StatementType,
)
from finintel.locate.outline import LocationHint, bookmark_hints, contents_hints, section_paths
from finintel.locate.profile import profile_document
from finintel.locate.scope import classify_scope, is_entity_label
from finintel.locate.scorer import SELECT_THRESHOLD, TIE_MARGIN, score_page
from finintel.locate.signals import PageView, VisualLine, detect_chrome
from finintel.locate.titles import TitleMatch, match_title
from finintel.parse.text_layer import TextLayer

#: Bump when selection behaviour changes.
LOCATOR_VERSION = "1"
HEADER_BAND = 0.12  # without a title line, scope and exclusion evidence comes from the top 12 %
ENTITY_COLUMN_BAND = 0.35

HUMAN = {
    StatementType.INCOME_STATEMENT: "consolidated income statement",
    StatementType.COMPREHENSIVE_INCOME: "consolidated statement of comprehensive income",
    StatementType.BALANCE_SHEET: "consolidated balance sheet",
    StatementType.CASH_FLOW: "consolidated cash flow statement",
    StatementType.CHANGES_IN_EQUITY: "consolidated statement of changes in equity",
}
_ORDER = {kind: i for i, kind in enumerate(StatementType)}


def locate(layer: TextLayer) -> LocateResult:
    chrome = detect_chrome(layer)
    views = {page.page: PageView(page, chrome) for page in layer.pages}
    folios = infer_folios(list(views.values()))
    paths = section_paths(layer.outline, layer.page_count)
    hints: dict[int, list[LocationHint]] = defaultdict(list)
    for source in (
        bookmark_hints(layer.outline),
        contents_hints(list(views.values()), folios, layer),
    ):
        for page, page_hints in source.items():
            hints[page].extend(page_hints)

    candidates = _resolve_unknown_scope(
        [c for view in views.values() for c in _page_candidates(view, hints, paths, folios)]
    )
    warnings: list[LocateWarning] = []
    statements: dict[StatementType, StatementLocation] = {}
    selected: set[tuple[int, StatementType]] = set()
    for kind in StatementType:
        location, chosen, notes = _select(kind, candidates, views, folios)
        statements[kind] = location
        selected |= {(page, kind) for page in chosen}
        warnings += notes

    if statements[StatementType.INCOME_STATEMENT].status == "not_found" and not any(
        c.statement_type is StatementType.INCOME_STATEMENT for c in candidates
    ):
        soci = statements[StatementType.COMPREHENSIVE_INCOME]
        if soci.status == "found":
            statements[StatementType.INCOME_STATEMENT] = soci.model_copy(
                update={
                    "statement_type": StatementType.INCOME_STATEMENT,
                    "source_type": StatementType.COMPREHENSIVE_INCOME,
                }
            )
            warnings = [
                w
                for w in warnings
                if not (
                    w.code == "statement_not_found"
                    and w.statement is StatementType.INCOME_STATEMENT
                )
            ]
            warnings.append(
                LocateWarning(
                    code="income_statement_from_comprehensive_income",
                    message=f"No separate income statement: the statement of comprehensive income "
                    f"on p.{soci.pages[0]} is used as the income statement",
                    page=soci.pages[0],
                    statement=StatementType.INCOME_STATEMENT,
                )
            )

    income = statements[StatementType.INCOME_STATEMENT]
    balance = statements[StatementType.BALANCE_SHEET]
    profile = profile_document(
        [views[p] for p in income.pages] if income.status == "found" else [],
        [views[p] for p in balance.pages] if balance.status == "found" else [],
        [loc.title for loc in statements.values() if loc.title],
    )
    warnings += _profile_warnings(
        profile.document_type, profile.balance_sheet_classified, balance, profile.evidence
    )

    ordered = sorted(candidates, key=lambda c: (_ORDER[c.statement_type], -c.score, c.page))
    return LocateResult(
        locator_version=LOCATOR_VERSION,
        page_count=layer.page_count,
        folio_offset=folios.offset,
        statements=statements,
        candidates=tuple(
            c.model_copy(update={"selected": (c.page, c.statement_type) in selected})
            for c in ordered
        ),
        profile=profile,
        warnings=tuple(warnings),
    )


# ------------------------------------------------------------------------------ candidates


def _page_candidates(
    view: PageView,
    hints: Mapping[int, Sequence[LocationHint]],
    paths: Mapping[int, tuple[str, ...]],
    folios: Folios,
) -> Iterable[PageCandidate]:
    page = view.page.page
    titles: list[tuple[VisualLine, TitleMatch]] = [
        (line, match) for line in view.title_lines if (match := match_title(line.text))
    ]
    page_hints = hints.get(page, [])
    kinds = {m.statement_type for _, m in titles} | {h.match.statement_type for h in page_hints}
    column_labels = [v.text for v in view.band(ENTITY_COLUMN_BAND) if is_entity_label(v.text)]
    for kind in sorted(kinds, key=_ORDER.__getitem__):
        own = [(line, m) for line, m in titles if m.statement_type is kind]
        own.sort(key=lambda lm: lm[1].continued)  # a fresh title beats a "continued" one
        title_line, title = own[0] if own else (None, None)
        kind_hints = [h for h in page_hints if h.match.statement_type is kind]
        score, signals = score_page(view, kind, title, kind_hints)

        if title_line is not None:
            header = [
                v.text
                for v in view.lines
                if v.bbox[3] <= title_line.bbox[1] + 1
                and not view.is_chrome(v)
                and v is not title_line
            ]
        else:
            header = [v.text for v in view.band(HEADER_BAND)]
        title_scope, title_text = (title.scope, title.text) if title else (None, None)
        if title_scope is None:
            scoped = next((h for h in kind_hints if h.match.scope is not None), None)
            if scoped is not None:
                title_scope, title_text = scoped.match.scope, scoped.source
        scope, evidence = classify_scope(
            title_scope, title_text, column_labels, header, paths[page]
        )

        excluded = exclusion_reason(header, paths[page])
        if excluded is None and scope is Scope.COMPANY:
            excluded = f"company-only statement ({evidence})"
        yield PageCandidate(
            page=page,
            page_label=view.page.label or folios.label(page),
            statement_type=kind,
            title=title.text if title else None,
            continued=bool(title and title.continued),
            scope=scope,
            scope_evidence=evidence,
            score=score,
            signals=signals,
            excluded=excluded,
        )


def _resolve_unknown_scope(candidates: list[PageCandidate]) -> list[PageCandidate]:
    """No entity qualifier anywhere means one set of statements (EXTRACTION section 1.2).
    If the report does name entities, an unnamed page cannot be trusted as the group's."""
    scoped = any(c.scope in (Scope.GROUP, Scope.COMPANY, Scope.MIXED) for c in candidates)
    out = []
    for c in candidates:
        if c.scope is not Scope.UNKNOWN:
            out.append(c)
        elif not scoped:
            out.append(
                c.model_copy(
                    update={
                        "scope": Scope.SINGLE_ENTITY,
                        "scope_evidence": "one set of statements; no entity qualifier anywhere",
                    }
                )
            )
        elif c.excluded is None:
            out.append(
                c.model_copy(
                    update={
                        "excluded": "names no entity, but the report has group or company pages"
                    }
                )
            )
        else:
            out.append(c)
    return out


# ------------------------------------------------------------------------------ selection


def _select(
    kind: StatementType,
    candidates: Sequence[PageCandidate],
    views: Mapping[int, PageView],
    folios: Folios,
) -> tuple[StatementLocation, list[int], list[LocateWarning]]:
    pool = [c for c in candidates if c.statement_type is kind]
    eligible = sorted(
        (
            c
            for c in pool
            if c.excluded is None
            and c.scope in SELECTABLE_SCOPES
            and c.score >= SELECT_THRESHOLD
            and not c.continued
        ),
        key=lambda c: (-c.score, c.page),
    )
    if not eligible:
        return (
            StatementLocation(statement_type=kind, status="not_found"),
            [],
            _not_found(kind, pool),
        )

    best = eligible[0]
    run, links = _follow(best.page, kind, views)
    rivals = [c for c in eligible[1:] if c.page not in run and best.score - c.score <= TIE_MARGIN]
    label = [views[p].page.label or folios.label(p) for p in run]
    spread = any(is_spread(views[p]) for p in run)
    if rivals:
        rival = rivals[0]
        pages = tuple(sorted({*run, rival.page}))
        location = StatementLocation(
            statement_type=kind,
            status="ambiguous",
            scope=best.scope,
            pages=pages,
            page_labels=tuple(views[p].page.label or folios.label(p) for p in pages),
            title=best.title,
            score=best.score,
            spread=spread,
        )
        warning = LocateWarning(
            code="entity_scope_ambiguous",
            message=f"Two {HUMAN[kind]} candidates score within {TIE_MARGIN}: "
            f"p.{best.page} ({best.score:.2f}, {best.scope_evidence}) and "
            f"p.{rival.page} ({rival.score:.2f}, {rival.scope_evidence}); both go to review",
            page=best.page,
            statement=kind,
        )
        return location, list(pages), [warning]

    location = StatementLocation(
        statement_type=kind,
        status="found",
        scope=best.scope,
        pages=tuple(run),
        page_labels=tuple(label),
        title=best.title,
        score=best.score,
        continuations=tuple(links),
        spread=spread,
    )
    notes = [
        LocateWarning(
            code="multi_page_table",
            message=f"The {HUMAN[kind]} continues from p.{link.page - 1} to "
            f"p.{link.page}: {link.evidence}",
            page=link.page,
            statement=kind,
        )
        for link in links
    ]
    return location, list(run), notes


def _follow(
    start: int, kind: StatementType, views: Mapping[int, PageView]
) -> tuple[list[int], list[Continuation]]:
    run, links = [start], []
    while run[-1] + 1 in views:
        link = continues(views[run[-1]], views[run[-1] + 1], kind)
        if link is None:
            break
        run.append(link.page)
        links.append(link)
    return run, links


def _not_found(kind: StatementType, pool: Sequence[PageCandidate]) -> list[LocateWarning]:
    if kind not in (StatementType.INCOME_STATEMENT, StatementType.BALANCE_SHEET):
        return []
    if not pool:
        detail = "no page carries its title, bookmark or contents entry"
    else:
        rejected = sorted(pool, key=lambda c: (-c.score, c.page))[:4]
        detail = "rejected: " + "; ".join(
            f"p.{c.page} {c.excluded or ('continued title' if c.continued else '')}".rstrip()
            + (f" (score {c.score:.2f} < {SELECT_THRESHOLD})" if c.score < SELECT_THRESHOLD else "")
            for c in rejected
        )
    return [
        LocateWarning(
            code="statement_not_found",
            message=f"No {HUMAN[kind]} found: {detail}. Point to the page to continue.",
            statement=kind,
        )
    ]


def _profile_warnings(
    kind: DocumentType,
    classified: bool | None,
    balance: StatementLocation,
    evidence: Mapping[str, tuple[str, ...]],
) -> list[LocateWarning]:
    page = balance.pages[0] if balance.pages else None
    notes: list[LocateWarning] = []
    if kind is DocumentType.BANK:
        notes.append(
            LocateWarning(
                code="bank_layout",
                message="Bank layout: "
                + ", ".join(evidence["bank"])
                + " on the located statements; revenue, current assets and current liabilities "
                "are null by design",
                page=page,
            )
        )
    if kind is DocumentType.NHS_TRUST:
        notes.append(
            LocateWarning(
                code="public_sector_layout",
                message="NHS layout: " + ", ".join(evidence["nhs"]),
                page=page,
            )
        )
    if classified is False:
        notes.append(
            LocateWarning(
                code="unclassified_balance_sheet",
                message=f"The balance sheet on p.{page} has no current/non-current split; current "
                "assets and current liabilities are null by design and the current ratio does "
                "not apply",
                page=page,
                statement=StatementType.BALANCE_SHEET,
            )
        )
    if kind is DocumentType.OTHER:
        seen = "; ".join(f"{k}: {', '.join(v) or 'none'}" for k, v in evidence.items())
        notes.append(
            LocateWarning(
                code="document_type_ambiguous",
                message=f"Document type unclear ({seen}); corporate ratios are withheld until a "
                "reviewer sets the type",
                page=page,
            )
        )
    return notes
