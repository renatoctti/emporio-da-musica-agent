from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def test_package_imports():
    import emporio  # noqa: F401


def test_source_data_present():
    assert (DATA / "políticas_da_loja.pdf").exists()
    assert len(list(DATA.glob("*.csv"))) == 6
