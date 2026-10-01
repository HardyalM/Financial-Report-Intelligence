"""Retrieval pipeline without a database: fusion, priors, diversity, floor, query-set selection."""

from __future__ import annotations

import re

from finintel.locate.models import DocumentType
from finintel.narrative import CHUNKER_VERSION
from finintel.narrative.models import Chunk
from finintel.narrative.sections import _RULES
from finintel.retrieval.embeddings import FakeEmbedder
from finintel.retrieval.pipeline import (
    EVIDENCE_FLOOR,
    PRIOR_BONUS,
    InMemoryIndex,
    OverlapReranker,
    retrieve_all,
    retrieve_topic,
    rrf,
)
from finintel.retrieval.queries import TOPICS, TopicQueries, query_set

KNOWN_SECTIONS = {sid for sid, _ in _RULES} | {
    "ceo_review", "financial_review", "segment_review", "strategy", "narrative_other",
}  # fmt: skip


def _chunk(cid: str, text: str, section: str = "narrative_other", table: bool = False) -> Chunk:
    return Chunk(
        chunk_id=cid, chunker_version=CHUNKER_VERSION, document_sha256="aa" * 32, text=text,
        token_count=len(text.split()), char_start=0, char_end=len(text), page_start=1,
        page_end=1, char_page_map=((0, 1),), line_boxes=(), section_id=section,
        heading_path=(section,), is_table=table,
    )  # fmt: skip


def test_rrf_fuses_and_is_deterministic() -> None:
    fused = rrf([["a", "b", "c"], ["b", "a", "d"]])
    assert [cid for cid, _ in fused][:2] == ["a", "b"]  # equal scores: id order
    assert fused[0][1] == 1 / 61 + 1 / 62
    assert rrf([["x"], ["y"]]) == rrf([["x"], ["y"]])


def test_query_variants_selected_by_document_type() -> None:
    def risks(dt: DocumentType) -> tuple[str, ...]:
        return next(t.queries for t in query_set(dt) if t.topic == "strategic_risks")

    assert "Credit risk and expected credit losses" in risks(DocumentType.BANK)
    assert "Board assurance framework principal risks" in risks(DocumentType.NHS_TRUST)
    assert "Principal risks and uncertainties" in risks(DocumentType.CORPORATE)
    assert risks(DocumentType.BANK) != risks(DocumentType.CORPORATE)
    for dt in DocumentType:
        assert tuple(t.topic for t in query_set(dt)) == TOPICS


def test_priors_name_real_sections() -> None:
    for dt in DocumentType:
        for t in query_set(dt):
            assert t.priors <= KNOWN_SECTIONS, (dt, t.topic, t.priors - KNOWN_SECTIONS)


def test_retrieves_on_topic_and_ignores_tables() -> None:
    chunks = [
        _chunk("r1", "principal risks and uncertainties include supply chain disruption"),
        _chunk("r2", "emerging risks and risk mitigations and risk appetite were reviewed"),
        _chunk("x1", "the canteen menu changed in the spring"),
        _chunk("t1", "principal risks principal risks 1,234 5,678", table=True),
    ]
    index = InMemoryIndex(chunks, FakeEmbedder())
    topic = TopicQueries("strategic_risks", ("principal risks and uncertainties",), frozenset())
    result = retrieve_topic(topic, index, OverlapReranker())
    ids = [c.chunk_id for c in result.chunks]
    assert ids[0] == "r1" and "t1" not in ids


def test_prior_is_a_tiebreaker_and_diversity_caps_sections() -> None:
    text = "going concern basis of preparation"
    chunks = [_chunk(f"a{i}", text, "notes_accounting_policies") for i in range(5)]
    chunks.append(_chunk("p1", text, "going_concern"))
    topic = TopicQueries("t", ("going concern basis of preparation",), frozenset({"going_concern"}))
    result = retrieve_topic(topic, InMemoryIndex(chunks, FakeEmbedder()), OverlapReranker())
    assert result.chunks[0].chunk_id == "p1" and result.chunks[0].prior
    assert result.chunks[0].score == result.chunks[0].rerank + PRIOR_BONUS
    sections = [c.chunk_id[0] for c in result.chunks]
    assert sections.count("a") == 3  # PER_SECTION_MAX


def test_floor_gives_insufficient_evidence_or_omits_optional_topic() -> None:
    chunks = [_chunk("x1", "the canteen menu changed in the spring")]
    index = InMemoryIndex(chunks, FakeEmbedder())
    results = {r.topic: r for r in retrieve_all(DocumentType.CORPORATE, index, OverlapReranker())}
    assert results["strategic_risks"].status == "insufficient_evidence"
    assert results["liquidity_and_capital"].status == "omitted"


def test_prior_alone_cannot_clear_the_floor() -> None:
    weak = "capital"  # overlaps almost none of the composed query
    chunks = [_chunk(f"w{i}", weak, "going_concern") for i in range(3)]
    topic = TopicQueries(
        "t", tuple(f"query term{i} other{i}" for i in range(10)), frozenset({"going_concern"})
    )
    result = retrieve_topic(topic, InMemoryIndex(chunks, FakeEmbedder()), OverlapReranker())
    assert all(c.rerank < EVIDENCE_FLOOR for c in result.chunks)
    assert result.status == "insufficient_evidence"


def test_empty_index_is_insufficient() -> None:
    index = InMemoryIndex([], FakeEmbedder())
    result = retrieve_topic(query_set(DocumentType.CORPORATE)[1], index, OverlapReranker())
    assert result.status == "insufficient_evidence" and not result.chunks


def test_fake_embedder_is_deterministic_and_normalised() -> None:
    a, b = FakeEmbedder().embed(["Principal risks", "Principal risks"])
    assert a == b and abs(sum(x * x for x in a) - 1.0) < 1e-9
    assert re.fullmatch(r"fake-.*", FakeEmbedder.model_id)
