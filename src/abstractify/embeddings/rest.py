from __future__ import annotations

import json
import urllib.error
import urllib.request

from abstractify.embeddings.base import Embedder


class RestEmbedder(Embedder):
    """POST {"texts": [...]} to an external embeddings HTTP endpoint."""

    name = "rest"

    def __init__(self, url: str, api_key: str = "") -> None:
        if not url:
            raise ValueError("embed_url is required for REST embedding mode")
        self.url = url
        self.api_key = api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = json.dumps({"texts": texts, "input": texts}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"REST embedder failed: {exc}") from exc
        return _parse_embeddings(body, expected=len(texts))


def _parse_embeddings(body: object, expected: int) -> list[list[float]]:
    if isinstance(body, dict):
        if "embeddings" in body and isinstance(body["embeddings"], list):
            vecs = body["embeddings"]
        elif "data" in body and isinstance(body["data"], list):
            vecs = [row["embedding"] for row in body["data"]]
        elif "vector" in body:
            vecs = [body["vector"]]
        else:
            raise RuntimeError(f"REST embedder: unexpected JSON keys {list(body)}")
    elif isinstance(body, list):
        vecs = body
    else:
        raise RuntimeError("REST embedder: response is not JSON object/list")
    if len(vecs) != expected:
        raise RuntimeError(f"REST embedder: got {len(vecs)} vectors, expected {expected}")
    return [[float(x) for x in v] for v in vecs]
