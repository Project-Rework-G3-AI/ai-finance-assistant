"""Integrasi Sentry: error, tracing, dan log terpusat.

Dipisah dari main.py supaya konfigurasi observability tidak tercampur logika bot
dan bisa diuji sendiri.

Prinsip:
  - Tanpa SENTRY_DSN, semua fungsi di sini jadi no-op. Bot tetap jalan seperti
    biasa di lokal tanpa akun Sentry.
  - Aplikasi ini memproses bukti transaksi keuangan dan menyimpan kredensial di
    environment, jadi data sensitif disamarkan sebelum keluar dari server.
"""

from __future__ import annotations

import logging
import os
import re
import sys

import sentry_sdk

log = logging.getLogger(__name__)

# Nilai yang tidak boleh keluar dari server. Dicocokkan berdasarkan nama variabel
# atau nama header, lalu nilainya diganti [REDACTED].
_POLA_RAHASIA = re.compile(
    r"(TELEGRAM_BOT_TOKEN|AI_API_KEY|GOOGLE_OAUTH[A-Z_]*|OAUTH_REFRESH_TOKEN|"
    r"refresh_token|client_secret|client_id|Authorization|SENTRY_DSN)"
    r"([\"'=:\s]+)"
    r"(?:Bearer\s+|Basic\s+)?"
    r"(\S+?)"
    r"(?=[\"'\s]|$)",
    re.I,
)

# Token bot Telegram juga muncul di dalam URL, bukan sebagai "NAMA=nilai":
# https://api.telegram.org/bot<id>:<rahasia>/getFile. httpx menyertakan URL ini
# di pesan exception, jadi tanpa pola khusus tokennya ikut terkirim ke Sentry.
_POLA_TG_URL = re.compile(r"(/bot)(\d+:[A-Za-z0-9_-]{30,})")

# Kredensial juga bisa muncul sebagai parameter URL (?api_key=..., &token=...).
# Ini sering terjadi pada pesan error httpx yang menyertakan URL lengkap.
_POLA_QUERY = re.compile(
    r"([?&](?:api[_-]?key|token|access[_-]?token|refresh[_-]?token|"
    r"key|secret|client[_-]?secret|password)=)([^&\s\"']+)",
    re.I,
)

# Kunci dict yang nilainya selalu disamarkan, sedangkan kuncinya dipertahankan
# agar struktur data di Sentry tetap terbaca saat debugging.
_KUNCI_RAHASIA = {
    "refresh_token", "access_token", "client_secret", "client_id",
    "authorization", "api_key", "token", "password", "secret",
    "telegram_bot_token", "ai_api_key", "sentry_dsn",
}

_BATAS_KEDALAMAN = 12


def samarkan(obj, _depth: int = 0):
    """Ganti nilai sensitif dengan [REDACTED] secara rekursif.

    Menangani dua bentuk kebocoran: pola "NAMA=nilai" di dalam teks (mis. pesan
    exception yang menyertakan URL berisi token), dan nilai pada dict dengan kunci
    sensitif (mis. variabel lokal di stack trace).
    """
    if _depth > _BATAS_KEDALAMAN:
        return obj
    if isinstance(obj, dict):
        hasil = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in _KUNCI_RAHASIA:
                hasil[k] = "[REDACTED]" if v else v
            else:
                hasil[k] = samarkan(v, _depth + 1)
        return hasil
    if isinstance(obj, (list, tuple)):
        return [samarkan(v, _depth + 1) for v in obj]
    if isinstance(obj, str):
        teks = _POLA_RAHASIA.sub(
            lambda m: m.group(1) + m.group(2) + "[REDACTED]", obj
        )
        teks = _POLA_TG_URL.sub(lambda m: m.group(1) + "[REDACTED]", teks)
        return _POLA_QUERY.sub(lambda m: m.group(1) + "[REDACTED]", teks)
    return obj


