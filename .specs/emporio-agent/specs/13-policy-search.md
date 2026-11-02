# Spec 13: Policy search and retrieval evaluation

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-11-02
**Scope:** a ranked search over the manual sections, an optional embeddings step, an offline retrieval evaluation
**Depends on:** 04, 08, 10
**Delivery:** autonomous (after its dependencies)

---

## Summary

Until now the agent picked manual sections by id from an index in the prompt. That works when the
question names the topic, and fails when it is vague ("posso devolver sem ter usado?"). This spec
adds `search_policies(query)`: it ranks the 28 sections with BM25 and, when an embeddings model is
reachable, fuses that ranking with cosine similarity over embeddings (reciprocal rank fusion).
A gold set of questions with the expected section measures the quality of each method, with no
model call for the lexical part.

## Context

`get_policy_sections` stays for the exact lookup by id. The search returns the text of the top
sections so the agent does not need a second call. Embeddings are optional and lazy: they are
requested on the first search, cached on disk by text hash, and any failure falls back to BM25, so
the project still runs offline and without a key.

---

## Allowed files

**Production**

- `src/emporio/retrieval.py` (new): tokenizer, `Bm25Index`, `Embedder`, `OpenAIEmbedder`, `PolicyRetriever`
- `src/emporio/tools.py`: tool `search_policies`; `ToolContext.retriever`
- `src/emporio/config.py`: `embedding_model`, `use_embeddings`
- `src/emporio/conversation.py`, `src/emporio/evals/runner.py`: build the retriever
- `src/emporio/prompt.py`: rule 3 mentions the search
- `src/emporio/evals/retrieval.py` (new): gold set, metrics, `python -m emporio.evals.retrieval`

**Tests**

- `tests/test_retrieval.py` (new), `tests/test_tools.py`, `tests/test_config.py`, `tests/test_prompt.py`

**Docs:** `README.md`, `PROJECT_MAP.md`, `.env.example`

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| ✅ RF-01 | `tokenize(text)` lowercases, removes accents, splits on non-alphanumerics, drops Portuguese stop words and reduces plurals ("devoluções" and "devolução" match) | Must | Unit tests |
| ✅ RF-02 | `Bm25Index(sections).rank(query)` returns every section with a positive score, best first; title words weigh more than body words | Must | "prazo de entrega para outra cidade" ranks 5.2 first |
| ✅ RF-03 | `PolicyRetriever.search(query, limit)` uses BM25 alone without an embedder and reciprocal rank fusion with one; the result says which method ran | Must | Both paths tested with a fake embedder |
| ✅ RF-04 | An embedder failure (exception) on the first search falls back to BM25 and is not retried within the same retriever | Must | Fake embedder that raises |
| ✅ RF-05 | Section and query vectors are cached on disk by model and text hash; a second retriever with the same cache makes no section embedding call | Should | Fake embedder call counter |
| ✅ RF-06 | Tool `search_policies(query, limit)` validates the arguments and returns `{"method", "sections": [{id, title, text, score}]}` with 1 to 5 sections; an empty query is an `invalid_argument` error | Must | Tool tests |
| ✅ RF-07 | `Settings.use_embeddings` is true when `EMPORIO_EMBEDDINGS` is not `off` and an API key exists; `embedding_model` defaults to `openai/text-embedding-3-small` | Must | Config tests |
| ✅ RF-08 | The gold set has at least 30 questions, written from the manual and not tuned to the ranker, each with the accepted section ids | Must | Count and ids exist |
| ✅ RF-09 | `evaluate_retrieval(search, gold)` returns recall@1, recall@3 and mean reciprocal rank | Must | Metric unit test with a stub search |
| ✅ RF-10 | BM25 reaches recall@3 of at least 0.8 on the gold set | Must | Threshold test on the real manual |
| ✅ RF-11 | `python -m emporio.evals.retrieval` prints the metrics for BM25 and, with a key, for embeddings and hybrid; `--report FILE` writes JSON | Should | Command test with a fake embedder |

## Non-functional requirements

- The offline path adds no dependency and makes no network call.
- No API key or vector is written to the repository; the vector cache lives under `var/`.

## Out of scope

- An external vector database (it would need an account and break the offline run); the
  `Embedder` protocol and the retriever are the seam where one would plug in.
- Re-chunking the manual: sections are already short (about 350 characters on average).

## Test checklist

- [x] ✅ Tokenizer, BM25 order, fusion, fallback, cache
- [x] ✅ Tool arguments and result shape
- [x] ✅ Settings
- [x] ✅ Gold set size and metrics, BM25 threshold on the real manual
