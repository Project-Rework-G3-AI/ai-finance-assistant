"""Kode testing wajib berbahasa Inggris; prosa tetap bahasa Indonesia.

Aturan ini sudah diminta berulang kali dan dilanggar berulang kali, karena tidak
ada yang memaksanya. Test ini yang memaksa: nama fungsi, kelas, variabel, dan
argumen di `tests/` harus bahasa Inggris, sedangkan docstring dan komentar tetap
bahasa Indonesia.

Batasnya sengaja jelas:

- **Diperiksa**: identifier di direktori `tests/` saja. Kode produksi
  (`main.py`, `cash_report/`) tidak diperiksa dan tidak boleh diubah namanya
  hanya demi aturan ini.
- **Tidak diperiksa**: teks di dalam string dan komentar. Justru prosa Indonesia
  di sana yang diinginkan.
- **Kata ambigu diabaikan**: banyak kata Indonesia juga kata Inggris sah
  (`target`, `total`, `data`, `main`, `normal`, `dasar`). Kata seperti itu tidak
  dipakai menghukum, karena akan menghasilkan tuduhan palsu.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent

# Kata Indonesia yang TIDAK sekaligus kata Inggris yang lazim dipakai dalam kode.
# Daftar ini sengaja konservatif: lebih baik melewatkan satu pelanggaran daripada
# menuduh kode yang benar.
INDONESIAN_WORDS = frozenset("""
ada adalah agar akan akhir akun ambil angka antar arah atas awal
bagi bahan bangun baris baru bawah benar bentuk berasal beri berkas
berhasil besar bisa boleh buat bukan bulan cara cari catat cek cepat
coba cocok cukup daftar dalam dapat dari dengan depan
detik dibaca dibuat dikirim dilakukan diperlukan disebut dulu
gagal gambar ganti gunakan hasil harus hitung hubung ikut isi jadi
jalan jalankan jumlah juga kalau kami kamu kanan kata kecil kembali
kemudian kenapa kepala kerja kirim kolom kosong kunci lagi lain
lama langsung lanjut lapor lebih lembar lengkap lihat luar maka
maksimal mulai masuk mata maupun melalui memakai membuat memeriksa
mencatat mendapat mengisi menjadi menulis mereka meter milik minimal
minta modal muat mudah nama nilai namun nyata oleh pada paling
panjang pasang pasti perlu pertama pilih proses pulihkan putih
baca rekam rekaman ruang saat sama sampai sedang sedikit semua sendiri
senin setelah sesuai setiap simpan sisa soal sudah sumber susun
tabel tahap tahun tanpa tanya tawar telah tempat tengah tepi terakhir
terhadap tetapi tidak tinggi tipe tolong tulis tujuan tujuh untuk
ukur ukuran umum unik utama walau
waktu yakin yaitu yang
""".split())


def split_words(name: str) -> list[str]:
    """Pecah identifier menjadi kata: `install_fakes` -> [install, fakes]."""
    parts = re.split(r"[_\W]+", name)
    words: list[str] = []
    for part in parts:
        words += re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", part) or (
            [part] if part else [])
    return [w.lower() for w in words if w]


def indonesian_words_in(name: str) -> list[str]:
    """Kata Indonesia yang ditemukan di dalam sebuah identifier."""
    return sorted({w for w in split_words(name) if w in INDONESIAN_WORDS})


def identifiers_in(path: Path) -> dict[str, int]:
    """Semua nama yang didefinisikan atau disimpan di satu berkas, ke barisnya."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names = [node.id]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            names = [node.attr]
        for name in names:
            found.setdefault(name, getattr(node, "lineno", 0))
    return found


def test_there_are_test_files_to_check():
    """Penjaga: kalau glob-nya salah, seluruh pemeriksaan jadi hampa."""
    assert len(list(TESTS_DIR.glob("*.py"))) > 10


@pytest.mark.parametrize(
    "path", sorted(TESTS_DIR.glob("*.py")), ids=lambda p: p.name)
def test_identifiers_are_english(path: Path):
    """Nama fungsi, kelas, variabel, dan argumen wajib bahasa Inggris."""
    offenders = {
        name: indonesian_words_in(name)
        for name in identifiers_in(path)
        if indonesian_words_in(name)
    }
    assert not offenders, (
        f"{path.name} memakai identifier bahasa Indonesia: {offenders}. "
        "Ganti namanya ke bahasa Inggris; docstring dan komentar tetap "
        "bahasa Indonesia.")


def test_the_checker_catches_a_real_offence():
    """Penjaga: pemeriksa harus benar-benar bisa menangkap pelanggaran.

    Tanpa ini, daftar kata yang salah ketik akan membuat test di atas selalu
    lulus dan tidak menjaga apa pun.
    """
    assert indonesian_words_in("pasang_tiruan") == ["pasang", "tiruan"] or \
        indonesian_words_in("pasang_tiruan") == ["pasang"]
    assert indonesian_words_in("build_cases") == []
    assert indonesian_words_in("install_fakes") == []


def test_ambiguous_words_are_not_punished():
    """Kata yang sah dalam dua bahasa tidak boleh dianggap pelanggaran."""
    for name in ("target", "total", "data", "main_cli", "normal", "test_pass"):
        assert indonesian_words_in(name) == [], name


def test_prose_may_stay_indonesian():
    """Aturan ini soal identifier, bukan dokumentasi.

    Docstring berbahasa Indonesia adalah keharusan, jadi tidak boleh ikut
    dianggap pelanggaran. Test ini mengunci niat itu supaya seseorang tidak
    "memperbaiki" prosa menjadi bahasa Inggris demi meluluskan pemeriksaan.
    """
    source_text = (TESTS_DIR / "sc05_dedupe.py").read_text(encoding="utf-8")
    assert "berapa baris yang tersimpan" in source_text or \
        "yang diukur" in source_text.lower()
