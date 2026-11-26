"""Test ai_trace: no-op tanpa key/pytest, mapping usage, catat tidak melempar."""
import ai_trace


def test_tidak_aktif_di_bawah_pytest(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    assert ai_trace.aktif() is False  # guard pytest


def test_usage_dari_memetakan_token_openai():
    u = ai_trace.usage_dari({"usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}})
    assert u == {"input": 100, "output": 40, "total": 140, "unit": "TOKENS"}
    assert ai_trace.usage_dari({}) is None
    assert ai_trace.usage_dari(None) is None


def test_catat_tidak_melempar_meski_langfuse_belum_terpasang():
    # aktif() False di bawah pytest -> catat no-op murni
    ai_trace.catat("uji", model="m", input="x")
    with ai_trace.lacak("uji-ctx") as rekam:
        rekam(output="ok")
    # tidak ada exception = lulus
