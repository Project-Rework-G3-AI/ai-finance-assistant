"""Pelacakan panggilan LLM ke Langfuse Cloud (opsional) — Python SDK v5.

Dua env wajib: LANGFUSE_PUBLIC_KEY & LANGFUSE_SECRET_KEY. LANGFUSE_BASE_URL
hanya perlu bila region bukan EU default. Kosong = tidak aktif, nol dampak
runtime. Di bawah pytest juga tidak aktif — exception test sengaja dibuat
dan tidak boleh mengirim event (prinsip sama dengan guard Sentry).

SDK v5 berbasis OpenTelemetry dan memakai endpoint ingestion v4 — SDK v2
lama memakai /api/public/ingestion yang sudah tidak diterima Langfuse Cloud
(berhenti 16 Nov 2026), itulah sebabnya trace tak pernah muncul.

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
    """Singleton klien (get_client membaca env LANGFUSE_* otomatis)."""
    global _client
    if _client is None:
        from langfuse import get_client

        _client = get_client()
    return _client


def diagnosa() -> str:
    """Cek koneksi & kredensial — untuk verifikasi cepat di lokal/Render.

    Jalankan: python -c "import ai_trace; print(ai_trace.diagnosa())"
    """
    if not aktif():
        return (
            "off — LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY kosong "
            "(atau sedang di bawah pytest)"
        )
    try:
        ok = _pasang().auth_check()
        return "ok — kredensial valid" if ok else "gagal — kredensial ditolak"
    except Exception as e:  # noqa: BLE001
        return f"gagal — {type(e).__name__}: {e}"


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
        if error:
            meta["error"] = True
        with lf.start_as_current_observation(
            as_type="generation", name=nama, model=model
        ) as gen:
            gen.update(input=input, output=(output if output is not None else None),
                       metadata=meta, usage=usage)
            if error:
                gen.update(output={"error": error[:500]})
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

    Sukses maupun gagal tercatat; exception tetap diteruskan setelah dicatat.
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
