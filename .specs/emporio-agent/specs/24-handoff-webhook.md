# Spec 24: webhook when a handoff ticket is opened

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-11-03
**Scope:** tell the store team's own tool (n8n, Slack, any HTTP endpoint) when Melô opens a new ticket
**Depends on:** 8 (handoff tool)
**Delivery:** autonomous

---

## Summary

Today a ticket only exists in the database; somebody has to run `emporio handoffs` to see it. A real store
would want the team to be told. One optional setting, `HANDOFF_WEBHOOK_URL`, makes the agent send a small JSON
message to that address each time a new ticket is created.

## Context

The call happens inside the `open_handoff` tool after the ticket is stored, so a failure of the webhook can
never undo the ticket or break the answer. A duplicate (the ticket already existed) sends nothing. The message
has a `text` field so a Slack incoming webhook accepts it as it is, and the structured fields for n8n or any
other receiver.

---

## Allowed files

**Source:** src/emporio/webhook.py (new), src/emporio/handoff.py, src/emporio/tools.py,
src/emporio/conversation.py, src/emporio/cli.py (the MCP context only), src/emporio/config.py

**Tests:** tests/test_webhook.py (new)

**Config and docs:** .env.example, .specs/emporio-agent/progress.md, README.md (in the README spec)

**Do not touch:** the prompts, the evaluation runner (it never sends a webhook)

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| RF-01 | `HANDOFF_WEBHOOK_URL` is optional; blank means off; only `http` and `https` addresses are accepted, anything else is a configuration error | Must | Settings test |
| RF-02 | When a new ticket is created the notifier POSTs JSON with `event`, `text`, `protocol`, `category`, `summary`, `order_id`, `session_id`, `created_at` and `due_at` | Must | Local HTTP server test |
| RF-03 | The message never carries the customer's name, e-mail, phone or id; the contact the customer typed is not part of the ticket | Must | Body test on the keys |
| RF-04 | A duplicate ticket sends nothing | Must | Tool test |
| RF-05 | A timeout (3 seconds), a refused connection, an HTTP error or a bad address is logged and ignored: the tool still returns the protocol | Must | Failure tests |
| RF-06 | With no address configured nothing is sent and nothing changes | Must | Existing tests stay green |
| RF-07 | The evaluation runner never sends a webhook | Must | Runner context test |

## Non-functional requirements

- The call is synchronous with a short timeout, so a new ticket can add up to 3 seconds to that one answer.
- The `summary` is written by the model from what the customer said; the spec does not promise it holds no
  personal text, only that the structured contact data is never added.

## Out of scope

- Retries and a queue (a failed message is lost, and the ticket stays in the database).
- Signing the message (the receiver should be reached over a private address or a secret path).

## Test checklist

- [ ] RF-01 settings tests
- [ ] RF-02, RF-03 local server test and key test
- [ ] RF-04, RF-05 tool and failure tests
- [ ] RF-07 runner context
