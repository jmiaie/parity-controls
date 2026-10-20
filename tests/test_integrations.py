"""parity_integrations: the freeze/verify lockfile, and the dbt and GX adapter skeletons.

Every refusal is driven, not assumed: each verify test mutates a copy of the fixture and
asserts the refusal names the mechanism. Tests that need dbt or Great Expectations installed
skip when they are absent; the missing-dependency path is tested instead, and skips when the
dependency IS present.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from parity import ParityViolation, canonical_hash
from parity_integrations import MissingDependency
from parity_integrations import dbt as pdbt
from parity_integrations import great_expectations as pgx
from parity_integrations.lockfile import freeze, main, read_csv_rows, verify

FIXTURE = Path(__file__).parent / "fixtures" / "books"
HAS_DBT = importlib.util.find_spec("dbt") is not None
HAS_GX = importlib.util.find_spec("great_expectations") is not None


@pytest.fixture
def books(tmp_path):
    d = tmp_path / "books"
    shutil.copytree(FIXTURE, d)
    return d


# ---------------------------------------------------------------- lockfile: freeze / verify

def test_freeze_then_verify_passes_on_unchanged_files(books):
    lock = freeze(books)
    assert sorted(lock["files"]) == ["balances.csv", "positions.csv"]
    assert lock["files"]["positions.csv"]["rows"] == 3
    assert verify(books, lock) is True


def test_row_order_does_not_move_the_digest(books):
    lock = freeze(books)
    p = books / "positions.csv"
    head, *rows = p.read_text().splitlines()
    p.write_text("\n".join([head, *reversed(rows)]) + "\n")
    assert verify(books, lock) is True


def test_a_changed_cell_is_refused(books):
    lock = freeze(books)
    p = books / "positions.csv"
    p.write_text(p.read_text().replace("sell,short", "sell,long"))
    with pytest.raises(ParityViolation, match="positions.csv: canonical hash moved"):
        verify(books, lock)


def test_a_dropped_row_is_refused(books):
    lock = freeze(books)
    p = books / "balances.csv"
    p.write_text("\n".join(p.read_text().splitlines()[:-1]) + "\n")
    with pytest.raises(ParityViolation, match="balances.csv: canonical hash moved"):
        verify(books, lock)


def test_a_renamed_file_reads_as_one_missing_and_one_unwanted(books):
    lock = freeze(books)
    (books / "balances.csv").rename(books / "balances_v2.csv")
    with pytest.raises(ParityViolation) as exc:
        verify(books, lock)
    msg = str(exc.value)
    assert "never landed ['balances.csv']" in msg and "arrived unwanted ['balances_v2.csv']" in msg


def test_a_duplicated_header_is_refused_not_collapsed(tmp_path):
    p = tmp_path / "dup.csv"
    p.write_text("id,side,side\n1,buy,long\n")
    with pytest.raises(ParityViolation, match="duplicated header"):
        read_csv_rows(p)


def test_a_ragged_row_is_refused(tmp_path):
    p = tmp_path / "ragged.csv"
    p.write_text("id,side\n1,buy,EXTRA\n")
    with pytest.raises(ParityViolation, match="ragged row"):
        read_csv_rows(p)


def test_freezing_an_empty_set_is_refused(tmp_path):
    with pytest.raises(ParityViolation, match="refusing to freeze an empty set"):
        freeze(tmp_path)


def test_digest_is_the_core_canonical_hash_over_text_cells(books):
    lock = freeze(books / "balances.csv")
    rows = [{"account": "A-1", "ccy": "USD", "balance": "1000.00"},
            {"account": "A-2", "ccy": "EUR", "balance": "250.50"}]
    assert lock["files"]["balances.csv"]["digest"] == canonical_hash(
        rows, columns=["account", "ccy", "balance"])


def test_cli_exit_codes(books, tmp_path, capsys):
    lock = tmp_path / "lock.json"
    assert main(["freeze", str(books), "--lock", str(lock)]) == 0
    assert json.loads(lock.read_text())["version"] == 1
    assert main(["verify", str(books), "--lock", str(lock)]) == 0
    (books / "positions.csv").write_text("trade_id\nP-1\n")
    assert main(["verify", str(books), "--lock", str(lock)]) == 1
    assert "PARITY VIOLATION" in capsys.readouterr().err
    assert main(["verify", str(books), "--lock", str(tmp_path / "missing.json")]) == 2


# ---------------------------------------------------------------- dbt adapter

def _dbt_project(tmp_path):
    proj = tmp_path / "proj"
    (proj / "seeds").mkdir(parents=True)
    (proj / "dbt_project.yml").write_text("name: demo\n")
    shutil.copy(FIXTURE / "balances.csv", proj / "seeds" / "balances.csv")
    return proj


def test_dbt_seeds_freeze_and_verify_without_dbt_installed(tmp_path):
    proj = _dbt_project(tmp_path)
    lock = pdbt.freeze_seeds(proj)
    assert pdbt.verify_seeds(proj, lock) is True
    (proj / "seeds" / "balances.csv").write_text("account,ccy,balance\nA-1,USD,0\n")
    with pytest.raises(ParityViolation):
        pdbt.verify_seeds(proj, lock)


def test_dbt_seeds_refuse_a_directory_that_is_not_a_dbt_project(tmp_path):
    with pytest.raises(FileNotFoundError, match="dbt_project.yml"):
        pdbt.freeze_seeds(tmp_path)


@pytest.mark.skipif(HAS_DBT, reason="dbt is installed; the missing-dependency path cannot run")
def test_dbt_relation_parity_names_the_extra_when_dbt_is_missing(tmp_path):
    with pytest.raises(MissingDependency, match=r"parity-controls\[dbt\]"):
        pdbt.relation_key_parity(tmp_path, "src", "model", "id")


@pytest.mark.skipif(not HAS_DBT, reason="needs dbt-core (pip install 'parity-controls[dbt]')")
def test_dbt_relation_parity_is_an_honest_stub_with_dbt_installed(tmp_path):
    with pytest.raises(NotImplementedError, match="ROADMAP"):
        pdbt.relation_key_parity(tmp_path, "src", "model", "id")


# ---------------------------------------------------------------- Great Expectations adapter

def test_gx_shaped_results_without_gx_installed():
    ok = pgx.expect_offered_present_parity({1, 2}, {2, 1})
    assert ok == {"success": True, "expectation_type": "expect_offered_present_parity",
                  "result": {"message": None}}
    bad = pgx.expect_offered_present_parity({1, 2}, {1, 3}, key="id")
    assert bad["success"] is False and "never landed [2]" in bad["result"]["message"]
    xf = pgx.expect_cross_field(iter([("buy", "short")]), {"buy": ("long",)})
    assert xf["success"] is False and xf["result"]["element_count"] == 1
    rows = [{"a": 1}]
    h = pgx.expect_canonical_hash(rows, canonical_hash(rows))
    assert h["success"] is True and h["result"]["observed_value"] == canonical_hash(rows)
    assert pgx.expect_canonical_hash(rows, "0" * 64)["success"] is False


def test_gx_misuse_is_raised_not_reported_as_a_failed_expectation():
    with pytest.raises(TypeError):
        pgx.expect_offered_present_parity("abc", "cba")


@pytest.mark.skipif(HAS_GX, reason="great_expectations is installed; missing path cannot run")
def test_gx_register_names_the_extra_when_gx_is_missing():
    with pytest.raises(MissingDependency, match=r"parity-controls\[great-expectations\]"):
        pgx.register_expectations()


@pytest.mark.skipif(not HAS_GX, reason="needs great_expectations "
                    "(pip install 'parity-controls[great-expectations]')")
def test_gx_register_is_an_honest_stub_with_gx_installed():
    with pytest.raises(NotImplementedError, match="ROADMAP"):
        pgx.register_expectations()


def test_importing_parity_pulls_in_no_integration():
    import subprocess
    import sys
    out = subprocess.run(
        [sys.executable, "-c", "import sys, parity; print(sorted(m for m in sys.modules "
         "if m.startswith(('parity_integrations', 'dbt', 'great_expectations'))))"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
