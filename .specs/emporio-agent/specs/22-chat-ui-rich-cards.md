# Spec 22: chat window with rich cards

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-11-03
**Scope:** make the customer view look like the support chats of large stores: a branded header, a welcome screen, answer cards built from the tool results, follow-up buttons, and a store page with the chat as a widget
**Depends on:** 15 (chat-first page), 14 (turn metrics)
**Delivery:** autonomous

---

## Summary

The page already behaves like a chat, but every answer is plain text in a bubble. A customer who asks for a
guitar wants to see the price, the installments and the stock at a glance, and a customer who asks about an
order wants to see where it is. The tool results already hold these facts, so the page can draw them as cards
without asking the model for anything new and without any new number being computed in the browser.

## Context

The four suggestion buttons stay exactly as they are (same labels, same texts). The developer mode stays as it
is. The card logic is a pure file, `cards.js`, that turns the trace of one answer into card models; it has no
access to the page, so a Node script can test it. The drawing code in `app.js` only places those models in the
page, with text always inserted as text.

---

## Allowed files

**Source:** src/emporio/web/app.py (CSP and the `/loja` route only), src/emporio/web/static/index.html,
app.css, app.js, cards.js (new), loja.html (new), loja.css (new), loja.js (new)

**Tests:** tests/test_web.py, tests/test_cards.py (new), tests/js/cards.test.js (new)

**Docs:** .specs/emporio-agent/progress.md

**Do not touch:** the agent, the tools, the prompts, the evaluations

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| ✅ RF-01 | `cards.js` exposes `cardsFromTrace(trace)`: one card per useful tool result, in the order of the calls. `get_product` gives a product card, `search_products` a list card (at most 4 items), `get_order_status` an order card, `open_handoff` a ticket card, and the policy tools one sources card with the section ids and titles | Must | Node test with one trace per tool |
| ✅ RF-02 | A failed call, a truncated result, an empty list and an unknown tool give no card | Must | Node test |
| ✅ RF-03 | The product card shows the list price struck through only when there is a promotion, the price, the discount percent, the best installment as "até Nx de R$ X sem juros", the PIX line and the stock; the numbers are the ones in the result | Must | Node test compares the text with the result |
| ✅ RF-04 | The order card has the steps Confirmado, Enviado, Entregue with the done and current ones marked from the status; a cancelled order shows one "Cancelado" step; the tracking code and the estimate are shown, and an estimate already passed is marked | Must | Node test for each status |
| ✅ RF-05 | The ticket card shows the protocol, the category label, the deadline and "Aberto"; a duplicate says it already existed | Must | Node test |
| ✅ RF-06 | `followUps(cards)` returns at most 3 short questions chosen from the kinds of the cards (a product leads to payment options, an order to a return, a ticket to nothing) | Should | Node test |
| ✅ RF-07 | The empty conversation shows a welcome screen: the brand, the greeting, the four suggestion buttons unchanged, and a row of four shortcuts that send a message | Must | Static structure test |
| ✅ RF-08 | The header is a branded band with the name, an "IA" badge and the store status; the composer carries the note that the assistant is an AI and can be wrong | Must | Static structure test |
| ✅ RF-09 | Under each answer there is a copy button (clipboard with a fallback) and the cards of RF-01; the card for the order copies the tracking code | Must | Static structure test |
| ✅ RF-10 | The page has a dark theme and a phone layout with the same tokens; the developer mode is unchanged | Must | Existing tests of spec 15 stay green |
| ✅ RF-11 | `/loja` serves a store page with the chat as a widget (launcher button, panel with the chat in a frame of the same origin); the chat page can be framed only by the same origin | Must | Route test, header test |
| ✅ RF-12 | The static files keep the rules of spec 11: no external request, no `innerHTML` | Must | Existing test |

## Non-functional requirements

- The browser never computes a price, a discount or a date: it formats numbers the tools returned.
- Every card has a text alternative (headings and labels, no information only in color).
- The suggestions keep their order and text: "Violões até R$ 1.000", "Ohana CK-20 em 10x", "Troca por defeito", "Quero devolver um produto".

## Out of scope

- Product photos (the data has none; an inline instrument icon is used).
- Feedback buttons (spec 23).

## Test checklist

- [x] RF-01 to RF-06 Node tests, run from pytest (skipped when Node is not installed)
- [x] RF-07 to RF-09 and RF-12 static structure tests
- [x] RF-11 route and header tests
- [x] Screenshots of the three views are retaken after the work
