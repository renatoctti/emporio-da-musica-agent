"""The store manual as numbered sections, plus the lookup used by the agent.

Section-level retrieval is exact and cheap for a manual with 28 short sections, and it lets the
agent cite the item number ("item 4.1"). See the README for why there are no embeddings.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from emporio.results import error

MAX_SECTIONS_PER_CALL = 8

# The manual contradicts itself in two places (assumption A4); the cover and the company table
# win over item 7, and the e-mail is written without an accent.
POLICY_CORRECTIONS: tuple[tuple[str, str], ...] = (
    ("(67) 3321-4500", "(67) 3341-4444"),
    ("contato@empóriodamusica.com.br", "contato@emporiodamusica.com.br"),
)

_PAGE_HEADER = "Empório da Música Manual de Políticas e Procedimentos"
_PAGE_FOOTER = re.compile(r"^Página \d+$")
_TOP_HEADING = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")
_SUB_HEADING = re.compile(r"^(\d{1,2}\.\d{1,2})\s+(\S.*)$")
_COLUMN_GAP = re.compile(r"\s{2,}")
_LIST_MARKER = re.compile(r"^(•|\d+\.)$")


@dataclass(frozen=True)
class PolicySection:
    id: str
    title: str
    text: str
    parent_id: str | None


def _format_line(line: str) -> str:
    """Join table columns with " | " and list markers with the item text."""
    parts = _COLUMN_GAP.split(line.strip())
    if len(parts) == 1:
        return parts[0]
    if _LIST_MARKER.fullmatch(parts[0]):
        return " ".join(parts)
    return " | ".join(parts)


def _clean_text(lines: list[str]) -> str:
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = unicodedata.normalize("NFC", text)
    for wrong, right in POLICY_CORRECTIONS:
        text = text.replace(wrong, right)
    return text


def load_policy_sections(pdf_path: Path) -> tuple[PolicySection, ...]:
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Policy PDF not found: {pdf_path}")

    lines: list[str] = []
    for page in PdfReader(pdf_path).pages:
        lines.extend(page.extract_text(extraction_mode="layout").splitlines())

    drafts: list[dict[str, Any]] = []
    expected_top = 1  # list items such as "1. Saudação" never match: top-level ids only increase
    current_top: str | None = None
    for raw in lines:
        line = unicodedata.normalize("NFC", raw).strip()
        if line == _PAGE_HEADER or _PAGE_FOOTER.fullmatch(line):
            continue
        top = _TOP_HEADING.match(line)
        if top and int(top.group(1)) == expected_top:
            current_top = top.group(1)
            expected_top += 1
            drafts.append({"id": current_top, "title": top.group(2), "parent": None, "lines": []})
            continue
        sub = _SUB_HEADING.match(line)
        if sub and current_top is not None and sub.group(1).split(".")[0] == current_top:
            drafts.append(
                {"id": sub.group(1), "title": sub.group(2), "parent": current_top, "lines": []}
            )
            continue
        if drafts:
            drafts[-1]["lines"].append(_format_line(raw))

    if not drafts:
        raise ValueError(f"no sections found in {pdf_path.name}")
    return tuple(
        PolicySection(
            id=d["id"],
            title=_COLUMN_GAP.sub(" ", d["title"]).strip(),
            text=_clean_text(d["lines"]),
            parent_id=d["parent"],
        )
        for d in drafts
    )


def policy_index(sections: Sequence[PolicySection]) -> str:
    """One line per section, subsections indented; meant for the system prompt."""
    return "\n".join(
        f"{s.id}. {s.title}" if s.parent_id is None else f"  {s.id} {s.title}" for s in sections
    )


def get_policy_sections(
    sections: Sequence[PolicySection], section_ids: Sequence[str]
) -> dict[str, Any]:
    if not section_ids or len(section_ids) > MAX_SECTIONS_PER_CALL:
        return error(
            "invalid_argument",
            f"Request between 1 and {MAX_SECTIONS_PER_CALL} section ids per call.",
        )
    known = {s.id for s in sections}
    wanted: set[str] = set()
    not_found: list[str] = []
    for raw in section_ids:
        section_id = raw.strip().rstrip(".")
        if section_id not in known:
            if section_id not in not_found:
                not_found.append(section_id)
            continue
        wanted.add(section_id)
        wanted.update(s.id for s in sections if s.parent_id == section_id)
    return {
        "sections": [
            {"id": s.id, "title": s.title, "text": s.text} for s in sections if s.id in wanted
        ],
        "not_found": not_found,
    }
