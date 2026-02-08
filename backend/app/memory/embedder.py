from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

import httpx


class EmbeddingError(RuntimeError):
    """Raised when embedding generation fails."""


class Embedder(ABC):
    """Embedding interface for pluggable providers."""

    provider: str
    model_name: str
    dimension: int

    @abstractmethod
    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate vectors for each text input."""


class DeterministicEmbedder(Embedder):
    """Offline deterministic embedding generator for tests and local runs."""

    provider = "deterministic"

    def __init__(self, dimension: int, model_name: str = "deterministic-v1") -> None:
        if dimension <= 0:
            raise EmbeddingError("Embedding dimension must be > 0")
        self.dimension = int(dimension)
        self.model_name = model_name

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vectors.append(self._embed_single(text))
        return vectors

    def _embed_single(self, text: str) -> list[float]:
        cleaned = text.strip().lower()
        vector = [0.0] * self.dimension
        if not cleaned:
            vector[0] = 1.0
            return vector

        for token in self._tokenize(cleaned):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:4], byteorder="big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            magnitude = 1.0 + (digest[5] / 255.0)
            vector[index] += sign * magnitude
        return _normalize_vector(vector)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        tokens: list[str] = []
        buffer: list[str] = []
        for ch in text:
            if ch.isspace():
                if buffer:
                    tokens.append("".join(buffer))
                    buffer.clear()
                continue
            if ch.isalnum() or ch in {"_", "-"}:
                buffer.append(ch)
                continue
            if buffer:
                tokens.append("".join(buffer))
                buffer.clear()
            tokens.append(ch)
        if buffer:
            tokens.append("".join(buffer))
        return tokens


class OpenAIEmbedder(Embedder):
    """OpenAI-compatible embedding provider implementation."""

    provider = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        dimension: int,
        timeout_sec: float = 20.0,
    ) -> None:
        if dimension <= 0:
            raise EmbeddingError("Embedding dimension must be > 0")
        if not api_key.strip():
            raise EmbeddingError("OpenAI embedding API key is empty")
        self.model_name = model_name
        self.dimension = int(dimension)
        self._timeout_sec = timeout_sec
        self._api_key = api_key
        normalized = base_url.rstrip("/")
        self._endpoint = f"{normalized}/v1/embeddings"

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self.model_name, "input": list(texts)}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
                response = await client.post(self._endpoint, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingError("OpenAI embedding request failed") from exc

        data = response.json()
        vectors = self._parse_embeddings(data, len(texts))
        return [_normalize_vector(vector) for vector in vectors]

    def _parse_embeddings(self, payload: Any, expected_size: int) -> list[list[float]]:
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) != expected_size:
            raise EmbeddingError("Embedding response shape is invalid")

        vectors: list[list[float]] = []
        for row in rows:
            embedding = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(embedding, list):
                raise EmbeddingError("Embedding row is missing vector data")
            if len(embedding) != self.dimension:
                raise EmbeddingError("Embedding dimension mismatch")
            try:
                vector = [float(value) for value in embedding]
            except (TypeError, ValueError) as exc:
                raise EmbeddingError("Embedding contains non-numeric values") from exc
            vectors.append(vector)
        return vectors


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(item * item for item in vector))
    if norm <= 0:
        return vector
    return [item / norm for item in vector]
