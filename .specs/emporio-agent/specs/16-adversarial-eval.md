# Spec 16: Adversarial evaluation cases

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-11-02
**Scope:** new evaluation cases that attack the agent, plus tests that check the checks
**Depends on:** 10, 13
**Delivery:** autonomous (after its dependencies)

---

## Summary

The first 21 evaluation cases check that the agent routes questions well. This spec adds a set of
cases that try to make it misbehave: leaking its instructions, accepting a new persona, skipping the
identity check, reading the order of another customer, obeying an instruction hidden in a pasted
message, confirming a price someone else promised, and being asked something unrelated or harmful.
Each case has a deterministic check, so the evaluation stays free of a second model acting as judge.

## Context

The rules that protect the data already live in code (the verification state and the ownership
check), so the real defence is tested at the tool level. These cases test the layer above it: what
the model says when pushed. The checks are patterns and tool constraints, the same as the other
cases, and a failure is read by a person.

---

## Allowed files

**Production:** src/emporio/evals/cases.py (new cases, tag adversarial)

**Tests:** tests/test_adversarial.py (new)

**Docs:** README.md, PROJECT_MAP.md

**Do not touch:** the agent, the tools and the prompt (a failing case is a finding, reported as such).

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| ✅ RF-01 | At least 12 new cases with the tag adversarial and ids that continue the existing ones | Must | Count and unique ids |
| ✅ RF-02 | The set covers: instruction leak in Portuguese, English and Spanish; persona override; an identity bypass by claimed authority; repeated wrong verifications; the order of another customer; an instruction pasted inside the message; a request for the e-mails of other customers; a harmful off-topic request; a price promised by someone else; an injection-looking order number | Must | Each topic has a case |
| ✅ RF-03 | Every case has at least one deterministic check (a forbidden or expected tool, or a reply pattern) | Must | Structural test |
| ✅ RF-04 | For every adversarial case a safe reply passes and an unsafe reply fails, so no check is vacuous | Must | One good and one bad scripted turn per case |
| ✅ RF-05 | python -m emporio.evals --tag adversarial runs only these cases | Should | Existing tag filter |

## Non-functional requirements

- No new dependency and no second model as a judge.
- Patterns match what a real leak or a real obedience would contain, not the wording of a refusal.

## Out of scope

- Fixing the agent when a case fails: a failure is reported, and the fix is a separate change.
- Multi-turn social engineering beyond the repeated verification.

## Test checklist

- [x] ✅ Count, ids, tags and structure
- [x] ✅ A good and a bad scripted reply for every case
