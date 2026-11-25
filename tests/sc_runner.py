"""Runner SC-01: jalankan model asli pada dataset berlabel, simpan hasil per baris.

Alur yang diuji sengaja dipersempit ke satu hal: gambar -> kategori. Karena itu
hanya `main.extract` yang dijalankan apa adanya, sedangkan penulisan ke Google
Sheets/Drive tidak dipanggil sama sekali. Dengan begitu spreadsheet perusahaan
tidak tersentuh dan hasil bisa diulang.

Hasil ditulis bertahap ke CSV setelah setiap gambar selesai diproses. Ini bukan
gaya berlebihan: run pertama di sesi sebelumnya sempat mati setelah puluhan
panggilan API berbayar, dan yang menyelamatkan hasilnya hanya karena CSV sudah
terlanjur ditulis.

Pemakaian:

    # 1. unduh gambar dataset (sekali saja)
    python3 tests/sc_runner.py --download

    # 2. jalankan evaluasi (butuh AI_API_KEY)
    python3 tests/sc_runner.py

    # 3. hitung ulang metrik dari CSV yang sudah ada (tanpa memanggil AI)
    python3 tests/sc_runner.py --metrics-only

Lokasi dataset diatur di `.env` lewat SC_PAIRS dan SC_IMAGES.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import datetime
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc_common as cfg  # noqa: E402

cfg.load_env()

import httpx  # noqa: E402

from sc_metrics import compute  # noqa: E402
import sc02_completeness  # noqa: E402

OUTPUT_COLUMNS = [
    "file", "reference_category", "proposed_category", "match",
    "reference_amount", "proposed_amount", "amount_diff",
    "reference_date", "proposed_date",
    "proposed_bank", "proposed_direction", "proposed_note",
    "mode", "note", "model_note", "seconds",
]


def read_results(path: Path) -> dict[str, dict]:
    """Hasil yang sudah ada, dipakai untuk melanjutkan run yang terputus."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {(r.get("file") or "").strip(): r for r in csv.DictReader(f)}


