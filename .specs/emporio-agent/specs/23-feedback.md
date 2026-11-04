# Spec 23: customer feedback on the answers

**Status:** ✅ In progress
**Author:** renatoctti
**Date:** 2026-11-03
**Scope:** let the customer rate each answer with thumbs up or down, store it, and turn the bad ones into candidates for the evaluation
**Depends on:** 22 (answer actions), 14 (turn storage)
**Delivery:** autonomous

---

## Summary

Large support chats ask for a thumbs up or down under each answer. The ratings are the cheapest signal of
where the agent fails. This spec stores them next to the conversation and gives the developer a command that
lists the bad ones and exports them as candidate evaluation cases.

## Context

A rating belongs to one turn of one session (the same turn index as the metrics). A second click on the same
button removes the rating. The export does not invent checks: each candidate carries the question, the reply
and the comment, and a person writes the check before it joins the evaluation.

---

## Allowed files

**Source:** src/emporio/db.py, src/emporio/web/app.py, src/emporio/cli.py, src/emporio/web/static/app.js,
app.css, index.html

**Tests:** tests/test_feedback.py (new), tests/test_web.py

**Docs:** .specs/emporio-agent/progress.md, README.md (in the README spec)

**Do not touch:** the agent, the tools, the prompts

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| RF-01 | A `feedback` table keeps one rating (`up` or `down`) and an optional comment per session and turn; saving again replaces it, saving `None` removes it | Must | Store test |
| RF-02 | `POST /api/feedback` takes `turn_index`, `rating` (`up`, `down` or null) and an optional `comment` of at most 500 characters; anything else is a 400, a turn that does not exist is a 400, GET is a 405 | Must | Route tests |
| RF-03 | `/api/state` returns the stored rating of each turn (`feedback`: `up`, `down` or null) so a reload keeps the buttons | Must | State test |
| RF-04 | Under each answer there are two buttons (thumbs up and down, with `aria-pressed`); clicking sends the rating, clicking the pressed one removes it | Must | Static structure test |
| RF-05 | `emporio feedback` lists the answers rated down (session, turn, question, comment); with `-o FILE` it writes them as JSON candidates (`session_id`, `turn_index`, `question`, `reply`, `comment`) | Should | CLI test |
| RF-06 | A new conversation (reset) starts without ratings; the ratings of old sessions stay stored | Must | Route test |

## Non-functional requirements

- The comment is stored as text and shown only to the developer; nothing is sent anywhere.
- The static files keep the rules of spec 11: no `innerHTML`, no external request.

## Out of scope

- Turning the candidates into evaluation cases automatically (a person writes the checks).

## Test checklist

- [ ] RF-01 store tests
- [ ] RF-02, RF-03, RF-06 route tests
- [ ] RF-04 static structure test
- [ ] RF-05 CLI test
