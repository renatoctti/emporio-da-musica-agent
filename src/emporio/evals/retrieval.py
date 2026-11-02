"""Offline evaluation of the policy search: recall@1, recall@3 and mean reciprocal rank.

`python -m emporio.evals.retrieval` compares BM25 with embeddings and the hybrid. The BM25 part
needs no key. The questions are written from the manual, in the words a customer would use, and
are not tuned to the ranker; several are deliberately vague, which is where lexical search is weak.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from emporio.config import ROOT, Settings, load_settings
from emporio.policies import load_policy_sections
from emporio.retrieval import Embedder, OpenAIEmbedder, PolicyRetriever

POLICY_FILE = "políticas_da_loja.pdf"
RANK_DEPTH = 5


@dataclass(frozen=True)
class GoldQuestion:
    question: str
    expected: tuple[str, ...]  # any of these sections is a correct answer


GOLD: tuple[GoldQuestion, ...] = (
    GoldQuestion("Quanto tempo tenho para devolver depois que recebi o produto?", ("4.1",)),
    GoldQuestion("Comprei online e me arrependi, o que eu faço?", ("4.1",)),
    GoldQuestion("Posso devolver sem ter usado e receber o dinheiro de volta?", ("4.1",)),
    GoldQuestion("O violão chegou com defeito, posso trocar?", ("4.2",)),
    GoldQuestion("Meu instrumento deu problema depois de 40 dias, e agora?", ("4.2", "8.2")),
    GoldQuestion("Quero trocar por outra cor do mesmo modelo", ("4.3",)),
    GoldQuestion("Dá para devolver a boquilha do saxofone?", ("4.4",)),
    GoldQuestion("Instrumento personalizado sob encomenda tem troca?", ("4.4",)),
    GoldQuestion("O frete é grátis aqui em Campo Grande?", ("5.1",)),
    GoldQuestion("Quanto tempo demora a entrega para outra cidade?", ("5.2",)),
    GoldQuestion("Vocês enviam por Sedex ou PAC?", ("5.2",)),
    GoldQuestion("O que eu faço se a mercadoria chegar danificada?", ("5.2",)),
    GoldQuestion("Como acompanho a minha encomenda?", ("5.3",)),
    GoldQuestion("Qual o formato do código de rastreio?", ("5.3",)),
    GoldQuestion("Dá para parcelar em 12 vezes sem juros?", ("3", "3.1")),
    GoldQuestion("Qual é a parcela mínima no cartão de crédito?", ("3", "3.1")),
    GoldQuestion("Posso pagar uma parte no Pix e outra no cartão?", ("3.1",)),
    GoldQuestion("Tem desconto para pagamento no Pix?", ("3", "6.2")),
    GoldQuestion("O boleto demora para compensar?", ("3",)),
    GoldQuestion("A que horas a loja fecha no sábado?", ("2",)),
    GoldQuestion("Vocês abrem no feriado?", ("2",)),
    GoldQuestion("Vai ter promoção na Black Friday?", ("6.1",)),
    GoldQuestion("O desconto do Pix vale em produto que já está em promoção?", ("6.2",)),
    GoldQuestion("Se o produto acabar durante a promoção, vocês seguram o preço?", ("6.2",)),
    GoldQuestion("Qual é o prazo da garantia legal?", ("8.1",)),
    GoldQuestion("Quantos meses de garantia o fabricante dá?", ("8.2",)),
    GoldQuestion("As cordas gastas são cobertas pela garantia?", ("8.3",)),
    GoldQuestion("Vocês vendem cordas e palhetas?", ("1", "7.1")),
    GoldQuestion("Como vocês tratam os meus dados pessoais?", ("9",)),
    GoldQuestion("Quero que apaguem meus dados", ("9",)),
    GoldQuestion("Quando a loja foi fundada?", ("1", "1.2")),
    GoldQuestion("Qual é o CNPJ da empresa?", ("1.2",)),
    GoldQuestion("Em quanto tempo respondem a uma reclamação?", ("7.3",)),
    GoldQuestion("O que acontece com um produto que saiu de linha?", ("7.3",)),
)


@dataclass(frozen=True)
class Metrics:
    n: int
    recall_at_1: float
    recall_at_3: float
    mrr: float


def evaluate_retrieval(
    search: Callable[[str, int], list[str]], gold: Sequence[GoldQuestion] = GOLD
) -> Metrics:
    """`search(question, limit)` returns section ids, best first."""
    first = third = 0
    reciprocal = 0.0
    for item in gold:
        ids = search(item.question, RANK_DEPTH)
        rank = next(
            (i for i, section_id in enumerate(ids, start=1) if section_id in item.expected), None
        )
        first += rank == 1
        third += rank is not None and rank <= 3
        reciprocal += 1 / rank if rank else 0.0
    n = len(gold)
    return Metrics(n, first / n, third / n, reciprocal / n)


def _default_embedder(settings: Settings) -> Embedder | None:
    return OpenAIEmbedder(settings) if settings.use_embeddings else None


def main(
    argv: Sequence[str] | None = None,
    *,
    embedder_factory: Callable[[], Embedder | None] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m emporio.evals.retrieval", description=__doc__)
    parser.add_argument("--report", metavar="FILE", help="write the metrics as JSON here")
    parser.add_argument("--no-cache", action="store_true", help="do not keep vectors on disk")
    args = parser.parse_args(argv)

    load_dotenv()
    settings = load_settings()
    sections = load_policy_sections(settings.data_dir / POLICY_FILE)
    embedder = embedder_factory() if embedder_factory else _default_embedder(settings)
    cache = None if args.no_cache else ROOT / "var" / "embeddings-cache.json"
    retriever = PolicyRetriever(sections, embedder, cache_path=cache)

    methods = ["bm25"] + (["embeddings", "hybrid"] if embedder else [])
    results: dict[str, Metrics] = {}
    for method in methods:
        mode = "auto" if method == "hybrid" else method
        try:
            results[method] = evaluate_retrieval(
                lambda q, k, mode=mode: retriever.ranked_ids(q, k, method=mode)
            )
        except RuntimeError as exc:
            print(f"{method}: skipped ({exc})")

    print(f"{'method':<12}{'n':>4}{'recall@1':>10}{'recall@3':>10}{'mrr':>8}")
    for name, m in results.items():
        print(f"{name:<12}{m.n:>4}{m.recall_at_1:>10.2f}{m.recall_at_3:>10.2f}{m.mrr:>8.2f}")

    if args.report:
        report = {
            "date": date.today().isoformat(),
            "embedding_model": getattr(embedder, "model", None),
            "methods": {
                name: {
                    "n": m.n,
                    "recall_at_1": round(m.recall_at_1, 4),
                    "recall_at_3": round(m.recall_at_3, 4),
                    "mrr": round(m.mrr, 4),
                }
                for name, m in results.items()
            },
        }
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"report written to {args.report}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
