# Spec 15: Chat-first interface with a developer mode

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-11-02
**Scope:** the static page of the web interface (HTML, CSS, JavaScript) and its tests
**Depends on:** 12, 13, 14
**Delivery:** autonomous (after its dependencies)

---

## Summary

The first web interface put a "how the assistant decided" panel next to the chat. It is useful for
whoever evaluates the project, but a customer would never see it, and it made the page look like a
tool and not like a conversation. This spec makes the default view a real messaging chat and moves
everything about the agent's reasoning into a **developer mode**, off by default, opened with a
button in the header.

## Context

No server change is needed: the page already receives the trace (spec 12) and the metrics
(spec 14). The page stays plain HTML, CSS and JavaScript, with no external request and no
innerHTML, so the checks of spec 12 still apply.

---

## Allowed files

**Production:** src/emporio/web/static/index.html, app.css, app.js (rewritten); theme.js and favicon.svg unchanged

**Tests:** tests/test_web.py (the two panel tests are replaced by tests for this spec)

**Docs:** README.md, PROJECT_MAP.md, docs/*.jpg (new screenshots)

**Do not touch:** the Python server code and the agent.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| ✅ RF-01 | The default view is a chat: a header with the assistant avatar, name and the store status, a conversation made of bubbles (customer on the right, Melô on the left), the time of each message sent in this visit, a typing indicator while the answer is pending and a rounded composer with an icon send button | Must | Static checks plus a manual pass in a browser |
| ✅ RF-02 | The first message of the conversation is the greeting of Melô, followed by quick-reply buttons (the suggestions of the state) that disappear after the first customer message | Must | Static check and manual pass |
| ✅ RF-03 | Nothing about the agent's reasoning is visible in the default view: no trace, no source tags, no metrics, no test data, no panel | Must | The dev-only elements are hidden unless the body is in developer mode |
| ✅ RF-04 | A header button, Modo dev, with aria-pressed and a code icon, turns the developer mode on and off; the choice is remembered on wide screens | Must | Static check of the control and of the storage key |
| ✅ RF-05 | In developer mode a side panel has four tabs: Decisões (the trace and the legend), Métricas (summary and one line per turn), Chamados (open handoff tickets) and Dados de teste (the fictional customers, with a button that fills the composer); each answer also shows its source tags and a line with time, tool calls, tokens and cost when known | Must | Static check and manual pass |
| ✅ RF-06 | The store hours, address and contacts stay available to every customer through an information button in the header | Must | Static check of the dialog |
| ✅ RF-07 | On narrow screens the panel is a drawer, closed by default, closed by the backdrop and by Escape; the header shows icons only | Must | CSS check and manual pass at 390 px |
| ✅ RF-08 | The theme is one header button that cycles system, light and dark and says which one is active | Should | Static check |
| ✅ RF-09 | A reload restores the transcript, the verification badge and the developer-mode choice | Must | Existing state tests plus manual pass |

## Non-functional requirements

- No external request, no innerHTML, no inline script or style (Content-Security-Policy).
- Both themes with their own palette; contrast and focus rings kept; prefers-reduced-motion respected.
- All the controls have an accessible name.

## Out of scope

- Message timestamps stored on the server (restored messages show no time).
- Streaming of the answer text.

## Test checklist

- [x] ✅ The page has the chat parts and the developer-mode control
- [x] ✅ Dev-only parts are hidden by default in the CSS
- [x] ✅ No external request and no innerHTML
- [x] ✅ Manual pass in a browser: customer view, developer mode, both themes, 390 px
