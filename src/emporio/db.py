"""SQLite storage: conversation history and human-handoff tickets.

Uses only the standard library. The file holds personal data, so it lives under `var/`,
which is git-ignored.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from emporio.metrics import TurnMetrics

HANDOFF_CATEGORIES: tuple[str, ...] = ("complaint", "return_request", "defect", "other")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    reference_date TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    created_at TEXT NOT NULL,
    message_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocol TEXT UNIQUE,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    customer_id INTEGER,
    order_id INTEGER,
    session_id TEXT REFERENCES sessions(id),
    created_at TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS turn_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    turn_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    model_calls INTEGER NOT NULL,
    tool_calls INTEGER NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    UNIQUE (session_id, turn_index)
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    turn_index INTEGER NOT NULL,
    rating TEXT NOT NULL CHECK (rating IN ('up', 'down')),
    comment TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (session_id, turn_index)
);
"""


class UnknownSessionError(KeyError):
    """The session id is not in the database."""


@dataclass(frozen=True)
class SessionInfo:
    id: str
    created_at: datetime
    model: str
    message_count: int
    first_user_message: str | None
    reference_date: date | None = None


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
    status: str


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


_SESSION_QUERY = """
    SELECT s.id, s.created_at, s.model, s.reference_date,
           (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count,
           (SELECT json_extract(m.message_json, '$.content') FROM messages m
             WHERE m.session_id = s.id AND json_extract(m.message_json, '$.role') = 'user'
             ORDER BY m.id LIMIT 1) AS first_user_message
    FROM sessions s
"""


def _session_info(row: sqlite3.Row) -> SessionInfo:
    return SessionInfo(
        id=row["id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        model=row["model"],
        message_count=row["message_count"],
        first_user_message=row["first_user_message"],
        reference_date=date.fromisoformat(row["reference_date"]) if row["reference_date"] else None,
    )


def _turn_metrics(row: sqlite3.Row) -> TurnMetrics:
    return TurnMetrics(
        latency_ms=row["latency_ms"],
        model_calls=row["model_calls"],
        tool_calls=row["tool_calls"],
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
    )


class SessionStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _require(self, session_id: str) -> None:
        row = self._conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise UnknownSessionError(session_id)

    def create_session(self, model: str, reference_date: date | None, now: datetime) -> str:
        session_id = secrets.token_hex(4)
        with self._conn:
            self._conn.execute(
                "INSERT INTO sessions (id, created_at, model, reference_date) VALUES (?, ?, ?, ?)",
                (
                    session_id,
                    _stamp(now),
                    model,
                    reference_date.isoformat() if reference_date else None,
                ),
            )
        return session_id

    def append_message(self, session_id: str, message: dict[str, Any], now: datetime) -> None:
        self._require(session_id)
        with self._conn:
            self._conn.execute(
                "INSERT INTO messages (session_id, created_at, message_json) VALUES (?, ?, ?)",
                (session_id, _stamp(now), json.dumps(message, ensure_ascii=False)),
            )

    def append_messages(
        self,
        session_id: str,
        messages: Sequence[dict[str, Any]],
        now: datetime,
        metrics: TurnMetrics | None = None,
    ) -> None:
        """Store a whole turn in one transaction: every message (and its metrics) or none."""
        self._require(session_id)
        rows = [(session_id, _stamp(now), json.dumps(m, ensure_ascii=False)) for m in messages]
        with self._conn:
            # The turn index is the number of customer messages stored before this turn.
            turn_index = self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?"
                " AND json_extract(message_json, '$.role') = 'user'",
                (session_id,),
            ).fetchone()[0]
            self._conn.executemany(
                "INSERT INTO messages (session_id, created_at, message_json) VALUES (?, ?, ?)",
                rows,
            )
            if metrics is not None:
                self._conn.execute(
                    "INSERT INTO turn_metrics (session_id, turn_index, created_at, latency_ms,"
                    " model_calls, tool_calls, prompt_tokens, completion_tokens)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        turn_index,
                        _stamp(now),
                        metrics.latency_ms,
                        metrics.model_calls,
                        metrics.tool_calls,
                        metrics.prompt_tokens,
                        metrics.completion_tokens,
                    ),
                )

    def load_messages(self, session_id: str) -> list[dict[str, Any]]:
        self._require(session_id)
        rows = self._conn.execute(
            "SELECT message_json FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
        )
        return [json.loads(row["message_json"]) for row in rows]

    def load_turn_metrics(self, session_id: str) -> dict[int, TurnMetrics]:
        """Metrics of a conversation by turn index (turns stored before spec 14 have none)."""
        self._require(session_id)
        rows = self._conn.execute(
            "SELECT * FROM turn_metrics WHERE session_id = ? ORDER BY turn_index", (session_id,)
        )
        return {row["turn_index"]: _turn_metrics(row) for row in rows}

    def all_turn_metrics(self, session_id: str | None = None) -> list[TurnMetrics]:
        if session_id is None:
            rows = self._conn.execute("SELECT * FROM turn_metrics ORDER BY id")
        else:
            rows = self._conn.execute(
                "SELECT * FROM turn_metrics WHERE session_id = ? ORDER BY id", (session_id,)
            )
        return [_turn_metrics(row) for row in rows]

    def save_feedback(
        self,
        session_id: str,
        turn_index: int,
        rating: str | None,
        comment: str | None,
        now: datetime,
    ) -> None:
        """One rating per turn: a new one replaces the old, None removes it."""
        self._require(session_id)
        with self._conn:
            if rating is None:
                self._conn.execute(
                    "DELETE FROM feedback WHERE session_id = ? AND turn_index = ?",
                    (session_id, turn_index),
                )
                return
            self._conn.execute(
                "INSERT INTO feedback (session_id, turn_index, rating, comment, created_at)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (session_id, turn_index) DO UPDATE SET"
                " rating = excluded.rating, comment = excluded.comment,"
                " created_at = excluded.created_at",
                (session_id, turn_index, rating, comment, _stamp(now)),
            )

    def load_feedback(self, session_id: str) -> dict[int, tuple[str, str | None]]:
        self._require(session_id)
        rows = self._conn.execute(
            "SELECT turn_index, rating, comment FROM feedback WHERE session_id = ?", (session_id,)
        )
        return {row["turn_index"]: (row["rating"], row["comment"]) for row in rows}

    def down_feedback(self) -> list[tuple[str, int, str | None]]:
        """Every answer rated down, as (session id, turn index, comment), oldest first."""
        rows = self._conn.execute(
            "SELECT session_id, turn_index, comment FROM feedback WHERE rating = 'down' ORDER BY id"
        )
        return [(row["session_id"], row["turn_index"], row["comment"]) for row in rows]

    def get_session(self, session_id: str) -> SessionInfo:
        row = self._conn.execute(_SESSION_QUERY + " WHERE s.id = ?", (session_id,)).fetchone()
        if row is None:
            raise UnknownSessionError(session_id)
        return _session_info(row)

    def list_sessions(self, limit: int = 20) -> list[SessionInfo]:
        rows = self._conn.execute(
            _SESSION_QUERY + " ORDER BY s.created_at DESC, s.rowid DESC LIMIT ?", (limit,)
        )
        return [_session_info(row) for row in rows]


