# Spec 04: Policy retrieval

**Status:** 🟡 Draft
**Author:** renatoctti
**Date:** 2026-10-31
**Scope:** PDF parsing and the policy lookup tool
**Depends on:** none
**Delivery:** autonomous

---

## Summary

Extracts the store manual into numbered sections (`1`, `1.1`, `4.2`, ...), fixes the known
contradictions in the text, and offers a lookup that returns the requested sections. A compact
index of ids and titles is meant to live in the system prompt so the model can pick sections.

## Context

The manual has 28 short numbered sections. Section-level retrieval is exact, cheap, lets the agent
cite "item 4.1", and needs no embeddings (see README decision). The extraction must not mistake
numbered list items (`1. Saudação`, `2. Entendimento` in item 7.2) or table rows ("5 a 12 dias
úteis") for headings.

---

## Allowed files

**Production**

- `src/emporio/policies.py` (new)
- `pyproject.toml`: add the `pypdf` dependency

**Tests**

- `tests/test_policies.py` (new)

**Do not touch:** every other file.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| 🟡 RF-01 | `load_policy_sections(pdf_path)` extracts text with page-layout mode, removes page headers ("Empório da Música Manual de Políticas e Procedimentos") and footers ("Página N"), and drops the cover before section 1 | Must | No section text contains "Página 3" or the header line |
| 🟡 RF-02 | Top-level headings match `N. Title` and are accepted **only in strictly increasing order starting at 1**; subsections match `N.M Title` and are accepted only when `N` is the current top-level section | Must | The numbered list of item 7.2 and table rows never become sections |
| 🟡 RF-03 | The parsed ids are exactly: 1 to 10, 1.1, 1.2, 3.1, 4.1 to 4.4, 5.1 to 5.3, 6.1, 6.2, 7.1 to 7.3, 8.1 to 8.3 (28 sections) | Must | Set equality on the real PDF |
| 🟡 RF-04 | Text corrections are applied after extraction: `(67) 3321-4500` becomes `(67) 3341-4444`; `contato@empóriodamusica.com.br` becomes `contato@emporiodamusica.com.br` (A4) | Must | No section contains "3321-4500" or "empóriodamusica"; section 7 contains "3341-4444" |
| 🟡 RF-05 | Table rows that extract as several columns separated by runs of spaces are joined with ` \| ` | Should | Section 3 contains "PIX \| Pagamento à vista" |
| 🟡 RF-06 | `get_policy_sections(sections, section_ids)` returns the requested sections in document order; a top-level id also returns its subsections; ids are de-duplicated; unknown ids go to `not_found` | Must | `["4"]` returns 4, 4.1, 4.2, 4.3, 4.4; `["4", "4.1"]` returns each once; `["99"]` gives `not_found == ["99"]` |
| 🟡 RF-07 | More than 8 requested ids, or an empty list, returns `invalid_argument` | Should | Both covered |
| 🟡 RF-08 | `policy_index(sections)` renders one line per section (`4.1 Direito de Arrependimento (Compras Online)`), indented for subsections | Must | 28 lines, contains "7.3" and its title |
| 🟡 RF-09 | A PDF that yields no sections raises `ValueError`; a missing file raises `FileNotFoundError` | Must | Both covered with a blank PDF fixture and a bad path |

---

## Expected behavior

1. Read pages with `PdfReader(...).pages[i].extract_text(extraction_mode="layout")`, join with newlines.
2. Walk the lines keeping the current top-level id; start a new section at each valid heading; append other lines (right-stripped, internal runs of 2+ spaces collapsed to one, except table rows per RF-05) to the current section.
3. Apply corrections to every section text.

---

## Contracts

**`src/emporio/policies.py`** 🟡

```python
@dataclass(frozen=True)
class PolicySection:
    id: str                  # "4.1"
    title: str               # "Direito de Arrependimento (Compras Online)"
    text: str                # body without the heading line
    parent_id: str | None    # "4", or None for top-level

POLICY_CORRECTIONS: tuple[tuple[str, str], ...]

def load_policy_sections(pdf_path: Path) -> tuple[PolicySection, ...]
def policy_index(sections: Sequence[PolicySection]) -> str
def get_policy_sections(sections: Sequence[PolicySection], section_ids: Sequence[str]) -> dict[str, Any]
# {"sections": [{"id", "title", "text"}...], "not_found": [str...]}
# or {"error": {"code": "invalid_argument", ...}}
```

Errors: `FileNotFoundError`, `ValueError` (no sections found).

---

## Edge cases

| ID | Scenario | Trigger | Expected behavior |
|---|---|---|---|
| 🟡 EC-01 | Heading at a page boundary | `5.2 Entregas para Outras Cidades` is the last line of page 4 | Section 5.2 has its body from page 5 (SEDEX, PAC, Jadlog) |
| 🟡 EC-02 | List item that looks like a heading | `3. Consulta:` after section 7 | Not a section (expected next top-level id is 8) |
| 🟡 EC-03 | Ids with surrounding spaces or a trailing dot | `" 4.1 "`, `"4."` | Normalized to `4.1` and `4` |

---

## Minimum test cases

| # | Target | Scenario | Fixture | Expected result | Test file |
|---|---|---|---|---|---|
| 🟡 T-01 | `load_policy_sections` | ids | real PDF in `data/` | the 28 ids of RF-03 | `tests/test_policies.py` |
| 🟡 T-02 | `load_policy_sections` | corrections and cleaning | real PDF | RF-01, RF-04, RF-05 | `tests/test_policies.py` |
| 🟡 T-03 | `load_policy_sections` | page boundary | real PDF | EC-01 | `tests/test_policies.py` |
| 🟡 T-04 | `get_policy_sections` | expansion, dedupe, not found | real PDF | RF-06 | `tests/test_policies.py` |
| 🟡 T-05 | `get_policy_sections` | invalid arguments | `[]`, 9 ids | `invalid_argument` | `tests/test_policies.py` |
| 🟡 T-06 | `policy_index` | rendering | real PDF | RF-08 | `tests/test_policies.py` |
| 🟡 T-07 | `load_policy_sections` | failures | bad path, blank PDF built with pypdf | RF-09 | `tests/test_policies.py` |

### Acceptance criterion

```bash
python -m pytest tests/test_policies.py -q
```

---

## Implementation checklist

- [ ] 🟡 `git diff --stat` checked against **Allowed files**
- [ ] 🟡 Tests written before the code
- [ ] 🟡 Corrections kept in the named constant `POLICY_CORRECTIONS`, not inline
- [ ] 🟡 No silent catch; extraction failures propagate
- [ ] 🟡 `ruff check` and `ruff format --check` pass

## Open questions

None.

## Architectural adherence

| Rule | Status | Note |
|---|---|---|
| Domain modules do not import the LLM client | 🟡 | |
| No silent catch | 🟡 | |
| Scope respected | 🟡 | |