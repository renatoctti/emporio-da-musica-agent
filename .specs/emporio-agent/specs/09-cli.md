# Spec 09: Command-line interface

**Status:** 🟡 Draft
**Author:** renatoctti
**Date:** 2026-10-31
**Scope:** CLI commands: chat, resume, sessions, handoffs, export, replay, data report
**Depends on:** 05, 08
**Delivery:** autonomous (after its dependencies)

---

## Summary

The user-facing program. `emporio` opens a chat; `emporio chat --resume ID` continues a stored
conversation; `sessions`, `handoffs`, `export`, `replay` and `data-report` cover history, the store
team's ticket view, transcripts for the README, and the data-quality report.

## Context

The challenge accepts a CLI as interface. `replay` feeds scripted customer messages through the
real agent so the sample conversations in the repository are reproducible, not hand-written.

---

## Allowed files

**Production**

- `src/emporio/cli.py` (new)
- `src/emporio/__main__.py`: delegate to `cli.main`

**Tests**

- `tests/test_cli.py` (new)

**Do not touch:** domain modules and `agent.py`.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| 🟡 RF-01 | `main(argv)` returns an exit code; `emporio` with no subcommand equals `emporio chat` | Must | `main([])` starts a chat (with injected fakes) |
| 🟡 RF-02 | `chat` creates a session (or resumes with `--resume ID`), builds the toolset and agent, prints a greeting from Melô, then loops: read a line, `Agent.reply`, print the reply, persist `new_messages` | Must | Scripted input with one question persists user, assistant and tool messages |
| 🟡 RF-03 | Chat ends on `sair`, `exit`, `quit`, EOF or Ctrl-C, printing the session id and how to resume | Must | Each exit word ends the loop and prints the id |
| 🟡 RF-04 | On resume the verification state starts **empty** and the CLI says so ("para sua segurança, confirme o pedido de novo"); the stored history is loaded as context | Must | Resumed session has `verified_customer_id None` |
| 🟡 RF-05 | `--today YYYY-MM-DD` overrides `EMPORIO_TODAY` for the run; `--verbose` prints each tool call and a truncated result to stderr | Should | Settings in the built context use the flag value |
| 🟡 RF-06 | `sessions` lists stored sessions (id, date, number of messages, first user message truncated to 50 characters); `handoffs` lists open tickets (protocol, category, due date, order, summary truncated to 60) | Must | Output tables contain the seeded rows |
| 🟡 RF-07 | `export SESSION_ID [-o FILE]` renders the conversation as Markdown: header with session id, model and reference date; `**Cliente:**` and `**Melô:**` lines; each tool call as a block quote `> tool: name(args)` followed by `> result: <first 300 characters>` | Must | Export of a seeded session matches the expected Markdown exactly |
| 🟡 RF-08 | `replay SCRIPT [--today D] [-o FILE]` reads a UTF-8 text file (one customer message per line; blank lines and lines starting with `#` ignored), runs them in order through a fresh session and writes the export (RF-07) to `-o` or stdout | Must | A three-line script with a fake client yields three customer blocks |
| 🟡 RF-09 | `data-report` prints each `DataIssue` grouped by kind | Should | Output contains `order_total_mismatch` and "order 3" |
| 🟡 RF-10 | Missing API key prints "Set LLM_API_KEY (see .env.example)" to stderr and returns exit code 1; an unknown session id prints an error and returns 2; other infrastructure errors propagate with their traceback | Must | Both exit codes covered |

---

## Expected behavior

- Prompts use `Você: ` for input and `Melô: ` for output; output is UTF-8 (the CLI reconfigures `sys.stdout` when needed so accents work on Windows consoles).
- The database path comes from `Settings.db_path`; the directory is created on first use.
- Chat logic lives in `run_chat(reply, store, session_id, read, write)` with injected I/O so it is testable without a terminal.

---

## Contracts

**`src/emporio/cli.py`** 🟡

```python
def main(argv: Sequence[str] | None = None) -> int
def build_parser() -> argparse.ArgumentParser
def export_markdown(store: SessionStore, session_id: str) -> str
def run_chat(reply: Callable[[list[dict], str], AgentTurn], store: SessionStore, session_id: str,
             read: Callable[[str], str], write: Callable[[str], None]) -> None
```

**`src/emporio/__main__.py`** 🟡: `main()` calls `raise SystemExit(cli.main())`.

Commands: `chat [--resume ID] [--today D] [--verbose]`, `sessions`, `handoffs`, `export ID [-o FILE]`, `replay SCRIPT [--today D] [-o FILE]`, `data-report`.

---

## Edge cases

| ID | Scenario | Trigger | Expected behavior |
|---|---|---|---|
| 🟡 EC-01 | Empty line during chat | user presses Enter | Ignored, no model call |
| 🟡 EC-02 | Script with comments only | `replay` file with `#` lines | Exit 2 with "script has no messages" |
| 🟡 EC-03 | Export of an empty session | session with no messages | Header only |
| 🟡 EC-04 | Tool message whose content is long | 5000 characters | Truncated to 300 plus an ellipsis in the export |

---

## Minimum test cases

| # | Target | Scenario | Fixture | Expected result | Test file |
|---|---|---|---|---|---|
| 🟡 T-01 | `run_chat` | one turn, exit words, EOF, empty line | fake reply fn, in-memory store | RF-02, RF-03, EC-01 | `tests/test_cli.py` |
| 🟡 T-02 | `export_markdown` | seeded conversation with a tool call | in-memory store | RF-07, EC-03, EC-04 | `tests/test_cli.py` |
| 🟡 T-03 | `main` | `sessions`, `handoffs`, `data-report` | tmp db seeded through the stores | RF-06, RF-09 | `tests/test_cli.py` |
| 🟡 T-04 | `main` | `replay` with `FakeChatClient` patched in | script file | RF-08, EC-02 | `tests/test_cli.py` |
| 🟡 T-05 | `main` | resume state, unknown session, missing key | tmp db | RF-04, RF-10 | `tests/test_cli.py` |

### Acceptance criterion

```bash
python -m pytest tests/test_cli.py -q
```

---

## Implementation checklist

- [ ] 🟡 `git diff --stat` checked against **Allowed files**
- [ ] 🟡 Tests written before the code; no test calls a real LLM
- [ ] 🟡 Client construction is injectable (a factory argument) so tests patch it
- [ ] 🟡 Only `MissingApiKeyError` and unknown-session errors are caught, each mapped to its exit code
- [ ] 🟡 `ruff check` and `ruff format --check` pass

## Open questions

None.

## Architectural adherence

| Rule | Status | Note |
|---|---|---|
| CLI is the only module that touches stdin/stdout | 🟡 | |
| No silent catch | 🟡 | |
| Scope respected | 🟡 | |