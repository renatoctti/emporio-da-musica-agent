"""Spec 13: ranked policy search (BM25, optional embeddings) and its evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from emporio.evals.retrieval import GOLD, Metrics, evaluate_retrieval, main
from emporio.policies import PolicySection, load_policy_sections
from emporio.retrieval import Bm25Index, PolicyRetriever, tokenize

MANUAL = Path(__file__).resolve().parents[1] / "data" / "políticas_da_loja.pdf"


@pytest.fixture(scope="module")
def sections() -> tuple[PolicySection, ...]:
    return load_policy_sections(MANUAL)


class FakeEmbedder:
    """Maps a text to a vector chosen by the test; counts the calls."""

    model = "fake-embedding"

    def __init__(self, vectors: dict[str, list[float]] | None = None, *, fail: bool = False):
        self.vectors = vectors or {}
        self.fail = fail
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail:
            raise RuntimeError("embeddings are down")
        return [self.vectors.get(text, [0.0, 0.0, 1.0]) for text in texts]


def _tiny() -> tuple[PolicySection, ...]:
    return (
        PolicySection("1", "Frete", "O frete é grátis acima de R$ 500.", None),
        PolicySection("2", "Garantia", "A garantia legal cobre defeitos de fabricação.", None),
        PolicySection("3", "Horário", "A loja abre às nove horas.", None),
    )


# --- RF-01 tokenizer ---------------------------------------------------------------------------


def test_tokenize_removes_accents_stop_words_and_reduces_plurals():
    assert tokenize("As Devoluções de produtos") == tokenize("devolução produto")
    assert "de" not in tokenize("prazo de entrega")
    assert tokenize("Empório") == ["emporio"]


# --- RF-02 BM25 --------------------------------------------------------------------------------


def test_bm25_ranks_the_matching_section_first_and_only_positive_scores():
    ranking = Bm25Index(_tiny()).rank("qual a garantia contra defeitos")
    assert ranking[0][0] == "2"
    assert all(score > 0 for _, score in ranking)


def test_bm25_title_words_weigh_more_than_body_words():
    docs = (
        PolicySection("1", "Outro assunto", "frete frete frete", None),
        PolicySection("2", "Frete", "texto qualquer", None),
    )
    assert Bm25Index(docs).rank("frete")[0][0] == "2"


def test_bm25_on_the_real_manual(sections):
    ranking = Bm25Index(sections).rank("prazo de entrega para outra cidade")
    assert ranking[0][0] == "5.2"


# --- RF-03 / RF-04 / RF-05 retriever -----------------------------------------------------------


def test_retriever_without_embedder_is_bm25(tmp_path):
    result = PolicyRetriever(_tiny()).search("quando abre a loja", limit=2)
    assert result.method == "bm25"
    assert (
        result.hits[0].id == "3" and 1 <= len(result.hits) <= 2
    )  # only positive scores are returned
    assert result.hits[0].text and result.hits[0].title == "Horário"


def test_hybrid_fuses_both_rankings(tmp_path):
    sections = _tiny()
    # BM25 prefers section 1 ("frete"); the embedder prefers section 3 for this query.
    vectors = {
        "frete grátis": [1.0, 0.0, 0.0],
        "Frete\nO frete é grátis acima de R$ 500.": [0.0, 1.0, 0.0],
        "Garantia\nA garantia legal cobre defeitos de fabricação.": [0.0, 0.0, 1.0],
        "Horário\nA loja abre às nove horas.": [1.0, 0.0, 0.0],
    }
    retriever = PolicyRetriever(sections, FakeEmbedder(vectors), cache_path=tmp_path / "c.json")
    result = retriever.search("frete grátis", limit=2)
    assert result.method == "hybrid"
    assert {hit.id for hit in result.hits} == {"1", "3"}


def test_embedder_failure_falls_back_to_bm25_and_is_not_retried():
    embedder = FakeEmbedder(fail=True)
    retriever = PolicyRetriever(_tiny(), embedder)
    first = retriever.search("garantia", limit=1)
    second = retriever.search("horário", limit=1)
    assert first.method == second.method == "bm25"
    assert first.hits[0].id == "2" and second.hits[0].id == "3"
    assert len(embedder.calls) == 1


def test_vectors_are_cached_on_disk(tmp_path):
    cache = tmp_path / "vectors.json"
    first = FakeEmbedder()
    PolicyRetriever(_tiny(), first, cache_path=cache).search("garantia", limit=1)
    assert len(first.calls) == 2  # the sections once, the query once
    second = FakeEmbedder()
    PolicyRetriever(_tiny(), second, cache_path=cache).search("garantia", limit=1)
    assert second.calls == []
    assert json.loads(cache.read_text(encoding="utf-8"))  # something was saved


# --- RF-08 / RF-09 / RF-10 evaluation ----------------------------------------------------------


def test_gold_set_is_large_and_points_at_real_sections(sections):
    ids = {s.id for s in sections}
    assert len(GOLD) >= 30
    for item in GOLD:
        assert item.question.strip() and item.expected
        assert set(item.expected) <= ids, item


def test_metrics_with_a_stub_search():
    gold = GOLD[:3]

    def search(question: str, limit: int) -> list[str]:
        position = [g.question for g in gold].index(question)
        wrong = ["x1", "x2"]
        first = gold[position].expected[0]
        return [first, *wrong][:limit] if position == 0 else [*wrong, first][:limit]

    metrics = evaluate_retrieval(search, gold)
    assert metrics == Metrics(
        n=3,
        recall_at_1=pytest.approx(1 / 3),
        recall_at_3=pytest.approx(1.0),
        mrr=pytest.approx((1 + 1 / 3 + 1 / 3) / 3),
    )


def test_bm25_reaches_the_recall_threshold_on_the_gold_set(sections):
    retriever = PolicyRetriever(sections)

    def search(question: str, limit: int) -> list[str]:
        return [hit.id for hit in retriever.search(question, limit).hits]

    assert evaluate_retrieval(search, GOLD).recall_at_3 >= 0.8


# --- RF-11 command -----------------------------------------------------------------------------


def test_command_prints_bm25_and_writes_the_report(tmp_path, capsys):
    report = tmp_path / "retrieval.json"
    code = main(["--report", str(report)], embedder_factory=lambda: None)
    out = capsys.readouterr().out
    assert code == 0 and "bm25" in out
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["methods"]["bm25"]["n"] == len(GOLD)
    assert "hybrid" not in data["methods"]


def test_command_adds_embeddings_and_hybrid_when_an_embedder_exists(tmp_path, capsys):
    report = tmp_path / "retrieval.json"
    code = main(["--report", str(report), "--no-cache"], embedder_factory=lambda: FakeEmbedder())
    assert code == 0
    methods = json.loads(report.read_text(encoding="utf-8"))["methods"]
    assert set(methods) == {"bm25", "embeddings", "hybrid"}
