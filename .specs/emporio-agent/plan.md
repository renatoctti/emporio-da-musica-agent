# Empório da Música agent: implementation order

**Status:** Draft
**Date:** 2026-10-31

---

## Implementation order

Implement in the sequence below. Do not start a spec before the tests of its dependencies pass.
Each spec ends with one commit that includes its code, its tests and the update of `progress.md`.

| # | Spec | File | Depends on | Advance criterion |
|---|---|---|---|---|
| 01 | Foundation: settings and data | `specs/01-foundation-data.md` | none | Spec 01 tests pass |
| 02 | Price quote | `specs/02-pricing.md` | none | Spec 02 tests pass |
| 03 | Catalog search and product detail | `specs/03-catalog.md` | 01, 02 | Spec 03 tests pass |
| 04 | Policy retrieval | `specs/04-policy-retrieval.md` | none | Spec 04 tests pass |
| 05 | Persistence | `specs/05-persistence.md` | none | Spec 05 tests pass |
| 06 | Customer verification and orders | `specs/06-customer-orders.md` | 01 | Spec 06 tests pass |
| 07 | Business hours, returns, handoff | `specs/07-returns-handoff.md` | 01, 05, 06 | Spec 07 tests pass |
| 08 | Agent loop | `specs/08-agent-loop.md` | 02, 03, 04, 05, 06, 07 | Spec 08 tests pass |
| 09 | CLI | `specs/09-cli.md` | 05, 08 | Spec 09 tests pass |
| 10 | Routing eval | `specs/10-routing-eval.md` | 08 | Spec 10 tests pass and one live run is recorded |
| 11 | Samples and README | `specs/11-samples-readme.md` | 09, 10 | Five transcripts and a complete README |
| 12 | Local web interface | `specs/12-web-interface.md` | 05, 08, 09 | Spec 12 tests pass and a manual browser pass |

## Dependency graph

```
01 ──► 03 ──┐
02 ──► 03   │
01 ──► 06 ──┼──► 07 ──► 08 ──► 09 ──► 11
05 ─────────┘     ▲      │
04 ───────────────┘      └──► 10 ──► 11
```

Specs 01, 02, 04 and 05 are independent of each other.

## Feature completion criterion

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m emporio.evals          # live run, needs LLM_API_KEY
```