def read_source(out: Path) -> dict:
    """Keterangan asal angka pada `out` (kapan dihitung, berapa panggilan model)."""
    path = out / "source.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_source(out: Path, **fields) -> dict:
    """Simpan keterangan asal angka, digabung dengan yang sudah ada.

    Dipisah dari CSV karena CSV hanya berisi hasil per gambar. Tanpa berkas
    ini, laporan lama tidak bisa membedakan "dihitung baru" dari "dibaca ulang
    dari run kemarin", sehingga angka lama bisa dikutip sebagai hasil baru.
    """
    data = read_source(out)
    data.update(fields)
    (out / "source.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def source_line(out: Path) -> str:
    """Satu baris ringkas tentang asal angka, untuk kepala laporan."""
    s = read_source(out)
    if not s:
        return "Sumber data: tidak tercatat (laporan dibuat tanpa source.json)"
    computed = s.get("computed_at") or "tidak diketahui"
    calls = s.get("model_calls")
    if calls == 0:
        return (f"Sumber data: hasil run sebelumnya, dihitung {computed}. "
                f"Tidak ada panggilan model saat laporan ini dibuat.")
    if calls:
        return (f"Sumber data: dihitung {computed} dengan {calls} panggilan model "
                f"({s.get('model', 'model tidak tercatat')}).")
    return f"Sumber data: dihitung {computed}."


def verdict_block(judged_label: str, judged_value: float, target: float,
                  alternatives: list[tuple[str, float, str]]) -> list[str]:
    """Blok yang menyebut angka mana yang dibandingkan dengan target.

    Kedua kriteria sama-sama menampilkan beberapa angka sekaligus. Tanpa blok
    ini, baris "Status: BELUM TERCAPAI" tidak menjelaskan angka mana yang
    dibandingkan, sehingga pembaca harus menebak dan bisa menyimpulkan laporan
    yang salah. Dipakai SC-01 dan SC-02 dari satu tempat supaya tidak bisa
    berbeda lagi.
    """
    verdict = "TERCAPAI" if judged_value >= target else "BELUM TERCAPAI"
    lines = [
        f"Target BRD         : minimal {target:.0%}",
        f"Angka yang dinilai : {judged_label} {judged_value:.1%}  <- dibandingkan dengan target",
        f"Status             : {verdict}",
        "",
        "Angka lain (tidak dipakai menilai target)",
        "-" * 60,
    ]
    for label, value, reason in alternatives:
        lines.append(f"  {label:31}: {value:.1%}  {reason}")
    return lines


MODEL_COLUMNS = [
    "proposed_category", "proposed_amount", "proposed_date",
    "proposed_bank", "proposed_direction", "proposed_note",
]


def describe_reuse(done: dict, remaining: list) -> str:
    """Penjelasan saat hasil lama dipakai lagi.

    Sebelumnya pesannya hanya satu baris "melanjutkan: N sudah ada, N tersisa"
    di antara keluaran lain. Akibatnya run yang tidak memanggil model sama
    sekali terlihat seperti run yang selesai seketika, dan pembaca wajar
    mengira modelnya menjadi jauh lebih cepat. Padahal tidak ada satu pun
    panggilan model: hasil dari run sebelumnya dibaca ulang dari CSV.
    """
    total = len(done) + len(remaining)
    if remaining:
        headline = "SEBAGIAN HASIL LAMA DIPAKAI LAGI"
    else:
        headline = "HASIL LAMA DIPAKAI LAGI — TIDAK ADA PEMANGGILAN MODEL BARU"
    lines = [
        "",
        "=" * 60,
        headline,
        "=" * 60,
        f"  sudah ada di CSV : {len(done)} dari {total} gambar",
        f"  akan diproses    : {len(remaining)} gambar",
    ]
    if not remaining:
        lines.append("  panggilan model  : 0 — angka di bawah adalah hasil run sebelumnya")
        lines.append("")
        lines.append("  Untuk benar-benar menghitung ulang, pakai --restart.")
        lines.append("  Untuk sekadar melihat angka tanpa AI, pakai --metrics-only.")
    lines.append("=" * 60)
    return "\n".join(lines)


def stale_files(done: dict, pairs: list[dict]) -> list[str]:
    """Berkas di CSV lama yang tidak ada di daftar pasangan sekarang.

    Hasil yang tersimpan diikat ke satu set pasangan. Kalau CSV dibuat dengan
    pasangan lain, angkanya tidak sah untuk set sekarang, jadi lebih baik
    berhenti dengan jelas daripada diam-diam melaporkan angka yang salah.
    """
    wanted = {(p.get("file") or "").strip() for p in pairs}
    return sorted(name for name in done if name not in wanted)


async def run_pairs(pairs: list[dict], images_dir: Path, out: Path,
                    restart: bool = False) -> list[dict]:
    import main  # diimpor di dalam agar `--download` tidak butuh AI_API_KEY

    done = {} if restart else read_results(out)
    results = list(done.values())

    if done:
        extra = stale_files(done, pairs)
        if extra:
            raise SystemExit(
                f"hasil di {out} dibuat dengan pasangan berbeda: "
                f"{len(extra)} berkas tidak ada di daftar sekarang "
                f"(contoh: {extra[0]}).\n"
                f"Hapus berkas itu, atau jalankan dengan --restart."
            )

    remaining = [p for p in pairs if (p.get("file") or "").strip() not in done]
    if done:
        print(describe_reuse(done, remaining))
    if not remaining:
        # Tidak ada panggilan model sama sekali: catat sebagai 0, bukan
        # dibiarkan dari run sebelumnya yang mungkin berisi angka lain.
        write_source(out.parent, model_calls=0)
        return results

    if not main.AI_KEY:
        raise SystemExit(
            "AI_API_KEY kosong. SC-01 mengukur akurasi model, jadi tidak bisa "
            "dijalankan dalam mode mock."
        )
    print(f"model: {main.AI_MODEL} via {main.AI_BASE}")
    print(f"gambar: {images_dir}\nkeluaran: {out}\n")

    # Tulis header lebih dulu agar file tetap valid walau proses mati di tengah.
    write_header = not out.exists()
    f = open(out, "a", encoding="utf-8", newline="")
    w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
    if write_header:
        w.writeheader()
        f.flush()

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i, p in enumerate(remaining, 1):
            name = (p.get("file") or "").strip()
            image_path = images_dir / name
            if not image_path.exists():
                print(f"[{i}/{len(remaining)}] LEWATI {name}: file tidak ada")
                continue

            image_bytes = image_path.read_bytes()
            started = time.monotonic()
            try:
                rec = cfg.normalize_extract(
                    await main.extract(client, name, image_bytes, ""))
                error = ""
            except Exception as e:
                rec = {"category": "", "amount": None, "date": "",
                       "mode": "error", "note": "", "remark": ""}
                error = f"{type(e).__name__}: {e}"
            elapsed = time.monotonic() - started

            proposed = str(rec.get("category") or "").strip()
            reference = (p.get("reference_category") or "").strip()
            row = {
                "file": name,
                "reference_category": reference,
                "proposed_category": proposed,
                "match": "ya" if proposed == reference else "tidak",
                "reference_amount": (p.get("reference_amount") or "").strip(),
                "proposed_amount": rec.get("amount"),
                "amount_diff": _amount_diff(p.get("reference_amount"), rec.get("amount")),
                "reference_date": (p.get("reference_date") or "").strip(),
                "proposed_date": rec.get("date") or "",
                "proposed_bank": rec.get("bank") or "",
                "proposed_direction": rec.get("direction") or "",
                "proposed_note": rec.get("note") or "",
                "mode": rec.get("mode") or ("error" if error else ""),
                "note": (rec.get("remark") or error)[:300],
                "model_note": (rec.get("note") or "")[:200],
                "seconds": round(elapsed, 2),
            }
            w.writerow(row)
            f.flush()
            os.fsync(f.fileno())
            results.append(row)

            mark = "OK " if row["match"] == "ya" else "SALAH"
            print(f"[{i}/{len(remaining)}] {mark} {name[:38]:40} "
                  f"{proposed[:34]:36} ({elapsed:.1f}s)")

    f.close()

    # Dicatat supaya laporan bisa menyebut asal angkanya. Tanpa ini, laporan
    # dari run lama tidak bisa dibedakan dari laporan yang baru dihitung.
    write_source(out.parent,
                 computed_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
                 model_calls=len(remaining),
                 model=main.AI_MODEL,
                 reused=len(done))
    return results


def _amount_diff(reference, proposed) -> str:
    try:
        return str(int(float(reference)) - int(float(proposed)))
    except (TypeError, ValueError):
        return ""


def write_sc01_report(results: list[dict], out: Path) -> dict:
    """Hitung metrik SC-01 lalu tulis `sc01_report.txt` dan `sc01_metrics.json`."""
    pairs = [{"reference_category": r["reference_category"],
              "proposed_category": r["proposed_category"],
              "file": r["file"]} for r in results if r.get("reference_category")]
    m = compute(pairs)

    lines = [
        "SC-01 — Akurasi usulan kategori",
        "=" * 60,
        source_line(out),
        "",
        m.summary(),
        "",
    ]
    # Status memakai akurasi (benar/total), bukan baseline atau macro-average.
    # Keduanya ikut ditampilkan, jadi harus disebut mana yang dinilai.
    lines += verdict_block(
        "akurasi", m.accuracy, 0.85,
        [
            ("baseline kelas mayoritas", m.baseline,
             f"batas bawah; model harus melampauinya ({m.majority_label})"),
            ("macro-average recall", m.macro_avg,
             "bobot sama per kategori, tidak dipakai menilai target"),
        ],
    )
    lines += [
        "",
        "Per kategori (diurutkan dari yang paling sering muncul)",
        "-" * 60,
        f"{'kategori':46} {'acuan':>5} {'benar':>5} {'recall':>7}",
    ]
    for label, d in sorted(m.per_category.items(), key=lambda kv: -kv[1]["reference"]):
        lines.append(f"{label[:46]:46} {d['reference']:5} {d['correct']:5} "
                     f"{d['recall']:6.0%}")

    lines += ["", "Confusion matrix (baris = acuan, kolom = usulan)", "-" * 60]
    for a in m.confusion:
        row = ", ".join(f"{u}={n}" for u, n in
                        sorted(m.confusion[a].items(), key=lambda kv: -kv[1]))
        lines.append(f"{a[:44]:46} -> {row}")

    if m.wrong:
        lines += ["", f"Baris yang salah ({len(m.wrong)})", "-" * 60]
        for s in m.wrong:
            lines.append(f"{s['file'][:44]:46} {s['reference'][:26]:28} -> {s['proposed'][:28]}")

    text = "\n".join(lines)
    (out / "sc01_report.txt").write_text(text, encoding="utf-8")
    (out / "sc01_metrics.json").write_text(
        json.dumps({
            "total": m.total, "correct": m.correct, "accuracy": m.accuracy,
            "baseline": m.baseline, "majority_label": m.majority_label,
            "lift": m.lift, "macro_avg": m.macro_avg,
            "per_category": m.per_category, "confusion": m.confusion,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"metrics": m, "text": text}



def build_sc02_rows(results: list[dict]) -> list[dict]:
    """Ubah hasil per baris menjadi masukan SC-02.

    Acuan diambil dari `sc_pairs.csv` bila tersedia, supaya "terbaca" bisa
    dibedakan dari "terbaca benar". Tanpa acuan, hanya keterbacaan yang dinilai.
    """
    reference_by_file = {}
    try:
        for p in cfg.read_pairs(cfg.pairs_file()):
            name = (p.get("file") or "").strip()
            if name:
                reference_by_file[name] = {
                    "date": p.get("reference_date") or "",
                    "amount": p.get("reference_amount") or "",
                    "bank": p.get("bank") or "",
                    # Arah tidak punya kolom acuan di dataset. Dibandingkan hanya
                    # bila kelak ditambahkan, bukan ditebak sekarang.
                    "direction": p.get("reference_direction") or "",
                    "category": p.get("reference_category") or "",
                }
    except SystemExit:
        reference_by_file = {}

    rows = []
    for r in results:
        name = (r.get("file") or "").strip()
        record = {
            "date": r.get("proposed_date") or "",
            "amount": r.get("proposed_amount") or "",
            "bank": r.get("proposed_bank") or "",
            "direction": r.get("proposed_direction") or "",
            "category": r.get("proposed_category") or "",
            "note": r.get("proposed_note") or "",
            # `catatan` di main.py ditulis ke kolom `note` pada CSV hasil.
            "remark": r.get("note") or "",
            "mode": r.get("mode") or "",
        }
        # Acuan yang sudah menempel di baris hasil dipakai lebih dulu. Tanpa
        # ini, fungsi ini hanya bisa bekerja bila file pasangan ada di disk,
        # sehingga tidak bisa diuji dan diam-diam menilai tanpa acuan.
        reference = r.get("reference") or reference_by_file.get(name)
        rows.append({"file": name, "record": record,
                     "reference": reference})
    return rows


def write_sc03_report(results: list[dict], out: Path) -> dict:
    """Laporkan SC-03 dari sampel waktu yang sudah diukur.

    Berbeda dari SC-01 dan SC-02, SC-03 **tidak bisa dihitung** dari hasil
    ekstraksi: waktu tidak tersimpan di CSV hasil. Fungsi ini hanya membaca
    `sc03_samples.csv` yang ditulis oleh harness pengukur, lalu merangkumnya.
    Kalau berkas itu belum ada, laporkan apa adanya alih-alih mengarang angka.
    """
    import sc03_latency as sc03

    path = out / "sc03_samples.csv"
    if not path.exists():
        text = (
            "SC-03 — Waktu proses sampai tersimpan\n"
            + "=" * 60 + "\n"
            "Status             : BELUM DIUKUR\n\n"
            "Waktu tidak bisa dihitung ulang dari hasil ekstraksi, berbeda dari\n"
            "SC-01 dan SC-02. Jalankan pengukuran lebih dulu:\n\n"
            "  python3 tests/_sc03_run.py\n"
        )
        (out / "sc03_report.txt").write_text(text, encoding="utf-8")
        return {"result": None, "text": text}

    samples = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = sc03.Sample(file=r["file"], ok=(r.get("ok") == "True"),
                            error=r.get("error", ""))
            for name in sc03.STAGES:
                try:
                    s.stages[name] = float(r.get(name) or 0)
                except ValueError:
                    s.stages[name] = 0.0
            samples.append(s)

    # Harness pengukur me-mock Telegram, jadi tahap reply tidak diukur sungguhan.
    c = sc03.compute(samples, reply_measured=False)
    text = sc03.report(
        c, "Sumber data: diukur langsung pada rantai produksi, folder penyimpanan sandbox.")
    (out / "sc03_report.txt").write_text(text, encoding="utf-8")
    (out / "sc03_metrics.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"result": c, "text": text}


def write_sc05_report(results: list[dict], out: Path) -> dict:
    """Jalankan SC-05 dan tulis laporannya.

    Berbeda dari SC-01 sampai SC-04, kriteria ini **tidak butuh apa pun** dari
    luar: tanpa kunci AI, tanpa Google, tanpa dataset, tanpa jaringan. Karena itu
    ia dijalankan langsung di sini, bukan menunggu sampel dari harness terpisah.
    """
    import asyncio

    import sc05_dedupe as sc05

    try:
        import main as app
    except Exception as e:  # noqa: BLE001
        text = ("SC-05 — Bukti transaksi berulang tidak mencatat ganda\n"
                + "=" * 60 + "\n"
                "Status             : BELUM DIUKUR\n\n"
                f"Modul aplikasi tidak bisa dimuat: {type(e).__name__}: {e}\n")
        (out / "sc05_report.txt").write_text(text, encoding="utf-8")
        return {"result": None, "text": text}

    cases = asyncio.run(sc05.measure(app, 5))
    c = sc05.compute(cases)
    text = sc05.report(
        c, "Sumber data: `handle_update` dan `write_cash_report` dari main.py "
           "dipanggil apa adanya; Telegram, Google Sheets, dan ekstraksi AI "
           "diganti tiruan. Yang dinilai adalah logika dedup yang sebenarnya.")
    (out / "sc05_report.txt").write_text(text, encoding="utf-8")
    (out / "sc05_metrics.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"result": c, "text": text}


def write_sc04_report(results: list[dict], out: Path) -> dict:
    """Laporkan SC-04 dari token yang sudah direkam.

    Seperti SC-03, SC-04 tidak bisa dihitung dari hasil ekstraksi: jumlah token
    tidak tersimpan di sana. Yang dibaca adalah `sc04_samples.csv` berisi token
    per gambar, lalu **biaya diturunkan** dari tarif dan kurs yang berlaku saat
    ini. Biaya tidak pernah dibaca dari berkas, supaya menyesuaikan tarif atau
    kurs selalu berefek pada laporan.
    """
    import sc04_cost as sc04

    path = out / "sc04_samples.csv"
    if not path.exists():
        text = (
            "SC-04 — Biaya per gambar\n"
            + "=" * 60 + "\n"
            "Status             : BELUM DIUKUR\n\n"
            "Jumlah token tidak tersimpan di hasil ekstraksi, jadi biaya tidak\n"
            "bisa dihitung ulang dari sana. Jalankan pengukuran lebih dulu:\n\n"
            "  python3 tests/_sc04_run.py --usd-idr <kurs>\n"
        )
        (out / "sc04_report.txt").write_text(text, encoding="utf-8")
        return {"result": None, "text": text}

    # Tarif dan kurs: env/kode, bukan ditebak.
    price = sc04.pricing_from()
    exchange_rate = sc04.usd_to_idr_from()
    if not exchange_rate:
        text = ("SC-04 — Biaya per gambar\n" + "=" * 60 + "\n"
                "Status             : BELUM DIUKUR\n\n"
                f"Kurs belum diisi. Isi {sc04.ENV_USD_IDR} atau variabel "
                "USD_TO_IDR di tests/sc04_cost.py.\n")
        (out / "sc04_report.txt").write_text(text, encoding="utf-8")
        return {"result": None, "text": text}

    samples = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            samples.append(sc04.Sample(
                file=r["file"], ok=(r.get("ok") == "True"),
                error=r.get("error", ""),
                prompt_tokens=int(r.get("prompt_tokens") or 0),
                completion_tokens=int(r.get("completion_tokens") or 0)))

    c = sc04.compute(samples, target=sc04.target_from(), pricing=price,
                     usd_to_idr=exchange_rate)
    text = sc04.report(c, "Sumber data: token dibaca dari respons penyedia "
                          "saat pengukuran; biaya diturunkan dari tarif dan kurs "
                          "yang berlaku sekarang.")
    (out / "sc04_report.txt").write_text(text, encoding="utf-8")
    (out / "sc04_metrics.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"result": c, "text": text}


def write_sc02_report(results: list[dict], out: Path) -> dict:
    """Hitung SC-02 lalu tulis `sc02_report.txt` dan `sc02_metrics.json`."""
    rows = build_sc02_rows(results)
    c = sc02_completeness.compute(rows)

    target = 0.90
    judged = c.overall_accuracy
    without_category = c.accuracy_excluding("category")
    lines = [
        "SC-02 — Kelengkapan field wajib",
        "=" * 60,
        source_line(out),
        "",
        c.summary(),
        "",
    ]
    # Sama seperti SC-01: beberapa angka ditampilkan, jadi angka yang dinilai
    # harus disebut. Penyebutnya juga disebut, supaya 72,5% tidak disangka
    # rata-rata kelima field padahal hanya yang beracuan.
    lines += verdict_block(
        f"kecocokan rata-rata ({c.scored_count} field beracuan)", judged, target,
        [
            ("kelengkapan rata-rata", c.overall_completeness,
             "field terbaca, belum tentu benar"),
            ("kecocokan tanpa kategori", without_category,
             "kategori sudah diukur di SC-01"),
        ],
    )
    lines += [
        "",
        "Catatan penilaian",
        "-" * 60,
        "kelengkapan = field terbaca, tanpa penanda gagal baca dan bukan mode mock",
        "akurasi     = terbaca dan nilainya cocok dengan acuan (bila acuan ada)",
        "tebakan     = field yang diisi nilai bawaan kode karena model gagal membaca",
        "field tanpa acuan di dataset tidak ikut dirata-rata",
    ]
    text = "\n".join(lines)
    (out / "sc02_report.txt").write_text(text, encoding="utf-8")
    (out / "sc02_metrics.json").write_text(
        json.dumps({
            "total": c.total,
            "overall_completeness": c.overall_completeness,
            "overall_accuracy": c.overall_accuracy,
            "all_fields_complete": c.all_fields_complete,
            "fields": {n: {"total": f.total, "readable": f.readable,
                           "correct": f.correct, "fallback": f.fallback,
                           "scored": f.scored, "has_reference": f.has_reference,
                           "completeness": f.completeness, "accuracy": f.accuracy}
                       for n, f in c.fields.items()},
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"result": c, "text": text}


AVAILABLE_CRITERIA = ("sc01", "sc02", "sc03", "sc04", "sc05")


def selected_criteria(args) -> list[str]:
    """Kriteria yang diminta.

    Tanpa flag berarti semua kriteria yang tersedia. Ini dipusatkan di satu
    tempat supaya `--metrics-only`, `--repeat`, dan lintasan penuh tidak bisa
    berbeda pendapat soal apa yang harus diukur. Sebelumnya SC-01 jadi bawaan
    sementara SC-02 harus diminta, sehingga `--sc02` dan tanpa-flag terlihat
    seperti dua perintah yang tidak sederajat.
    """
    if getattr(args, "all", False):
        return list(AVAILABLE_CRITERIA)
    picked = [name for name in AVAILABLE_CRITERIA if getattr(args, name, False)]
    return picked or list(AVAILABLE_CRITERIA)


def run_reports(results: list[dict], out: Path, criteria: list[str]) -> dict[str, dict]:
    """Hitung laporan tiap kriteria, dikembalikan sesuai urutan `criteria`.

    Sebelumnya urutan cetak ditulis tangan sebagai dua blok `if` terpisah, dan
    blok SC-02 kebetulan diletakkan lebih dulu. Akibatnya log menampilkan SC-02
    di atas SC-01 seolah SC-02 berjalan lebih dulu, padahal satu lintasan
    ekstraksi dipakai bersama dan tidak ada yang berjalan dua kali. Dengan
    dispatch ini, urutan keluaran selalu mengikuti `criteria`, jadi menambah
    kriteria baru tidak bisa lagi menghasilkan urutan yang menyesatkan.
    """
    builders = {
        "sc01": write_sc01_report,
        "sc02": write_sc02_report,
        "sc03": write_sc03_report,
        "sc04": write_sc04_report,
        "sc05": write_sc05_report,
    }
    return {name: builders[name](results, out) for name in criteria}


def join_reports(reports: dict[str, dict]) -> str:
    """Gabungkan teks laporan dengan satu pemisah di antaranya."""
    return "\n".join(r["text"] for r in reports.values())


def spread_value(name: str, report: dict) -> float:
    """Angka utama satu kriteria, dipakai untuk mengukur sebaran antar-run."""
    if name == "sc01":
        return report["metrics"].accuracy
    return report["result"].overall_accuracy


def spread_block(name: str, values: list[float], repeat: int,
                 baseline: tuple[float, str] | None = None) -> str:
    """Ringkasan sebaran satu kriteria pada `repeat` run."""
    lowest, highest = min(values), max(values)
    average = sum(values) / len(values)
    label = {"sc01": "akurasi", "sc02": "kecocokan"}.get(name, "nilai")
    lines = [
        f"{name.upper()} — sebaran {repeat} run",
        f"{label} terendah : {lowest:.1%}",
        f"{label} tertinggi: {highest:.1%}",
        f"rata-rata        : {average:.1%}",
        f"rentang          : {(highest - lowest) * 100:.1f} poin persen",
    ]
    if baseline:
        lines.append(f"baseline         : {baseline[0]:.1%} ({baseline[1]})")
    return "\n".join(lines)


def main_cli() -> int:
    ap = argparse.ArgumentParser(
        description="Runner evaluasi kriteria keberhasilan (SC-01, SC-02)",
        epilog="Tanpa flag kriteria, semua kriteria yang tersedia diukur. "
               "Satu lintasan model dipakai bersama, jadi menambah kriteria "
               "tidak menambah biaya.")
    ap.add_argument("--download", action="store_true",
                    help="unduh gambar dataset dari repo, lalu berhenti")
    ap.add_argument("--pairs", default="", help="timpa SC_PAIRS")
    ap.add_argument("--images", default="", help="timpa SC_IMAGES")
    ap.add_argument("--out", default="sc-out", help="folder keluaran (default: sc-out)")
    ap.add_argument("--restart", action="store_true", help="abaikan hasil lama, proses dari awal")
    ap.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="jalankan N kali lalu laporkan rentang angka (untuk mengukur kestabilan)")
    ap.add_argument("--metrics-only", action="store_true", help="hitung metrik tanpa memanggil AI")

    pick = ap.add_mutually_exclusive_group()
    pick.add_argument("--sc01", action="store_true",
                      help="ukur akurasi kategori (SC-01) saja")
    pick.add_argument("--sc02", action="store_true",
                      help="ukur kelengkapan field wajib (SC-02) saja")
    pick.add_argument("--sc03", action="store_true",
                      help="ukur waktu proses sampai tersimpan (SC-03) saja")
    pick.add_argument("--sc04", action="store_true",
                      help="ukur biaya per gambar (SC-04) saja")
    pick.add_argument("--sc05", action="store_true",
                      help="uji penolakan duplikat (SC-05) saja")
    pick.add_argument("--all", action="store_true",
                      help="ukur semua kriteria yang tersedia (sama dengan tanpa flag)")
    a = ap.parse_args()

    criteria = selected_criteria(a)

    # Argumen CLI menang atas .env, supaya bisa dipakai tanpa menyunting file.
    if a.pairs:
        os.environ["SC_PAIRS"] = a.pairs
    if a.images:
        os.environ["SC_IMAGES"] = a.images

    if a.download:
        # Daftar pasangan diunduh dulu: tanpa itu tidak diketahui gambar mana
        # yang harus diambil. Keduanya ada di repo yang sama.
        cfg.download_pairs()
        folder = cfg.images_dir()
        print(f"mengunduh gambar ke: {folder}")
        downloaded, skipped = cfg.download_images(folder)
        print(f"selesai: {downloaded} diunduh, {skipped} sudah ada")
        is_ready, reason = cfg.ready(skip_ai_check=True)
        print(f"status: {'siap' if is_ready else 'BELUM siap'} — {reason}")
        return 0 if is_ready else 1

    out = Path(a.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    if a.metrics_only:
        # SC-03 tidak punya hasil ekstraksi untuk dibaca ulang: waktu tidak
        # tersimpan di CSV hasil. Kalau hanya SC-03 yang diminta, cukup
        # rangkum sampel waktunya tanpa menyentuh `results_per_row.csv`.
        if criteria in (["sc03"], ["sc04"], ["sc05"]):
            reports = run_reports([], out, criteria)
            print(join_reports(reports))
            return 0
        results = list(read_results(out / "results_per_row.csv").values())
        if not results:
            raise SystemExit(f"tidak ada hasil di {out / 'results_per_row.csv'}")
        reports = run_reports(results, out, criteria)
        print(join_reports(reports))
        return 0

    # SC-03 mengukur waktu, bukan isi. Waktunya sudah direkam harness pengukur,
    # jadi meminta SC-03 saja tidak boleh menuntut kunci model: laporan SC-03
    # hanya merangkum sampel yang sudah ada.
    if criteria in (["sc03"], ["sc04"], ["sc05"]):
        # Keduanya mengukur hal yang tidak tersimpan di hasil ekstraksi: waktu
        # dan token. Laporannya hanya merangkum sampel yang sudah ada, jadi
        # tidak perlu memanggil model dan tidak boleh mencetak banner "hasil
        # lama dipakai lagi" yang menyiratkan ada ekstraksi.
        reports = run_reports([], out, criteria)
        print(join_reports(reports))
        return 0

    is_ready, reason = cfg.ready()
    if not is_ready:
        raise SystemExit(f"belum siap: {reason}")

    pairs = cfg.read_pairs(cfg.pairs_file())
    print(f"pasangan: {len(pairs)}")

    if a.repeat > 1:
        # Dijalankan berulang untuk melihat sebaran angka. Model tidak menjamin
        # hasil identik antar-run, jadi satu angka saja bisa menyesatkan.
        per_criterion: dict[str, list[float]] = {name: [] for name in criteria}
        baselines: dict[str, tuple[float, str]] = {}
        for n in range(1, a.repeat + 1):
            print(f"\n===== run {n} dari {a.repeat} =====")
            run_dir = out / f"run-{n}"
            run_dir.mkdir(parents=True, exist_ok=True)
            run_results = asyncio.run(run_pairs(pairs, cfg.images_dir(),
                                                run_dir / "results_per_row.csv", True))
            reports = run_reports(run_results, run_dir, criteria)
            for name, rep in reports.items():
                per_criterion[name].append(spread_value(name, rep))
                if name == "sc01":
                    m = rep["metrics"]
                    baselines[name] = (m.baseline, m.majority_label)
            print(join_reports(reports))

        blocks = [spread_block(name, per_criterion[name], a.repeat,
                               baselines.get(name))
                  for name in criteria if per_criterion[name]]
        text = f"\n{'=' * 60}\n".join(blocks)
        (out / "spread.txt").write_text(text, encoding="utf-8")
        print("\n" + "=" * 60 + "\n" + text)
        return 0

    results = asyncio.run(run_pairs(pairs, cfg.images_dir(),
                                    out / "results_per_row.csv", a.restart))

    # Satu lintasan panggilan model cukup untuk semua kriteria: semuanya
    # membaca keluaran ekstraksi yang sama. Memisahkan lintasan hanya akan
    # menggandakan biaya tanpa menambah informasi.
    reports = run_reports(results, out, criteria)
    print(join_reports(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
