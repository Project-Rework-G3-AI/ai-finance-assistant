"""Pelacakan panggilan LLM ke Langfuse Cloud (opsional).

Dua env wajib: LANGFUSE_PUBLIC_KEY & LANGFUSE_SECRET_KEY (LANGFUSE_HOST
opsional, default cloud). Kosong = tidak aktif, nol dampak runtime.
Di bawah pytest juga tidak aktif — exception test sengaja dibuat dan
tidak boleh mengirim event (prinsip sama dengan guard Sentry).

Yang dikirim HANYA teks: prompt, output JSON, usage, metadata ringkas
(nama file, nomor halaman). Gambar/kredensial tidak pernah dikirim.
"""

import logging
import os
import sys
import time
from contextlib import contextmanager

log = logging.getLogger(__name__)

_client = None


def aktif() -> bool:
    """Langfuse aktif hanya bila kedua key terisi dan bukan saat pytest."""
    return (
        bool(os.getenv("LANGFUSE_PUBLIC_KEY", "").strip())
        and bool(os.getenv("LANGFUSE_SECRET_KEY", "").strip())
        and "pytest" not in sys.modules
    )


def _pasang():
    """Singleton klien Langfuse (membaca env LANGFUSE_* sendiri)."""
    global _client
    if _client is None:
        from langfuse import Langfuse

        _client = Langfuse()
    return _client


def usage_dari(data: dict) -> dict | None:
    """Ambil usage dari respons chat/completions (format OpenAI)."""
    u = (data or {}).get("usage") or {}
    if not u:
        return None
    masuk = u.get("prompt_tokens") or 0
    keluar = u.get("completion_tokens") or 0
    return {
        "input": masuk,
        "output": keluar,
        "total": u.get("total_tokens", masuk + keluar),
        "unit": "TOKENS",
    }


def catat(
    nama: str,
    *,
    model: str | None = None,
    input=None,
    output=None,
    usage: dict | None = None,
    metadata: dict | None = None,
    error: str | None = None,
    latensi_ms: int | None = None,
) -> None:
    """Catat satu panggilan LLM. Tidak pernah melempar — observability
    tidak boleh mengganggu alur bot."""
    if not aktif():
        return
    try:
        lf = _pasang()
        meta = dict(metadata or {})
        if latensi_ms is not None:
            meta["latensi_ms"] = latensi_ms
        trace = lf.trace(name=nama, metadata=meta)
        kwargs = {"name": nama, "model": model, "input": input, "metadata": meta}
        if output is not None:
            kwargs["output"] = output
        if usage:
            kwargs["usage"] = usage
        if error:
            kwargs["level"] = "ERROR"
            kwargs["status_message"] = error[:500]
        trace.generation(**kwargs)
        lf.flush()
    except Exception as e:  # noqa: BLE001 — observability gagal = diam
        log.warning("Langfuse catat gagal: %s: %s", type(e).__name__, e)


@contextmanager
def lacak(nama: str, *, model: str | None = None, input=None, metadata: dict | None = None):
    """Bungkus satu panggilan LLM:

        with ai_trace.lacak("vision-extract", model=m, input=prompt) as rekam:
            r = await client.post(...)
            data = r.json()
            rekam(output=..., usage=ai_trace.usage_dari(data))

    Sukses maupun gagal tercatat (gagal: level ERROR); exception tetap
    diteruskan setelah dicatat.
    """
    t0 = time.perf_counter()
    wadah = {"output": None, "usage": None, "error": None}

    def rekam(output=None, usage=None):
        wadah["output"] = output
        wadah["usage"] = usage

    try:
        yield rekam
    except Exception as e:
        wadah["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        catat(
            nama,
            model=model,
            input=input,
            output=wadah["output"],
            usage=wadah["usage"],
            metadata=metadata,
            error=wadah["error"],
            latensi_ms=int((time.perf_counter() - t0) * 1000),
        )
