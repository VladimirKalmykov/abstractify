from __future__ import annotations

import math
import re
from collections import Counter

from abstractify.embeddings.base import Embedder

TOKEN_RE = re.compile(r"[a-z0-9_]+", re.I)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


class NoneEmbedder(Embedder):
    """No vectors. Search uses substring + IDF over names and descriptions."""

    name = "none"

    def embed(self, texts: list[str], *, input_type: str = "document") -> list[list[float]]:
        del input_type
        return [[] for _ in texts]


def idf_search(query: str, items: list[dict], k: int = 20) -> list[dict]:
    """Rank items by name substring boost + TF-IDF cosine on name+description."""
    q = query.strip()
    if not q:
        return items[:k]
    q_low = q.lower()
    q_tokens = tokenize(q)
    docs = [tokenize(f"{it.get('name', '')} {it.get('description', '')}") for it in items]
    n = max(len(docs), 1)
    df: Counter[str] = Counter()
    for toks in docs:
        df.update(set(toks))

    def idf(tok: str) -> float:
        return math.log((n + 1) / (df.get(tok, 0) + 1)) + 1.0

    q_tf = Counter(q_tokens)
    q_vec = {t: q_tf[t] * idf(t) for t in q_tf}

    scored: list[tuple[float, dict]] = []
    for item, toks in zip(items, docs):
        name = str(item.get("name", "")).lower()
        desc = str(item.get("description", "")).lower()
        score = 0.0
        if q_low and q_low in name:
            score += 8.0
        elif q_low and q_low in desc:
            score += 3.0
        tf = Counter(toks)
        d_vec = {t: tf[t] * idf(t) for t in tf}
        score += _cosine(q_vec, d_vec)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:k]]


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
