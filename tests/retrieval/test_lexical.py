"""BM25 with heading field, stopwords, and the on-disk embedding memo. No model, no network."""

from __future__ import annotations

from pathlib import Path

from finintel.retrieval.embeddings import FakeEmbedder
from finintel.retrieval.lexical import Bm25, terms
from finintel.retrieval.local_models import MemoEmbedder
from finintel.retrieval.pipeline import InMemoryIndex
from tests.retrieval.test_retrieval import _chunk


def _with_heading(cid: str, text: str, heading: tuple[str, ...]):  # type: ignore[no-untyped-def]
    return _chunk(cid, text).model_copy(update={"heading_path": heading})


def test_terms_drop_stopwords_and_plural_s() -> None:
    assert terms("How does Unilever describe its strategies?") == [
        "unilever",
        "describe",
        "strategie",
    ]
    assert terms("Directors' risks") == ["director", "risk"]


def test_heading_match_outranks_a_vague_body_mention() -> None:
    body = "the group has a strategy for growth and mentions strategy once in passing"
    chunks = [
        _with_heading("vague", body * 2, ("Report", "Notes")),
        _with_heading("titled", "plans for growth in the coming years", ("Report", "Our Strategy")),
    ]
    ranked = Bm25(chunks).rank("How does the company describe its strategy?", 5)
    assert ranked[0][0] == "titled"


def test_root_heading_does_not_match_everything() -> None:
    chunks = [
        _with_heading("a", "alpha text", ("STRATEGY ROOT", "Section", "Leaf A")),
        _with_heading("b", "beta text", ("STRATEGY ROOT", "Section", "Leaf B")),
    ]
    assert Bm25(chunks).rank("strategy", 5) == []


def test_in_memory_index_uses_bm25_for_lexical() -> None:
    chunks = [
        _with_heading("t", "x", ("R", "Going concern")),
        _with_heading("u", "y", ("R", "Other")),
    ]
    assert InMemoryIndex(chunks, FakeEmbedder()).lexical("going concern", 5) == ["t"]


def test_memo_embedder_reuses_stored_vectors(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class Counting(FakeEmbedder):
        def embed(self, texts: list[str]) -> list[list[float]]:
            calls.append(list(texts))
            return super().embed(texts)

    first = MemoEmbedder(Counting(), tmp_path).embed(["a b", "c d", "a b"])
    again = MemoEmbedder(Counting(), tmp_path).embed(["c d", "a b"])
    assert calls == [["a b", "c d"]]  # second instance read the file; no new embedding
    assert again == [first[1], first[0]]
