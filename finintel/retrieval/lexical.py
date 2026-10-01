"""In-memory BM25 over chunk text and heading (RAG section 3.2, lexical leg).

Fields are combined BM25F-style: a term's frequency in a chunk is `tf_text + HEADING_WEIGHT *
tf_heading`, and length is normalised on the combined length. The heading is the last two elements
of `heading_path` (the leaf and its parent): the root bookmark of a large report appears on every
chunk and would match everything. This is what lets a section titled "Our Strategy" outrank a
passage that only sits semantically near the word. Stopwords are removed from query and chunk.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from finintel.narrative.models import Chunk

HEADING_WEIGHT = 3.0
K1 = 1.2
B = 0.75
HEADING_DEPTH = 2

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP_TEXT = """
a an and are as at be been but by did do does for from had has have how i in into is it
its of on or our said say says that the their there these they this to was we were what
when which who why will with would you your
"""
STOPWORDS = frozenset(_STOP_TEXT.split())


def terms(text: str) -> list[str]:
    out = []
    for tok in _TOKEN.findall(text.lower().replace("\u2019", "").replace("'", "")):
        if tok in STOPWORDS:
            continue
        out.append(
            tok[:-1] if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss") else tok
        )
    return out


class Bm25:
    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self._tf: dict[str, Counter[str]] = {}
        self._len: dict[str, float] = {}
        df: Counter[str] = Counter()
        for c in chunks:
            tf: Counter[str] = Counter(terms(c.text))
            for term in terms(" ".join(c.heading_path[-HEADING_DEPTH:])):
                tf[term] += HEADING_WEIGHT  # type: ignore[assignment]
            self._tf[c.chunk_id] = tf
            self._len[c.chunk_id] = float(sum(tf.values()))
            df.update(tf.keys())
        n = len(chunks)
        self._avg = (sum(self._len.values()) / n) if n else 0.0
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def rank(self, query: str, k: int) -> list[tuple[str, float]]:
        q = set(terms(query))
        scored: list[tuple[str, float]] = []
        for cid, tf in self._tf.items():
            norm = K1 * (1 - B + B * self._len[cid] / self._avg) if self._avg else K1
            s = sum(self._idf[t] * tf[t] * (K1 + 1) / (tf[t] + norm) for t in q if t in tf)
            if s > 0:
                scored.append((cid, s))
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return scored[:k]


def evidence_coverage(bm25: Bm25, query: str, depth: int = 20) -> float:
    """How much of the query's meaning one retrieved chunk carries (0 to 1).

    The share of the query's content words, weighted by rarity (idf), found together in the best of
    the top `depth` lexical chunks. A word that appears nowhere in the document counts at maximum
    weight, so a question about a figure or entity the report never mentions scores low however
    close its dense neighbours are. Used as an evidence floor before any model is called.
    """
    wanted = set(terms(query))
    if not wanted:
        return 0.0
    n = len(bm25._tf)
    unseen = math.log(1 + (n + 0.5) / 0.5)
    weight = {t: bm25._idf.get(t, unseen) for t in wanted}
    total = sum(weight.values())
    best = 0.0
    for cid, _ in bm25.rank(query, depth):
        present = sum(w for t, w in weight.items() if t in bm25._tf[cid])
        best = max(best, present / total)
    return best
