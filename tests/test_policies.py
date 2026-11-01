import re
from pathlib import Path

import pytest
from pypdf import PdfWriter

from emporio.policies import get_policy_sections, load_policy_sections, policy_index
from emporio.results import is_error

PDF = Path(__file__).resolve().parents[1] / "data" / "políticas_da_loja.pdf"

EXPECTED_IDS = (
    [str(n) for n in range(1, 11)]
    + ["1.1", "1.2", "3.1", "4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "5.3"]
    + ["6.1", "6.2", "7.1", "7.2", "7.3", "8.1", "8.2", "8.3"]
)


@pytest.fixture(scope="module")
def sections():
    return load_policy_sections(PDF)


def by_id(sections, section_id):
    return next(s for s in sections if s.id == section_id)


def test_parses_the_28_numbered_sections(sections):
    assert len(sections) == 28
    assert {s.id for s in sections} == set(EXPECTED_IDS)


def test_sections_are_in_document_order_with_parents(sections):
    assert [s.id for s in sections[:5]] == ["1", "1.1", "1.2", "2", "3"]
    assert by_id(sections, "4.2").parent_id == "4"
    assert by_id(sections, "4").parent_id is None
    assert by_id(sections, "4.1").title == "Direito de Arrependimento (Compras Online)"


def test_headers_footers_and_cover_are_removed(sections):
    text = "\n".join(s.text for s in sections)
    assert "Manual de Políticas e Procedimentos" not in text
    assert not re.search(r"Página \d", text)
    assert "Uso restrito" not in text


def test_known_contradictions_are_corrected(sections):
    text = "\n".join(s.text for s in sections)
    assert "3321-4500" not in text
    assert "empóriodamusica" not in text
    assert "(67) 3341-4444" in by_id(sections, "7").text
    assert "contato@emporiodamusica.com.br" in by_id(sections, "1.2").text


def test_table_rows_are_joined_with_pipes_and_bullets_are_not(sections):
    section3 = by_id(sections, "3").text
    assert "PIX | Pagamento à vista | 5% de desconto" in section3
    section31 = by_id(sections, "3.1").text
    assert "| Parcelamento" not in section31 and "• Parcelamento em até 3x" in section31


def test_section_split_across_a_page_boundary(sections):
    text = by_id(sections, "5.2").text
    assert "SEDEX" in text and "Jadlog" in text


def test_numbered_list_items_are_not_headings(sections):
    text = by_id(sections, "7.2").text
    assert "Saudação" in text and "Fechamento" in text


def test_get_expands_top_level_sections_and_deduplicates(sections):
    r = get_policy_sections(sections, ["4"])
    assert [s["id"] for s in r["sections"]] == ["4", "4.1", "4.2", "4.3", "4.4"]
    both = get_policy_sections(sections, ["4.1", "4"])
    assert [s["id"] for s in both["sections"]] == ["4", "4.1", "4.2", "4.3", "4.4"]
    assert r["not_found"] == []


def test_get_normalizes_ids_and_reports_unknown_ones(sections):
    r = get_policy_sections(sections, [" 4.1 ", "4.", "99"])
    assert [s["id"] for s in r["sections"]][:2] == ["4", "4.1"]
    assert r["not_found"] == ["99"]
    assert get_policy_sections(sections, ["99"]) == {"sections": [], "not_found": ["99"]}


def test_get_returns_title_and_text(sections):
    section = get_policy_sections(sections, ["8.1"])["sections"][0]
    assert section["title"] == "Garantia Legal"
    assert "90" in section["text"]


@pytest.mark.parametrize("ids", [[], [str(n) for n in range(1, 10)]])
def test_get_rejects_empty_and_oversized_requests(sections, ids):
    r = get_policy_sections(sections, ids)
    assert is_error(r) and r["error"]["code"] == "invalid_argument"


def test_index_has_one_line_per_section(sections):
    lines = policy_index(sections).splitlines()
    assert len(lines) == 28
    assert "7.3 Situações Especiais" in " ".join(lines)
    sub = next(line for line in lines if "4.1 Direito" in line)
    top = next(line for line in lines if line.startswith("4. "))
    assert sub.startswith("  ") and not top.startswith(" ")


def test_failures_are_loud(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_policy_sections(tmp_path / "missing.pdf")
    blank = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with blank.open("wb") as handle:
        writer.write(handle)
    with pytest.raises(ValueError, match="no sections"):
        load_policy_sections(blank)
