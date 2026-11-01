# Spec 05: Persistence

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-10-31
**Scope:** SQLite connection, conversation history, handoff tickets
**Depends on:** none
**Delivery:** autonomous

---

## Summary

A small SQLite layer (standard library `sqlite3`) with two repositories: `SessionStore` for
conversation history in OpenAI message format and `HandoffStore` for human-handoff tickets. The
schema is created on connect, so there is no setup step.

## Context

The customer must be able to resume a conversation and the store team must be able to list open
tickets. SQLite needs no server and no extra dependency. The database holds personal data, so it
lives under `var/` which is git-ignored.

---

## Allowed files

**Production**

- `src/emporio/db.py` (new)

**Tests**

- `tests/test_db.py` (new)

**Do not touch:** every other file.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| ✅ RF-01 | `connect(path)` creates the parent directory, opens SQLite with `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`, and creates the tables `sessions`, `messages`, `handoffs` if missing; `":memory:"` is allowed | Must | Connecting twice to the same file does not fail and keeps data |
| ✅ RF-02 | `SessionStore.create_session(model, reference_date, now)` returns a new 8-character lowercase hex id and stores model, reference date (or `None`) and creation time | Must | Ids are unique across 100 calls |
| ✅ RF-03 | `append_message(session_id, message, now)` stores the full OpenAI-style message dict as JSON, preserving order; an unknown session raises `UnknownSessionError` | Must | Messages with `tool_calls` and `role: "tool"` round-trip unchanged |
| ✅ RF-04 | `load_messages(session_id)` returns the messages in insertion order; an unknown session raises `UnknownSessionError`; an existing session without messages returns `[]` | Must | Order preserved with 10 messages |
| ✅ RF-05 | `list_sessions(limit=20)` returns `SessionInfo` newest first, with `message_count` and the text of the first `user` message (`None` if none) | Must | Three sessions come back newest first with counts |
| ✅ RF-06 | `HandoffStore.create(...)` inserts a ticket and sets `protocol = f"EMP-{created_at:%Y%m%d}-{id:04d}"` in the **same transaction** | Must | Protocol of the first ticket on 2026-03-25 is `EMP-20260325-0001`; ids increase |
| ✅ RF-07 | `category` must be one of `HANDOFF_CATEGORIES` (`complaint`, `return_request`, `defect`, `other`); anything else raises `ValueError` and stores nothing | Must | Invalid category leaves the table empty |
| ✅ RF-08 | `list_open()` returns open tickets oldest first; `find_open(order_id, category)` returns the matching open ticket or `None` | Must | Closed tickets are excluded |
| ✅ RF-09 | Handoff and message rows reference real sessions when `session_id` is given (foreign key); `customer_id`, `order_id`, `session_id` may be `None` | Must | A ticket with an unknown `session_id` raises `sqlite3.IntegrityError` |

---

## Expected behavior

- Timestamps are stored as ISO-8601 text (`datetime.isoformat(timespec="seconds")`) and parsed back to `datetime`.
- Each repository method opens its own short transaction through the connection (`with conn:`) so a failed insert never leaves a half-written ticket.
- Infrastructure errors (`sqlite3.Error`) propagate untouched.

---

## Contracts

**`src/emporio/db.py`** ✅

```python
HANDOFF_CATEGORIES: tuple[str, ...] = ("complaint", "return_request", "defect", "other")

class UnknownSessionError(KeyError): ...

@dataclass(frozen=True)
class SessionInfo:
    id: str
    created_at: datetime
    model: str
    message_count: int
    first_user_message: str | None

@dataclass(frozen=True)
class Handoff:
    id: int
    protocol: str
    category: str
    summary: str
    customer_id: int | None
    order_id: int | None
    session_id: str | None
    created_at: datetime
    due_at: datetime
    status: str            # "open" | "closed"

def connect(path: Path | str) -> sqlite3.Connection

class SessionStore:
    def __init__(self, conn: sqlite3.Connection) -> None
    def create_session(self, model: str, reference_date: date | None, now: datetime) -> str
    def append_message(self, session_id: str, message: dict[str, Any], now: datetime) -> None
    def load_messages(self, session_id: str) -> list[dict[str, Any]]
    def list_sessions(self, limit: int = 20) -> list[SessionInfo]

class HandoffStore:
    def __init__(self, conn: sqlite3.Connection) -> None
    def create(self, *, category: str, summary: str, customer_id: int | None, order_id: int | None,
               session_id: str | None, created_at: datetime, due_at: datetime) -> Handoff
    def list_open(self) -> list[Handoff]
    def find_open(self, order_id: int, category: str) -> Handoff | None
```

Tables: `sessions(id TEXT PRIMARY KEY, created_at TEXT, model TEXT, reference_date TEXT)`;
`messages(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT REFERENCES sessions(id), created_at TEXT, message_json TEXT)`;
`handoffs(id INTEGER PRIMARY KEY AUTOINCREMENT, protocol TEXT UNIQUE, category TEXT, summary TEXT, customer_id INTEGER, order_id INTEGER, session_id TEXT REFERENCES sessions(id), created_at TEXT, due_at TEXT, status TEXT DEFAULT 'open')`.

---

## Edge cases

| ID | Scenario | Trigger | Expected behavior |
|---|---|---|---|
| ✅ EC-01 | Non-ASCII content | Portuguese text with accents and emoji | Round-trips exactly (`ensure_ascii=False`) |
| ✅ EC-02 | Two tickets same day | second `create` | Protocol ends `0002` |
| ✅ EC-03 | Re-open the database file | new `connect` on the same path | Previous sessions and tickets are visible |

---

## Minimum test cases

| # | Target | Scenario | Fixture | Expected result | Test file |
|---|---|---|---|---|---|
| ✅ T-01 | `connect` | idempotent schema, persistence on disk | tmp file path | RF-01, EC-03 | `tests/test_db.py` |
| ✅ T-02 | `SessionStore` | create, append, load with tool messages | in-memory | RF-02 to RF-04, EC-01 | `tests/test_db.py` |
| ✅ T-03 | `SessionStore` | unknown session | in-memory | `UnknownSessionError` on append and load | `tests/test_db.py` |
| ✅ T-04 | `list_sessions` | ordering and counts | three sessions | RF-05 | `tests/test_db.py` |
| ✅ T-05 | `HandoffStore.create` | protocol format and EC-02 | in-memory | RF-06 | `tests/test_db.py` |
| ✅ T-06 | `HandoffStore.create` | invalid category, bad foreign key | in-memory | `ValueError`, `IntegrityError`, no row stored | `tests/test_db.py` |
| ✅ T-07 | `list_open`, `find_open` | open vs closed (closed through a direct `UPDATE` in the test) | in-memory | RF-08 | `tests/test_db.py` |

### Acceptance criterion

```bash
python -m pytest tests/test_db.py -q
```

---

## Implementation checklist

- [x] ✅ `git diff --stat` checked against **Allowed files**
- [x] ✅ Tests written before the code
- [x] ✅ Parameterized SQL only (no string-built queries)
- [x] ✅ No silent catch; `sqlite3.Error` propagates
- [x] ✅ `ruff check` and `ruff format --check` pass

## Open questions

None.

## Architectural adherence

| Rule | Status | Note |
|---|---|---|
| Domain modules do not import the LLM client | ✅ | |
| No silent catch | ✅ | |
| Scope respected | ✅ | |