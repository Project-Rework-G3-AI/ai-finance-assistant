"""Pengukur SC-04: biaya per gambar dari respons model yang sebenarnya.

`main._vision_extract()` tidak menyimpan jumlah token, karena aplikasi tidak
butuh angka itu untuk beroperasi. Pengukuran butuh, jadi pengukur ini memanggil
penyedia dengan payload yang **sama persis** dengan produksi, lalu membaca field
`usage` dari responsnya.

Yang sengaja tidak dilakukan: menaksir token dari panjang teks. Taksiran
menghasilkan angka yang terlihat masuk akal tetapi tidak bisa
dipertanggungjawabkan, dan target Rp50 terlalu ketat untuk dinilai dengan
perkiraan.

Dijalankan:  python3 tests/_sc04_run.py [--limit N] [--restart]
"""

from __future__ import annotations

import asyncio
import base64
import csv
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import sc04_cost as sc04  # noqa: E402

OUT = REPO / "sc-out"
SAMPLES = OUT / "sc04_samples.csv"
# Yang disimpan hanya fakta: token yang benar-benar terpakai. Biaya adalah
# turunan dari tarif dan kurs, jadi sengaja TIDAK disimpan. Kalau disimpan,
# mengubah tarif atau kurs akan tetap menampilkan biaya lama, dan penyesuaian
# tarif yang diminta jadi tidak berefek.
KOLOM = ["file", "ok", "error", "prompt_tokens", "completion_tokens"]


def baca_env() -> None:
    """Baca `.env` di akar repo, sama seperti aplikasi."""
    berkas = REPO / ".env"
    if not berkas.exists():
        return
    for baris in berkas.read_text(encoding="utf-8").splitlines():
        baris = baris.strip()
        if not baris or baris.startswith("#") or "=" not in baris:
            continue
        kunci, _, nilai = baris.partition("=")
        kunci = kunci.strip()
        if kunci and kunci not in os.environ:
            os.environ[kunci] = nilai.strip().strip('"').strip("'")


def kredensial() -> tuple[str, str, str]:
    """Kunci, base URL, dan model. Gagal jelas bila salah satu kosong."""
    kunci = (os.getenv("AI_API_KEY") or "").strip()
    base = (os.getenv("AI_BASE_URL") or "").strip().rstrip("/")
    model = (os.getenv("AI_MODEL") or "").strip()
    kurang = [nama for nama, nilai in
              (("AI_API_KEY", kunci), ("AI_BASE_URL", base), ("AI_MODEL", model))
              if not nilai]
    if kurang:
        raise SystemExit(
            f"{', '.join(kurang)} kosong. Isi .env lebih dulu "
            "(lihat .env.example).")
    return kunci, base, model


def ambil_katalog(model: str) -> dict | None:
    """Tarif resmi dari katalog penyedia, atau None bila tidak bisa diambil."""
    import httpx

    try:
        r = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
        r.raise_for_status()
        for entri in r.json().get("data", []):
            if entri.get("id") == model:
                return entri
    except Exception:
        return None
    return None


def prompt_produksi() -> str:
    """Prompt yang sama persis dengan `main._vision_extract`.

    Diambil dari modul produksi bila memungkinkan, supaya jumlah token yang
    diukur benar-benar mewakili produksi. Kalau tidak bisa diimpor, salinan di
    bawah harus diperbarui bersamaan dengan main.py.
    """
    try:
        import main

        sumber = Path(main.__file__).read_text(encoding="utf-8")
        awal = sumber.index('prompt = (')
        akhir = sumber.index('if caption:', awal)
        potongan = sumber[awal:akhir]
        # Prompt disusun dari literal string; ambil isinya apa adanya.
        ns: dict = {}
        exec(potongan, {"KAT": main.KAT}, ns)  # noqa: S102
        return ns["prompt"]
    except Exception:
        from cash_report import categories as KAT

        return (
            "Ekstrak data transaksi dari bukti ini. Balas HANYA JSON tanpa teks lain: "
            '{"tanggal":"YYYY-MM-DD","keterangan":"...","nominal":number,'
            '"arah":"masuk|keluar|transfer",'
            f'"kategori":"satu dari: {KAT.PROMPT_KATEGORI}",'
            '"bank":"kantong asal dana — salah satu dari: BRI, BNI, Jago, TUNAI; '
            'kosong bila tidak terbaca",'
            '"kantong_tujuan":"hanya bila arah=transfer — kantong tujuan: '
            'BRI, BNI, Jago, TUNAI; kosong bila bukan transfer"}'
        )