def before_send(event, hint):
    """Bersihkan event sebelum dikirim ke Sentry."""
    return samarkan(event)


def before_send_transaction(event, hint):
    """Bersihkan transaksi (tracing) sebelum dikirim ke Sentry."""
    return samarkan(event)


def _env_float(nama: str, bawaan: float) -> float:
    try:
        return float(os.getenv(nama, "") or bawaan)
    except ValueError:
        log.warning("Nilai %s bukan angka, memakai bawaan %s", nama, bawaan)
        return bawaan


def init_sentry() -> bool:
    """Pasang Sentry. Return True bila aktif, False bila DSN tidak diisi.

    Harus dipanggil sebelum FastAPI dibuat agar integrasi Starlette/FastAPI
    menempel pada app.
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        log.info("SENTRY_DSN kosong — Sentry tidak aktif (bot tetap berjalan)")
        return False

    if "pytest" in sys.modules:
        # Run pytest sengaja memunculkan exception (fixture jalur gagal
        # pending, dll.) — mengirimnya ke Sentry hanya menghasilkan noise
        # yang membuka-ulang issue yang sudah di-resolve. capture_exception
        # tanpa init aman jadi no-op.
        log.info("Sentry dilewati — berjalan di bawah pytest")
        return False

    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=dsn,
        # Default mengikuti Sentry: bila tidak diisi, event dianggap production.
        # Ini pilihan yang aman — lupa mengisi di server tidak membuat error
        # produksi tersamar sebagai development dan lolos dari filter dashboard.
        # Untuk lokal, set SENTRY_ENVIRONMENT=development di .env.
        environment=os.getenv("SENTRY_ENVIRONMENT", "production").strip(),
        release=os.getenv("SENTRY_RELEASE", "").strip() or None,
        # Persentase request yang direkam untuk tracing. 0 mematikan tracing.
        traces_sample_rate=_env_float("SENTRY_TRACES_SAMPLE_RATE", 0.1),
        # Data pribadi tidak dikirim: aplikasi ini memproses bukti transaksi.
        send_default_pii=False,
        # Body request tidak pernah direkam: isinya gambar bukti transaksi.
        max_request_body_size="never",
        # Variabel lokal TIDAK ikut dikirim. Ini penting: argumen fungsi ikut
        # tersimpan sebagai variabel lokal, sehingga byte gambar bukti transaksi
        # (dan isi dict transaksi) akan bocor lewat stack trace. Diverifikasi:
        # dengan opsi ini False, penanda gambar tidak lagi muncul di payload,
        # sedangkan nama file, nomor baris, dan pesan exception tetap utuh.
        include_local_variables=False,
        before_send=before_send,
        before_send_transaction=before_send_transaction,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            # level=INFO  -> log INFO ke atas dikirim sebagai breadcrumb
            # event_level=ERROR -> log ERROR ke atas menjadi issue tersendiri
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    log.info(
        "Sentry aktif — environment=%s release=%s traces=%s",
        os.getenv("SENTRY_ENVIRONMENT", "production").strip(),
        os.getenv("SENTRY_RELEASE", "") or "(tidak diisi)",
        _env_float("SENTRY_TRACES_SAMPLE_RATE", 0.1),
    )
    return True


def capture_exception(exc: BaseException) -> None:
    """Laporkan exception yang ditangani sendiri agar tetap terlihat di Sentry.

    Banyak jalur di bot ini menangani error agar alur tetap jalan (fallback AI,
    retry antrean, loop Telegram). Tanpa panggilan ini, kegagalan tersebut tidak
    pernah muncul di Sentry.
    """
    sentry_sdk.capture_exception(exc)


def setup_logging() -> None:
    """Logging terstruktur ke stdout, format ringkas dengan timestamp.

    Menggantikan print(). Uvicorn memakai konfigurasi logging-nya sendiri, jadi
    handler di sini hanya dipasang bila root logger belum punya handler.
    """
    level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
