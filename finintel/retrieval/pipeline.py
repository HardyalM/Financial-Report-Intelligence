"""Per-topic hybrid retrieval (RAG section 3.2). Backend-agnostic: the Postgres index implements
`IndexBackend`; `InMemoryIndex` implements it for tests and eval without a database.

Order: dense + lexical top 50 per query -> RRF (k=60) top 40 -> rerank -> +0.05 section prior ->
at most 3 per section, top 8 -> evidence floor. Scores are used for ranking only; they never
become numbers in commentary.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from finintel.locate.models import DocumentType
from finintel.narrative.models import Chunk
from finintel.retrieval.embeddings import Embedder, cosine, tokens
from finintel.retrieval.lexical import Bm25, evidence_coverage
from finintel.retrieval.queries import OPTIONAL_TOPICS, QUERY_SET_VERSION, TopicQueries, query_set

PER_LIST = 50
RRF_K = 60
FUSED_KEEP = 40
PRIOR_BONUS = 0.05
PER_SECTION_MAX = 3
TOP_N = 8
#: Initial value; calibrated against company_a.retrieval.json at M4.2.
EVIDENCE_FLOOR = 0.30
FLOOR_MIN_CHUNKS = 2
#: Query-evidence coverage below which a question gets `insufficient_evidence` before any model
#: is called (lexical.evidence_coverage). Calibrated on the five E3 retrieval queries only: their
#: minimum is 0.73, less a 0.05 margin. It was not tuned on the QA labels; it refuses some
#: answerable questions whose rare words the report does not repeat (reported in STATUS).
COVERAGE_FLOOR = 0.68


class ChunkLike(Protocol):
    """What retrieval reads from a chunk. `narrative.models.Chunk` and database rows satisfy it."""

    @property
    def chunk_id(self) -> str: ...
    @property
    def text(self) -> str: ...
    @property
    def section_id(self) -> str: ...


class IndexBackend(Protocol):
    def dense(self, query: str, k: int) -> list[str]: ...
    def lexical(self, query: str, k: int) -> list[str]: ...
    def chunk(self, chunk_id: str) -> ChunkLike: ...


class Reranker(Protocol):
    model_id: str

    def score(self, query: str, chunks: Sequence[ChunkLike]) -> list[float]: ...


@dataclass(frozen=True)
class Retrieved:
    chunk_id: str
    rrf: float
    rerank: float
    score: float  # rerank + prior
    prior: bool


@dataclass(frozen=True)
class TopicResult:
    topic: str
    status: str  # "ok" | "insufficient_evidence" | "omitted"
    chunks: tuple[Retrieved, ...]
    query_set_version: str = QUERY_SET_VERSION


def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal rank fusion; ties break by id so output is deterministic."""
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def retrieve_topic(topic: TopicQueries, backend: IndexBackend, reranker: Reranker) -> TopicResult:
    rankings: list[list[str]] = []
    for q in topic.queries:
        rankings.append(backend.dense(q, PER_LIST))
        rankings.append(backend.lexical(q, PER_LIST))
    fused = rrf(rankings)[:FUSED_KEEP]
    if not fused:
        return _floor(topic.topic, ())
    chunks = [backend.chunk(cid) for cid, _ in fused]
    composed = " ".join(topic.queries)
    rerank = reranker.score(composed, chunks)
    scored = []
    for (cid, fused_score), chunk, rr in zip(fused, chunks, rerank, strict=True):
        prior = chunk.section_id in topic.priors
        scored.append(
            (Retrieved(cid, fused_score, rr, rr + (PRIOR_BONUS if prior else 0.0), prior), chunk)
        )
    scored.sort(key=lambda t: (-t[0].score, t[0].chunk_id))
    taken: list[Retrieved] = []
    per_section: dict[str, int] = defaultdict(int)
    for item, chunk in scored:
        if per_section[chunk.section_id] >= PER_SECTION_MAX:
            continue
        per_section[chunk.section_id] += 1
        taken.append(item)
        if len(taken) == TOP_N:
            break
    return _floor(topic.topic, tuple(taken))


def _floor(topic: str, chunks: tuple[Retrieved, ...]) -> TopicResult:
    # The floor tests the rerank score alone: the prior is a tie-breaker, not evidence.
    strong = sum(1 for c in chunks if c.rerank >= EVIDENCE_FLOOR)
    if strong >= FLOOR_MIN_CHUNKS:
        return TopicResult(topic, "ok", chunks)
    status = "omitted" if topic in OPTIONAL_TOPICS else "insufficient_evidence"
    return TopicResult(topic, status, chunks)


def retrieve_all(
    document_type: DocumentType, backend: IndexBackend, reranker: Reranker
) -> list[TopicResult]:
    return [retrieve_topic(t, backend, reranker) for t in query_set(document_type)]


class FusionOrderReranker:
    """No rerank model: keeps the fused (RRF) order by scoring on rank. The scores are positions,
    not relevance, so the evidence floor means nothing in this mode; it is used for ranking only."""

    model_id = "none (RRF order)"

    def score(self, query: str, chunks: Sequence[ChunkLike]) -> list[float]:
        n = len(chunks)
        return [1.0 - i / max(n, 1) for i in range(n)]


class OverlapReranker:
    """Offline reranker: fraction of query terms present in the chunk. Test/eval stand-in only."""

    model_id = "fake-overlap-v1"

    def score(self, query: str, chunks: Sequence[ChunkLike]) -> list[float]:
        q = set(tokens(query))
        return [len(q & set(tokens(c.text))) / len(q) if q else 0.0 for c in chunks]


class InMemoryIndex:
    """Dense (cosine) and lexical (term overlap) over in-memory chunks. Tables are not indexed."""

    def __init__(self, chunks: Sequence[Chunk], embedder: Embedder) -> None:
        self._chunks = {c.chunk_id: c for c in chunks if not c.is_table}
        self._bm25 = Bm25(list(self._chunks.values()))
        self._embedder = embedder
        ids = sorted(self._chunks)
        self._vecs = dict(
            zip(ids, embedder.embed([self._chunks[i].text for i in ids]), strict=True)
        )

    def dense(self, query: str, k: int) -> list[str]:
        qv = self._embedder.embed([query])[0]
        ranked = sorted(self._vecs, key=lambda i: (-cosine(qv, self._vecs[i]), i))
        return ranked[:k]

    def lexical(self, query: str, k: int) -> list[str]:
        return [cid for cid, _ in self._bm25.rank(query, k)]

    def coverage(self, query: str) -> float:
        return evidence_coverage(self._bm25, query)

    def chunk(self, chunk_id: str) -> Chunk:
        return self._chunks[chunk_id]