async def ukur_satu(client, kunci: str, base: str, model: str, prompt: str,
                    nama: str, gambar: bytes) -> dict:
    """Satu panggilan ke penyedia, kembalikan token yang terpakai."""
    b64 = base64.b64encode(gambar).decode()
    mime = "image/png" if nama.lower().endswith(".png") else "image/jpeg"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        "temperature": 0,
    }
    r = await client.post(f"{base}/chat/completions",
                          headers={"Authorization": f"Bearer {kunci}"},
                          json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if prompt_tokens is None or completion_tokens is None:
        raise RuntimeError(
            "respons tidak memuat usage.prompt_tokens/completion_tokens; "
            f"kunci yang ada: {sorted(usage)}")
    return {"prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens)}


def baca_samples() -> dict[str, dict]:
    if not SAMPLES.exists():
        return {}
    with SAMPLES.open(encoding="utf-8") as f:
        return {r["file"]: r for r in csv.DictReader(f)}


def tulis_baris(row: dict) -> None:
    baru = not SAMPLES.exists()
    with SAMPLES.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KOLOM)
        if baru:
            w.writeheader()
        w.writerow(row)


async def jalankan(limit: int | None, restart: bool, target: float | None,
                   prompt_usd: float | None, completion_usd: float | None,
                   usd_idr: float | None) -> None:
    import httpx

    baca_env()
    kunci, base, model = kredensial()

    OUT.mkdir(parents=True, exist_ok=True)
    if restart and SAMPLES.exists():
        SAMPLES.unlink()

    # Tarif: CLI > env > katalog. Tidak ada tebakan.
    katalog = None if (prompt_usd is not None or os.getenv(sc04.ENV_PROMPT)) \
        else ambil_katalog(model)
    harga = sc04.pricing_from(prompt=prompt_usd, completion=completion_usd,
                              model=model, catalog=katalog)

    kurs = sc04.usd_to_idr_from(usd_idr)
    if not kurs:
        raise SystemExit(
            "Kurs belum diketahui. Isi --usd-idr <rupiah per USD> "
            f"atau {sc04.ENV_USD_IDR}. Kurs tidak ditebak karena mengubah hasil.")
    batas = sc04.target_from(target)

    print(f"model      : {harga.model}")
    print(f"tarif      : prompt ${harga.prompt_usd:.10f}  "
          f"completion ${harga.completion_usd:.10f}  ({harga.source})")
    print(f"kurs       : Rp{kurs:.2f}/USD")
    print(f"target     : Rp{batas:.2f}/gambar")
    print()

    sudah = baca_samples()

    gambar_dir = REPO / "dataset/Bukti Transaksi Januari 2026"
    pairs = REPO / "dataset/pairs.csv"
    if not gambar_dir.is_dir() or not pairs.exists():
        raise SystemExit("dataset belum ada — jalankan --download dulu")

    with pairs.open(encoding="utf-8") as f:
        nama_acuan = {r["file"] for r in csv.DictReader(f)}
    sasaran = sorted(p for p in gambar_dir.glob("*.jpg") if p.name in nama_acuan)
    if limit:
        sasaran = sasaran[:limit]

    tersisa = [p for p in sasaran if p.name not in sudah]
    print(f"total sasaran : {len(sasaran)}")
    print(f"sudah ada     : {len(sasaran) - len(tersisa)}")
    print(f"akan diukur   : {len(tersisa)}")
    print()

    prompt = prompt_produksi()

    async with httpx.AsyncClient() as client:
        for i, path in enumerate(tersisa, 1):
            try:
                token = await ukur_satu(client, kunci, base, model, prompt,
                                        path.name, path.read_bytes())
                biaya = sc04.cost_idr(harga, token["prompt_tokens"],
                                      token["completion_tokens"], kurs)
                baris = {"file": path.name, "ok": True, "error": "",
                         "prompt_tokens": token["prompt_tokens"],
                         "completion_tokens": token["completion_tokens"]}
                status = f"Rp{biaya:6.2f}"
            except Exception as e:  # noqa: BLE001
                baris = {"file": path.name, "ok": False, "error": str(e)[:200],
                         "prompt_tokens": 0, "completion_tokens": 0}
                status = f"GAGAL {str(e)[:40]}"
            tulis_baris(baris)
            print(f"  [{i:3}/{len(tersisa)}] {path.name:42} {status}", flush=True)

    # Ringkasan dari seluruh sampel yang ada, bukan hanya yang baru diukur.
    samples = []
    for r in baca_samples().values():
        s = sc04.Sample(
            file=r["file"], ok=(r["ok"] == "True"), error=r.get("error", ""),
            prompt_tokens=int(r.get("prompt_tokens") or 0),
            completion_tokens=int(r.get("completion_tokens") or 0))
        # Biaya dihitung dari token dengan tarif yang berlaku sekarang, bukan
        # dibaca dari berkas. Ini yang membuat penyesuaian tarif berefek.
        s.cost_idr = sc04.cost_idr(harga, s.prompt_tokens,
                                   s.completion_tokens, kurs)
        samples.append(s)

    c = sc04.compute(samples, target=batas, pricing=harga, usd_to_idr=kurs)
    sc04.write_report(c, OUT,
                      "Sumber data: diukur langsung ke penyedia model, "
                      "token dibaca dari field usage pada respons.")
    print()
    print(sc04.report(c))


if __name__ == "__main__":
    def angka(flag: str) -> float | None:
        if flag not in sys.argv:
            return None
        return float(sys.argv[sys.argv.index(flag) + 1])

    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    asyncio.run(jalankan(
        limit=limit,
        restart="--restart" in sys.argv,
        target=angka("--target-idr"),
        prompt_usd=angka("--price-prompt"),
        completion_usd=angka("--price-completion"),
        usd_idr=angka("--usd-idr"),
    ))
