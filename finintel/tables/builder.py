"""Build one engine's StatementTable for one located statement (EXTRACTION sections 2 and 4.1).

Pages of a multi-page statement are read one by one and appended in order. Every row keeps its
own page, the section heading carries across the break, and continuation-page value columns map
to the first page's by position only when the counts match (the locator already required that);
if they do not, that page's figures are left out and the table says so.
"""

from __future__ import annotations

from finintel.locate.models import StatementLocation
from finintel.locate.signals import PageView
from finintel.parse.engines.base import ParsedTables
from finintel.parse.text_layer import TextLayer
from finintel.tables.grid import PageGrid, build_grid
from finintel.tables.models import Column, ColumnKind, StatementTable
from finintel.tables.regions import statement_regions
from finintel.tables.rows import DraftRow, finalise, join_wrapped, page_drafts


def build_statement_table(
    layer: TextLayer, location: StatementLocation, parsed: ParsedTables
) -> StatementTable:
    columns: list[Column] = []
    drafts: list[DraftRow] = []
    strategies: dict[int, str] = {}
    notes: list[str] = []
    for region in statement_regions(layer, location):
        page = layer.page(region.page)
        if page.rotation != 0:
            notes.append(f"p.{region.page}: rotated page (/Rotate {page.rotation}); not read in v1")
            continue
        view = PageView(page)
        grid = build_grid(view, region, parsed)
        strategies[region.page] = grid.strategy
        notes.extend(grid.notes)
        page_columns = _columns(grid)
        values = [c for c in page_columns if c.kind is ColumnKind.VALUE]
        if not columns:
            columns = page_columns
        elif len(values) != (first := sum(c.kind is ColumnKind.VALUE for c in columns)):
            notes.append(
                f"p.{region.page}: {len(values)} value columns, first page has {first}; "
                "figures on this page left out"
            )
            continue
        column_of = {id(band): f"v{i}" for i, band in enumerate(grid.value_bands, start=1)}
        drafts.extend(page_drafts(view, grid, column_of))
    if len(location.pages) > 1:
        notes.append(f"merged pages {list(location.pages)}; section headings carried across")
    return StatementTable(
        statement_type=location.statement_type,
        scope=location.scope,
        engine=parsed.engine,
        engine_version=parsed.engine_version,
        family=parsed.family,
        pages=location.pages,
        strategies=strategies,
        columns=tuple(columns),
        rows=tuple(finalise(join_wrapped(drafts))),
        notes=tuple(notes),
    )


def _columns(grid: PageGrid) -> list[Column]:
    columns: list[Column] = []
    if grid.note_band is not None:
        columns.append(
            Column(
                column_id="note",
                kind=ColumnKind.NOTE,
                header_text=grid.header_text(grid.note_band),
                x0=round(grid.note_band.x0, 2),
                x1=round(grid.note_band.x1, 2),
                evidence=grid.note_evidence,
            )
        )
    for i, band in enumerate(grid.value_bands, start=1):
        numeric = sum(1 for c in band.cells if c.parsed is not None)
        columns.append(
            Column(
                column_id=f"v{i}",
                kind=ColumnKind.VALUE,
                header_text=grid.header_text(band),
                x0=round(band.x0, 2),
                x1=round(band.x1, 2),
                evidence=f"{numeric}/{len(band.cells)} cells parse as numbers",
            )
        )
    return columns
