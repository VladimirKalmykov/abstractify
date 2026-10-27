"""Example custom embedding adapter.

Point config `custom_adapter` at a copy of this file (or your own service client).

Required:
    embed(texts: list[str]) -> list[list[float]]

Optional:
    retrieve(query: str, items: list[dict], k: int) -> list[dict]
"""

from __future__ import annotations


def embed(texts: list[str]) -> list[list[float]]:
    """Deterministic toy vectors — replace with a call to your local embedding service."""
    out: list[list[float]] = []
    for text in texts:
        acc = [0.0] * 8
        for i, ch in enumerate(text.encode("utf-8")):
            acc[i % 8] += (ch - 64) / 128.0
        out.append(acc)
    return out


def retrieve(query: str, items: list[dict], k: int = 10) -> list[dict]:
    q = query.lower()
    ranked = sorted(
        items,
        key=lambda it: -(
            (q in str(it.get("name", "")).lower()) * 5
            + (q in str(it.get("description", "")).lower()) * 2
        ),
    )
    return ranked[:k]