def _handoff(row: sqlite3.Row) -> Handoff:
    return Handoff(
        id=row["id"],
        protocol=row["protocol"],
        category=row["category"],
        summary=row["summary"],
        customer_id=row["customer_id"],
        order_id=row["order_id"],
        session_id=row["session_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        due_at=datetime.fromisoformat(row["due_at"]),
        status=row["status"],
    )


class HandoffStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        *,
        category: str,
        summary: str,
        customer_id: int | None,
        order_id: int | None,
        session_id: str | None,
        created_at: datetime,
        due_at: datetime,
    ) -> Handoff:
        if category not in HANDOFF_CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(HANDOFF_CATEGORIES)}")
        # One transaction: the protocol needs the row id, so a failure never leaves a half ticket.
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO handoffs (category, summary, customer_id, order_id, session_id,"
                " created_at, due_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    category,
                    summary,
                    customer_id,
                    order_id,
                    session_id,
                    _stamp(created_at),
                    _stamp(due_at),
                ),
            )
            handoff_id = cursor.lastrowid
            protocol = f"EMP-{created_at:%Y%m%d}-{handoff_id:04d}"
            self._conn.execute(
                "UPDATE handoffs SET protocol = ? WHERE id = ?", (protocol, handoff_id)
            )
        row = self._conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone()
        return _handoff(row)

    def list_open(self) -> list[Handoff]:
        rows = self._conn.execute("SELECT * FROM handoffs WHERE status = 'open' ORDER BY id")
        return [_handoff(row) for row in rows]

    def find_open(self, order_id: int, category: str) -> Handoff | None:
        row = self._conn.execute(
            "SELECT * FROM handoffs WHERE status = 'open' AND order_id = ? AND category = ?"
            " ORDER BY id LIMIT 1",
            (order_id, category),
        ).fetchone()
        return _handoff(row) if row else None
