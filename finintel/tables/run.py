"""Run the text-layer table engines on the located statements and build their StatementTables.

Engines read only the statement regions (pdfplumber is slow; never on every page), and each
engine's ParsedTables is cached per document, engine version and region set.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from finintel.cache import StageCache, StageKey
from finintel.locate.models import EXTRACTED, LocateResult, StatementType
from finintel.parse.engines.base import BBox, ParsedTables
from finintel.parse.engines.pdfplumber_engine import PARSE_VERSION as PLUMBER_VERSION
from finintel.parse.engines.pdfplumber_engine import PdfplumberEngine
from finintel.parse.engines.pymupdf_tables_engine import PARSE_VERSION as PYMUPDF_VERSION
from finintel.parse.engines.pymupdf_tables_engine import PymupdfTablesEngine
from finintel.parse.text_layer import TextLayer
from finintel.tables.builder import build_statement_table
from finintel.tables.models import StatementTable
from finintel.tables.regions import statement_regions

TextLayerEngine = PdfplumberEngine | PymupdfTablesEngine


def text_layer_engines() -> list[TextLayerEngine]:
    return [PdfplumberEngine(), PymupdfTablesEngine()]


def statement_tables(
    pdf: Path,
    sha256: str,
    layer: TextLayer,
    located: LocateResult,
    cache: StageCache,
) -> dict[StatementType, dict[str, StatementTable]]:
    """{statement type: {engine name: table}} for every located (found) extracted statement."""
    found = [located.statements[k] for k in EXTRACTED if located.statements[k].status == "found"]
    clips: dict[int, list[BBox]] = defaultdict(list)
    for location in found:
        for region in statement_regions(layer, location):
            clips[region.page].append(region.bbox)
    if not clips:
        return {}
    tables: dict[StatementType, dict[str, StatementTable]] = defaultdict(dict)
    for engine in text_layer_engines():
        parsed = _parsed(engine, pdf, sha256, dict(clips), cache)
        for location in found:
            tables[location.statement_type][engine.name] = build_statement_table(
                layer, location, parsed
            )
    return dict(tables)


def _parsed(
    engine: TextLayerEngine, pdf: Path, sha256: str, clips: dict[int, list[BBox]], cache: StageCache
) -> ParsedTables:
    version = PLUMBER_VERSION if isinstance(engine, PdfplumberEngine) else PYMUPDF_VERSION
    config = {
        "engine": engine.version,
        "clips": {str(p): [list(c) for c in cs] for p, cs in sorted(clips.items())},
    }
    key = StageKey.build(sha256, f"{engine.name}_parse", version, config)
    data, _ = cache.memo(
        key,
        "parsed.json",
        lambda: engine.parse(pdf, sorted(clips), clips).model_dump_json().encode("utf-8"),
    )
    return ParsedTables.model_validate_json(data)
