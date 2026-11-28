"""Tests for SC-07: bank statement reconciliation.

What is guarded here is not the numbers from a particular run, but the
properties of the measuring instrument:

1. The reference must be independent of the model being tested. If the
   reference were read by the same model, the result would be a model compared
   against itself.
2. The verdict uses the closing balance only, never the transaction count.
3. Any difference, however small, must make the criterion fail.
4. File names are never truncated, because truncating loses reproducible
   evidence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

import sc07_reconciliation as sc07  # noqa: E402

import sc_common as cfg  # noqa: E402

STATEMENT_DIR = cfg.statements_dir()
BRI_PDF = STATEMENT_DIR / "Mutasi_Rekening_BRI-Januari_2026.pdf"


def _ensure_statements() -> None:
    """Fetch the statement PDFs once so these tests do not depend on a local path."""
    if BRI_PDF.exists() and (STATEMENT_DIR / "BNI_Mutasi_Januari_2026.pdf").exists():
        return
    try:
        cfg.download_statements(STATEMENT_DIR)
    except SystemExit as exc:
        pytest.skip(f"statement PDFs unavailable: {exc}")


def _sample(difference=0.0, statement_closing=192643952.0, validation=True, errors=()):
    return {
        "model": "test",
        "references_independent": True,
        "samples": [{
            "file": "Mutasi_Rekening_BRI-Januari_2026.pdf",
            "reference_kind": "PDF text layer",
            "reference_independent": True,
            "account_number_reference": "306601000009566",
            "account_number_statement": "306601000009566",
            "period_reference": ["2026-01-01", "2026-01-31"],
            "period_statement": ["2026-01-01", "2026-01-31"],
            "opening_balance_reference": 214531779.0,
            "opening_balance_statement": 214531779.0,
            "total_debit_reference": 22066136.0,
            "total_debit_statement": 22066136.0,
            "total_credit_reference": 178309.0,
            "total_credit_statement": 178309.0,
            "closing_balance_reference": 192643952.0,
            "closing_balance_statement": statement_closing,
            "closing_balance_difference": difference,
            "transaction_count_reference": 14,
            "transaction_count_statement": 14,
            "validation_passed": validation,
            "validation_errors": list(errors),
            "seconds": 1.0,
            "error": "",
        }],
    }


def _write(tmp_path: Path, data: dict) -> Path:
    (tmp_path / "sc07_samples.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def test_matching_closing_balance_passes(tmp_path):
    result = sc07.write_report(_write(tmp_path, _sample()))
    assert result["metrics"]["passed"] is True
    assert result["metrics"]["matched"] == 1


def test_one_rupiah_difference_fails(tmp_path):
    """A difference of any size means a transaction was not read correctly."""
    result = sc07.write_report(
        _write(tmp_path, _sample(difference=1.0, statement_closing=192643953.0))
    )
    assert result["metrics"]["passed"] is False
    assert result["metrics"]["mismatched"] == 1


def test_unreadable_balance_is_not_a_pass(tmp_path):
    """A balance that could not be read must not count as matching."""
    data = _sample()
    data["samples"][0]["closing_balance_statement"] = None
    data["samples"][0]["closing_balance_difference"] = None
    result = sc07.write_report(_write(tmp_path, data))
    assert result["metrics"]["passed"] is False
    assert result["metrics"]["unreadable"] == 1


def test_transaction_count_does_not_decide_the_verdict(tmp_path):
    """SC-07 judges the closing balance. The transaction count is supporting detail.

    If the count took part in the verdict, this criterion would quietly become
    a different criterion with a different denominator.
    """
    data = _sample()
    data["samples"][0]["transaction_count_statement"] = 99
    result = sc07.write_report(_write(tmp_path, data))
    assert result["metrics"]["passed"] is True, "transaction count must not judge the target"


def test_reference_is_independent_of_the_model():
    """The reference must not come from the model under test."""
    import _sc07_run as run

    _ensure_statements()
    for filename in (run.BNI_FILE, run.BRI_FILE):
        path = STATEMENT_DIR / filename
        if not path.exists():
            pytest.skip(f"{filename} not available")
        reference = run._reference(filename, path.read_bytes())
        assert reference["independent_of_model"] is True
        assert reference["closing_balance"] is not None


def test_bni_reference_is_manual_and_records_where_the_figures_sit():
    """BNI has no text layer, so its reference is manual and must be traceable."""
    import _sc07_run as run

    reference = run.read_bni_reference()
    assert reference["closing_balance"] == 9556974.0
    assert reference["opening_balance"] + reference["total_credit"] - reference["total_debit"] \
        == reference["closing_balance"]
    assert reference["figures_location"], "where the figures sit must be recorded for re-checking"
    assert "scan" in reference["manual_reason"].lower() or "0 characters" in reference["manual_reason"]


def test_bri_text_layer_is_arithmetically_consistent():
    """Opening balance + credit - debit must equal the printed closing balance."""
    import _sc07_text_statement as statement

    _ensure_statements()
    if not BRI_PDF.exists():
        pytest.skip("BRI PDF not available")

    data = statement.read_text_statement(BRI_PDF.read_bytes())
    assert data["transaction_count"] == 14
    assert data["opening_balance_printed"] + data["total_credit_printed"] \
        - data["total_debit_printed"] == data["closing_balance_printed"]

    running = data["opening_balance_printed"]
    for row in data["transactions"]:
        running = running + row["credit"] - row["debit"]
        assert abs(running - row["balance"]) < 0.01


def test_file_names_are_never_truncated(tmp_path):
    """Truncating a file name loses evidence that can be reproduced."""
    data = _sample()
    long_name = "Mutasi_Rekening_BRI-Januari_2026_a_very_long_name_for_testing.pdf"
    data["samples"][0]["file"] = long_name
    result = sc07.write_report(_write(tmp_path, data))

    text = result["text"]
    assert text.count(long_name) >= 3, "file name must stay whole in every table"
    assert "Mutasi_Rekening_BRI-Januari_2026_a_very" not in text.replace(long_name, ""), \
        "a file name was truncated in one of the tables"


def test_statement_download_maps_repo_names_to_local_names(tmp_path):
    """The dataset repo uses spaces in file names; SC-07 uses underscores.

    Without this mapping, anyone reproducing the measurement has to rename the
    files by hand, and a wrong name silently becomes a skipped account.
    """
    import sc_common as cfg

    assert cfg.STATEMENT_FILES["BNI_Mutasi_Januari_2026.pdf"] == "BNI_Mutasi_Januari_2026.pdf"
    assert cfg.STATEMENT_FILES["Mutasi_Rekening_BRI-Januari_2026.pdf"] == \
        "Mutasi Rekening BRI-Januari 2026.pdf"
    assert cfg.STATEMENTS_SUBDIR == "Cash Report dan Mutasi Rekening"

    # Both names the harness expects must be reachable from the mapping.
    import _sc07_run as run

    assert run.BRI_FILE in cfg.STATEMENT_FILES
    assert run.BNI_FILE in cfg.STATEMENT_FILES


def test_missing_samples_gives_instructions(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        sc07.write_report(tmp_path)
    assert "_sc07_run.py" in str(excinfo.value)


def test_empty_reply_aborts_the_whole_statement_without_retry():
    """A blank model reply stops the whole reconciliation, not just one page.

    This is why the run is not stable: two of three measurements stopped here.
    `post_with_retry` only retries HTTP 5xx, so an empty body raises at once and
    no partial result is produced. The test pins the current behaviour so that
    adding a retry is a deliberate decision, not an accident.
    """
    import inspect

    import reconciliation.vision_extractor as extractor

    source = inspect.getsource(extractor)

    assert "Empty AI response" in source
    # Retry must not yet cover an empty body: only HTTP status errors are caught.
    retry_body = inspect.getsource(extractor.post_with_retry)
    assert "HTTPStatusError" in retry_body
    assert "Empty AI response" not in retry_body, (
        "empty replies are now retried; update the SC-07 stability section"
    )
