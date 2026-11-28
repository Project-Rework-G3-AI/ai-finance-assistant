"""Guards for the SC-08 measuring tool.

These tests do not measure the bot. They check that the tool cannot quietly
report a pass it did not earn. Each one names the way the tool could lie:

1. comparing the bot against its own function   -> reference must be independent
2. one correct number hiding three wrong ones   -> every figure is required
3. a fluent answer with a wrong figure          -> fails
4. a shorter correct answer                     -> passes
5. text without a number counted as agreement   -> fails
6. zero demanded as a stated digit              -> not required
7. only the first question deciding the verdict -> every answer counts
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _sc08_ledger as ledger_tools  # noqa: E402
import _sc08_reference as reference  # noqa: E402
import _sc08_run as runner  # noqa: E402
import sc08_qa as report  # noqa: E402


# A small ledger used when no extraction run is available. It is built here on
# purpose: a guard test that skips on a fresh clone protects nothing, and a test
# that only runs on the author's machine is not a guard at all.
FALLBACK_ROWS = [
    ["2026-01-02 09:00:00", "BNI", 500_000, "", "Pendapatan Usaha (Penjualan Produk)", "penjualan", "verified", "", "r1", "a.jpg", ""],
    ["2026-01-03 09:00:00", "BNI", 250_000, "", "Pendapatan Lain", "lain", "verified", "", "r2", "b.jpg", ""],
    ["2026-01-04 09:00:00", "BNI", "", 300_000, "Bahan Baku", "beli", "verified", "", "r3", "c.jpg", ""],
    ["2026-01-05 09:00:00", "BNI", "", 120_000, "Biaya-Ongkir", "kirim", "verified", "", "r4", "d.jpg", ""],
    ["2026-01-06 09:00:00", "BNI", "", 35_000, "Biaya-Ongkir", "kirim draft", "draft", "", "r5", "e.jpg", ""],
    ["2026-01-07 09:00:00", "BNI", "", 100_000, "Transfer Antar Bank", "transfer", "verified", "", "r6", "f.jpg", ""],
    ["2026-01-07 09:00:00", "BNI", 100_000, "", "Transfer Antar Bank", "transfer", "verified", "", "r6", "f.jpg", ""],
]


@pytest.fixture(scope="module")
def records() -> list[dict]:
    """Ledger rows for the guard tests.

    Uses the real extraction output when it is there, otherwise the small ledger
    above. Either way the guards run: they check the tool, not the data, so a
    missing extraction run must not turn them into no-ops.
    """
    results = REPO / "sc-out" / "results_per_row.csv"
    if results.exists():
        rows, _ = ledger_tools.build_ledger(results)
        return reference.read_rows(rows)
    return reference.read_rows(FALLBACK_ROWS)


@pytest.fixture(scope="module")
def expected(records) -> dict:
    return runner.build_expectations(records)


def correct_answer(expected: dict) -> str:
    """A fully correct answer to Q1, naming every figure the question asks for.

    Q1 asks for verified and draft separately, so a correct answer must state
    all four figures. Building it here keeps the guard tests honest: any test
    that fails below fails because of the change it makes, not because the
    baseline was already incomplete.
    """
    return (
        f"Uang masuk verified Rp{expected['verified']['in']:,.0f}, "
        f"draft Rp{expected['draft']['in']:,.0f}. "
        f"Uang keluar verified Rp{expected['verified']['out']:,.0f}, "
        f"draft Rp{expected['draft']['out']:,.0f}."
    )


def test_reference_answers_are_computed_without_the_production_module():
    """The reference must not import the code it judges.

    If it did, SC-08 would compare the answer path against itself: a bug in that
    function would appear on both sides and the measurement would always pass.
    """
    import ast

    path = Path(__file__).resolve().parent / "_sc08_reference.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    forbidden = [name for name in imported if name.split(".")[0] in {"cash_report", "main"}]
    assert not forbidden, (
        "the reference must not import the code it judges, found: "
        + ", ".join(forbidden)
    )

    # A mention in prose is fine; what matters is the real import graph.
    assert "reference.aggregate" not in path.read_text(encoding="utf-8")


def test_every_expected_figure_is_required_not_just_the_first(expected):
    """One right number must not carry three wrong ones into a pass."""
    question = runner.QUESTIONS[0]
    complete = correct_answer(expected)

    verdict = runner.judge(question, complete, expected)
    assert verdict["verdict"] == "pass", f"baseline must pass, got {verdict['missing']}"

    wrong = complete.replace(f"{expected['verified']['out']:,.0f}", "1")
    verdict = runner.judge(question, wrong, expected)

    assert verdict["verdict"] == "fail", (
        "one wrong figure must fail even when the others are right"
    )
    assert verdict["missing"], "the failing figure must be named"


def test_a_fluent_answer_with_a_wrong_figure_fails(expected):
    """Confident wording must not buy a pass."""
    question = runner.QUESTIONS[0]
    fluent = (
        "Berdasarkan pencatatan pada sheet TRANSAKSI periode Januari 2026, "
        "total uang masuk yang sudah terverifikasi adalah Rp1.000.000, "
        f"sedangkan uang keluar terverifikasi mencapai Rp{expected['verified']['out']:,.0f}, "
        f"dengan draft Rp{expected['draft']['out']:,.0f}."
    )
    verdict = runner.judge(question, fluent, expected)

    assert expected["verified"]["in"] != 1_000_000, "the fixture must not match by accident"
    assert verdict["verdict"] == "fail"


def test_a_short_correct_answer_passes(expected):
    """Brevity is not a fault: only the figures are judged."""
    question = runner.QUESTIONS[0]
    # Short and bare: four figures, no sentence structure, no explanation.
    short = (
        f"{expected['verified']['in']:,.0f} / {expected['draft']['in']:,.0f} / "
        f"{expected['verified']['out']:,.0f} / {expected['draft']['out']:,.0f}"
    )
    verdict = runner.judge(question, short, expected)

    assert verdict["verdict"] == "pass", f"figures were correct, missing: {verdict['missing']}"


def test_expense_ranking_ignores_income():
    """`largest expense` is ranked by money out, never by money out plus in.

    Built on a small ledger made here rather than on the real one, because on the
    real January data both rankings happen to agree: a category with big income
    is also the biggest spender. A guard that cannot tell the two rankings apart
    proves nothing, so this one forces them to disagree.
    """
    rows = [
        # Income far larger than spending. Ranking on out+in would put this first.
        ["2026-01-05 09:00:00", "BNI", 10_000_000, "", "Bagi Hasil", "masuk besar", "verified", "", "r1", "f1", ""],
        ["2026-01-06 09:00:00", "BNI", "", 100_000, "Bagi Hasil", "keluar kecil", "verified", "", "r2", "f2", ""],
        ["2026-01-07 09:00:00", "BNI", "", 900_000, "Bahan Baku", "keluar sedang", "verified", "", "r3", "f3", ""],
        ["2026-01-08 09:00:00", "BNI", "", 500_000, "Biaya-Ongkir", "keluar kecil", "verified", "", "r4", "f4", ""],
        ["2026-01-09 09:00:00", "BNI", "", 2_000_000, "Utang/Piutang", "keluar besar", "verified", "", "r5", "f5", ""],
        # Income on the biggest spending category too. Without it, a tool that
        # wrongly adds income to the expense figure would still print the right
        # number for the top three, and that bug would go unnoticed.
        ["2026-01-10 09:00:00", "BNI", 500_000, "", "Utang/Piutang", "pelunasan", "verified", "", "r6", "f6", ""],
    ]
    expected = runner.build_expectations(reference.read_rows(rows))

    order = [item["category"] for item in expected["top_expenses"]]
    assert order == ["Utang/Piutang", "Bahan Baku", "Biaya-Ongkir"], (
        f"ranked by money out, expected the spending order, got {order}"
    )
    assert "Bagi Hasil" not in order, (
        "a category that is large only because of its income is not a large expense"
    )
    assert expected["top_expenses"][0]["total"] == 2_000_000.0, (
        "the figure is money out only; adding the 500.000 income would make it 2.500.000"
    )


def test_an_answer_without_numbers_does_not_pass(expected):
    """A refusal or an apology is not an answer."""
    question = runner.QUESTIONS[0]
    for reply in ("Maaf, saya tidak bisa membantu.", "", "   "):
        verdict = runner.judge(question, reply, expected)
        assert verdict["verdict"] == "fail", f"must not pass on {reply!r}"


def test_a_zero_figure_need_not_be_written_as_a_digit(expected):
    """`tidak ada` is a correct statement of zero, not a missing figure."""
    question = runner.QUESTIONS[0]
    reply = (
        f"masuk verified Rp{expected['verified']['in']:,.0f}, "
        f"keluar verified Rp{expected['verified']['out']:,.0f}, "
        f"draft keluar Rp{expected['draft']['out']:,.0f}. Tidak ada uang masuk draft."
    )
    verdict = runner.judge(question, reply, expected)

    assert expected["draft"]["in"] == 0, "this test only means something when draft income is zero"
    assert verdict["verdict"] == "pass"


def _samples(first: str, rest: str) -> dict:
    """A sample file built here, so this guard never depends on a real run."""
    def sample(index: int, verdict: str) -> dict:
        return {
            "id": f"Q{index}",
            "question": f"pertanyaan {index}",
            "answer": "jawaban",
            "seconds": 1.0,
            "error": "",
            "verdict": verdict,
            "reason": "",
            "missing": [] if verdict == "pass" else ["verified_in"],
            "stated": [],
        }

    return {
        "model": "test",
        "period": "2026-01",
        "ledger_rows": 3,
        "reference": {
            "totals": {
                "verified": {"in": 1.0, "out": 2.0, "rows": 1},
                "draft": {"in": 0.0, "out": 0.0, "rows": 0},
                "transfer": {"in": 0.0, "rows": 0},
                "rows_in_period": 1,
                "period_start": "2026-01-01",
                "period_end_inclusive": "2026-01-31",
            },
            "top_expenses": [{"category": "x", "total": 1.0}],
        },
        "samples": [sample(1, first), sample(2, rest), sample(3, rest), sample(4, rest)],
    }


def test_the_verdict_needs_every_question_not_just_the_first(tmp_path):
    """Three right answers and one wrong one is not a pass."""
    (tmp_path / "sc08_samples.json").write_text(
        json.dumps(_samples("fail", "pass")), encoding="utf-8"
    )
    result = report.write_report(tmp_path)

    assert result["metrics"]["is_met"] is False, (
        "a failure in any answer must fail the criterion"
    )
    assert result["metrics"]["failed"] == 1
    assert result["metrics"]["passed"] == 3

    # And the reverse must hold, or the first assertion could pass for the wrong
    # reason: all four right must be met.
    (tmp_path / "sc08_samples.json").write_text(
        json.dumps(_samples("pass", "pass")), encoding="utf-8"
    )
    result = report.write_report(tmp_path)
    assert result["metrics"]["is_met"] is True
    assert result["metrics"]["failed"] == 0


def test_the_verdict_reads_every_sample_not_only_the_first(tmp_path):
    """A wrong answer in the last position must count too."""
    (tmp_path / "sc08_samples.json").write_text(
        json.dumps(_samples("pass", "pass")), encoding="utf-8"
    )
    data = json.loads((tmp_path / "sc08_samples.json").read_text(encoding="utf-8"))
    data["samples"][-1] = {**data["samples"][-1], "verdict": "fail", "missing": ["verified_in"]}
    (tmp_path / "sc08_samples.json").write_text(json.dumps(data), encoding="utf-8")

    result = report.write_report(tmp_path)
    assert result["metrics"]["is_met"] is False
    assert result["metrics"]["passed"] == 3
