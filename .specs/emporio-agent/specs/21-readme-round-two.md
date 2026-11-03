# Spec 21: README for the second round

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-11-02
**Scope:** bring the README, the architecture diagram, the screenshots and the project map in line with specs 13 to 20
**Depends on:** 13 to 20
**Delivery:** autonomous (after its dependencies)

---

## Summary

Specs 13 to 20 added a ranked policy search with its evaluation, per-turn metrics, a chat-first web
page with a developer mode, adversarial evaluation cases, an MCP server, continuous integration, a
context budget and a Docker image. The README is the first thing an evaluator reads, so it has to say
what exists now, with the numbers that the reports contain, and it has to keep stating the limits.

## Context

The README structure is fixed by the challenge and by the tests of spec 11: the required sections
stay in order and the honest remarks about the evaluation stay. This spec changes the content, adds a
Mermaid diagram that GitHub renders, three screenshots and the new commands and settings. A new test
compares the numbers in the README with the JSON reports, so they cannot drift apart.

---

## Allowed files

**Docs:** README.md, PROJECT_MAP.md, .specs/emporio-agent/progress.md

**Tests:** tests/test_readme_extension.py (new)

**Do not touch:** the source code and the reports in evals/results.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| ✅ RF-01 | The README documents the new commands (stats, mcp, the retrieval evaluation, docker run) and settings (embeddings and prices) | Must | Test of the needles |
| ✅ RF-02 | The counts are current: nine tools, about 460 tests, 33 evaluation cases, 20 specs; no stale count remains | Must | Test of stale and current counts |
| ✅ RF-03 | The retrieval numbers (recall at 1, recall at 3, MRR for BM25, embeddings and hybrid) in the README equal those of evals/results/retrieval.json | Must | Consistency test |
| ✅ RF-04 | The result of the full evaluation in the README equals the report evals/results/claude-haiku-5.5-33-cases.json | Must | Consistency test |
| ✅ RF-05 | The README has a Mermaid architecture diagram and the three screenshots (customer light, customer dark, developer mode) | Must | Test of the diagram and the files |
| ✅ RF-06 | The limits section states what the new parts do not do: the model never called the policy search in the evaluation, BM25 alone misses word variants, the Docker image was only built in CI, the MCP server was only checked with one client, the drawer on a phone was not seen on a real phone | Must | Test of the key words |
| ✅ RF-07 | The earlier honest remarks stay: the tuned evaluation, the first run of 18 out of 21, the held-out caveat | Must | Existing README tests |

## Non-functional requirements

- Plain statements, no claim that a part was verified when it was not.
- The skills and tools used to organise the work are not named (only that Claude was used).

## Out of scope

- A new evaluation run: the numbers are the ones already recorded.

## Test checklist

- [x] ✅ New commands and settings, counts, diagram and screenshots
- [x] ✅ README numbers equal the JSON reports
- [x] ✅ The earlier README tests still pass
