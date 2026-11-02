"""Ranked search over the manual sections: BM25, optionally fused with embeddings.

`get_policy_sections` fetches sections by id. This module answers the other kind of question,
the vague one ("posso devolver sem ter usado?"), by ranking the 28 sections. BM25 needs no
service. Embeddings are optional: they are requested on the first search, cached on disk by text
hash, and any failure falls back to BM25, so the project still runs offline and without a key.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from openai import OpenAI

from emporio.config import Settings
from emporio.policies import PolicySection
from emporio.results import error

DEFAULT_LIMIT = 3
MAX_LIMIT = 5
RRF_K = 60  # reciprocal rank fusion constant
_TITLE_WEIGHT = 3  # a word in the title counts as if it appeared three times in the body
_BM25_K1 = 1.5
_BM25_B = 0.75

_STOP_WORDS = frozenset(
    [
        "a",
        "o",
        "as",
        "os",
        "um",
        "uma",
        "uns",
        "umas",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "por",
        "para",
        "com",
        "sem",
        "sobre",
        "ao",
        "aos",
        "e",
        "ou",
        "que",
        "se",
        "eu",
        "me",
        "meu",
        "minha",
        "meus",
        "minhas",
        "voce",
        "voces",
        "vc",
        "tem",
        "ter",
        "ha",
        "ser",
        "sao",
        "foi",
        "eh",
        "e",
        "mais",
        "muito",
        "como",
        "qual",
        "quais",
        "quando",
        "onde",
        "quanto",
        "quantos",
        "quantas",
        "pode",
        "posso",
        "podem",
        "vai",
        "vou",
        "quero",
        "queria",
        "gostaria",
        "isso",
        "esse",
        "essa",
        "este",
        "esta",
        "aqui",
        "la",
        "ja",
        "nao",
        "sim",
        "ate",
        "tambem",
        "so",
    ]
)


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _stem(word: str) -> str:
    """Reduce the common Portuguese plurals so "devoluções" and "devolução" match."""
    if len(word) > 4:
        for suffix, repl in (("coes", "cao"), ("oes", "ao"), ("aes", "ao"), ("ais", "al")):
            if word.endswith(suffix):
                return word[: -len(suffix)] + repl
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", _strip_accents(text).lower())
    return [_stem(w) for w in words if w not in _STOP_WORDS]


class Bm25Index:
    def __init__(self, sections: Sequence[PolicySection]) -> None:
        self._ids = [s.id for s in sections]
        self._docs = [Counter(self._tokens(s)) for s in sections]
        self._lengths = [sum(doc.values()) for doc in self._docs]
        self._avg = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0
        document_frequency: Counter[str] = Counter()
        for doc in self._docs:
            document_frequency.update(doc.keys())
        total = len(self._docs)
        self._idf = {
            term: math.log(1 + (total - df + 0.5) / (df + 0.5))
            for term, df in document_frequency.items()
        }

    @staticmethod
    def _tokens(section: PolicySection) -> list[str]:
        return tokenize(section.title) * _TITLE_WEIGHT + tokenize(section.text)

    def rank(self, query: str) -> list[tuple[str, float]]:
        terms = set(tokenize(query))
        scored: list[tuple[str, float]] = []
        for section_id, doc, length in zip(self._ids, self._docs, self._lengths, strict=True):
            score = 0.0
            for term in terms:
                frequency = doc.get(term, 0)
                if not frequency:
                    continue
                norm = 1 - _BM25_B + _BM25_B * length / (self._avg or 1.0)
                score += (
                    self._idf[term] * frequency * (_BM25_K1 + 1) / (frequency + _BM25_K1 * norm)
                )
            if score > 0:
                scored.append((section_id, score))
        return sorted(scored, key=lambda item: -item[1])  # stable: ties keep manual order


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, in the same order."""


class OpenAIEmbedder:
    """Embeddings from any OpenAI-compatible endpoint (OpenRouter by default)."""

    def __init__(self, settings: Settings) -> None:
        self.model = settings.embedding_model
        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=30.0,
            max_retries=1,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


@dataclass(frozen=True)
class SearchHit:
    id: str
    title: str
    text: str
    score: float


@dataclass(frozen=True)
class SearchResult:
    method: str  # "bm25", "embeddings" or "hybrid"
    hits: list[SearchHit]


class PolicyRetriever:
    def __init__(
        self,
        sections: Sequence[PolicySection],
        embedder: Embedder | None = None,
        *,
        cache_path: Path | None = None,
    ) -> None:
        self._sections = tuple(sections)
        self._by_id = {s.id: s for s in self._sections}
        self._bm25 = Bm25Index(self._sections)
        self._embedder = embedder
        self._cache_path = cache_path
        self._cache: dict[str, list[float]] | None = None
        self._section_vectors: dict[str, list[float]] | None = None
        self._embedder_failed = False

    # -- vectors -------------------------------------------------------------------------------

    def _key(self, text: str) -> str:
        assert self._embedder is not None
        return hashlib.sha1(f"{self._embedder.model}|{text}".encode()).hexdigest()

    def _load_cache(self) -> dict[str, list[float]]:
        if self._cache is None:
            self._cache = {}
            if self._cache_path is not None and self._cache_path.is_file():
                try:
                    self._cache = json.loads(self._cache_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    self._cache = {}
        return self._cache

    def _save_cache(self) -> None:
        if self._cache_path is None or self._cache is None:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(self._cache), encoding="utf-8")
        except OSError:
            pass  # the cache is an optimisation; a read-only disk must not break the search

    def _vectors_for(self, texts: list[str]) -> list[list[float]]:
        assert self._embedder is not None
        cache = self._load_cache()
        missing = [t for t in dict.fromkeys(texts) if self._key(t) not in cache]
        if missing:
            for text, vector in zip(missing, self._embedder.embed(missing), strict=True):
                cache[self._key(text)] = vector
            self._save_cache()
        return [cache[self._key(t)] for t in texts]

    def _embedding_ranking(self, query: str) -> list[str]:
        if self._embedder is None or self._embedder_failed:
            raise RuntimeError("embeddings are not available")
        try:
            if self._section_vectors is None:
                texts = [f"{s.title}\n{s.text}" for s in self._sections]
                self._section_vectors = dict(
                    zip((s.id for s in self._sections), self._vectors_for(texts), strict=True)
                )
            (query_vector,) = self._vectors_for([query])
        except Exception as exc:
            self._embedder_failed = True
            raise RuntimeError(f"embeddings failed: {exc}") from exc
        scored = [
            (section_id, _cosine(query_vector, vector))
            for section_id, vector in self._section_vectors.items()
        ]
        return [section_id for section_id, _ in sorted(scored, key=lambda item: -item[1])]

    # -- search --------------------------------------------------------------------------------

    def _hits(self, scored: list[tuple[str, float]], limit: int) -> list[SearchHit]:
        return [
            SearchHit(i, self._by_id[i].title, self._by_id[i].text, round(score, 4))
            for i, score in scored[:limit]
        ]

    def ranked_ids(self, query: str, limit: int = MAX_LIMIT, *, method: str = "auto") -> list[str]:
        return [hit.id for hit in self.search(query, limit, method=method).hits]

    def search(
        self, query: str, limit: int = DEFAULT_LIMIT, *, method: str = "auto"
    ) -> SearchResult:
        """`method`: "auto" (hybrid when embeddings work), "bm25" or "embeddings"."""
        bm25 = self._bm25.rank(query)
        if method == "bm25":
            return SearchResult("bm25", self._hits(bm25, limit))
        try:
            by_meaning = self._embedding_ranking(query)
        except RuntimeError:
            if method == "embeddings":
                raise
            return SearchResult("bm25", self._hits(bm25, limit))
        if method == "embeddings":
            return SearchResult("embeddings", self._hits([(i, 0.0) for i in by_meaning], limit))
        fused: Counter[str] = Counter()
        for ranking in ([i for i, _ in bm25], by_meaning):
            for position, section_id in enumerate(ranking, start=1):
                fused[section_id] += 1 / (RRF_K + position)
        ordered = sorted(fused.items(), key=lambda item: -item[1])
        return SearchResult("hybrid", self._hits(ordered, limit))


def search_policies(
    retriever: PolicyRetriever, query: str, limit: int = DEFAULT_LIMIT
) -> dict[str, Any]:
    if not query.strip():
        return error("invalid_argument", "Give a non-empty query.")
    if not 1 <= limit <= MAX_LIMIT:
        return error("invalid_argument", f"limit must be between 1 and {MAX_LIMIT}.")
    result = retriever.search(query, limit)
    return {
        "method": result.method,
        "sections": [
            {"id": h.id, "title": h.title, "text": h.text, "score": h.score} for h in result.hits
        ],
    }


def build_retriever(settings: Settings, sections: Sequence[PolicySection]) -> PolicyRetriever:
    embedder = OpenAIEmbedder(settings) if settings.use_embeddings else None
    cache = settings.db_path.parent / "embeddings-cache.json"
    return PolicyRetriever(sections, embedder, cache_path=cache)
