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
COLUMNS = ["file", "ok", "error", "prompt_tokens", "completion_tokens"]


def read_env() -> None:
    """Baca `.env` di akar repo, sama seperti aplikasi."""
    path = REPO / ".env"
    if not path.exists():
        return
    for row in path.read_text(encoding="utf-8").splitlines():
        row = row.strip()
        if not row or row.startswith("#") or "=" not in row:
            continue
        key, _, value = row.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def credentials() -> tuple[str, str, str]:
    """Kunci, base URL, dan model. Gagal jelas bila salah satu kosong."""
    key = (os.getenv("AI_API_KEY") or "").strip()
    base = (os.getenv("AI_BASE_URL") or "").strip().rstrip("/")
    model = (os.getenv("AI_MODEL") or "").strip()
    missing_items = [name for name, value in
              (("AI_API_KEY", key), ("AI_BASE_URL", base), ("AI_MODEL", model))
              if not value]
    if missing_items:
        raise SystemExit(
            f"{', '.join(missing_items)} kosong. Isi .env lebih dulu "
            "(lihat .env.example).")
    return key, base, model


def fetch_catalog(model: str) -> dict | None:
    """Tarif resmi dari katalog penyedia, atau None bila tidak bisa diambil."""
    import httpx

    try:
        r = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
        r.raise_for_status()
        for entry in r.json().get("data", []):
            if entry.get("id") == model:
                return entry
    except Exception:
        return None
    return None


def production_prompt() -> str:
    """Prompt yang sama persis dengan `main._vision_extract`.

    Diambil dari modul produksi bila memungkinkan, supaya jumlah token yang
    diukur benar-benar mewakili produksi. Kalau tidak bisa diimpor, salinan di
    bawah harus diperbarui bersamaan dengan main.py.
    """
    try:
        import main

        source = Path(main.__file__).read_text(encoding="utf-8")
        start = source.index('prompt = (')
        end = source.index('if caption:', start)
        segment = source[start:end]
        # Prompt disusun dari literal string; ambil isinya apa adanya.
        ns: dict = {}
        exec(segment, {"KAT": main.KAT}, ns)  # noqa: S102
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


async def measure_one(client, key: str, base: str, model: str, prompt: str,
                    name: str, image: bytes) -> dict:
    """Satu panggilan ke penyedia, kembalikan token yang terpakai."""
    b64 = base64.b64encode(image).decode()
    mime = "image/png" if name.lower().endswith(".png") else "image/jpeg"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        "temperature": 0,
    }
    r = await client.post(f"{base}/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
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


def read_samples() -> dict[str, dict]:
    if not SAMPLES.exists():
        return {}
    with SAMPLES.open(encoding="utf-8") as f:
        return {r["file"]: r for r in csv.DictReader(f)}


def write_row(row: dict) -> None:
    is_new = not SAMPLES.exists()
    with SAMPLES.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if is_new:
            w.writeheader()
        w.writerow(row)


async def run_all(limit: int | None, restart: bool, target: float | None,
                   prompt_usd: float | None, completion_usd: float | None,
                   usd_idr: float | None) -> None:
    import httpx

    read_env()
    key, base, model = credentials()

    OUT.mkdir(parents=True, exist_ok=True)
    if restart and SAMPLES.exists():
        SAMPLES.unlink()

    # Tarif: CLI > env > katalog. Tidak ada tebakan.
    catalog = None if (prompt_usd is not None or os.getenv(sc04.ENV_PROMPT)) \
        else fetch_catalog(model)
    price = sc04.pricing_from(prompt=prompt_usd, completion=completion_usd,
                              model=model, catalog=catalog)

    exchange_rate = sc04.usd_to_idr_from(usd_idr)
    if not exchange_rate:
        raise SystemExit(
            "Kurs belum diketahui. Isi --usd-idr <rupiah per USD> "
            f"atau {sc04.ENV_USD_IDR}. Kurs tidak ditebak karena mengubah hasil.")
    threshold = sc04.target_from(target)

    print(f"model      : {price.model}")
    print(f"tarif      : prompt ${price.prompt_usd:.10f}  "
          f"completion ${price.completion_usd:.10f}  ({price.source})")
    print(f"kurs       : Rp{exchange_rate:.2f}/USD")
    print(f"target     : Rp{threshold:.2f}/gambar")
    print()

    existing = read_samples()

    image_dir = REPO / "dataset/Bukti Transaksi Januari 2026"
    pairs = REPO / "dataset/pairs.csv"
    if not image_dir.is_dir() or not pairs.exists():
        raise SystemExit("dataset belum ada — jalankan --download dulu")

    with pairs.open(encoding="utf-8") as f:
        reference_names = {r["file"] for r in csv.DictReader(f)}
    aimed = sorted(p for p in image_dir.glob("*.jpg") if p.name in reference_names)
    if limit:
        aimed = aimed[:limit]

    remaining = [p for p in aimed if p.name not in existing]
    print(f"total sasaran : {len(aimed)}")
    print(f"sudah ada     : {len(aimed) - len(remaining)}")
    print(f"akan diukur   : {len(remaining)}")
    print()

    prompt = production_prompt()

    async with httpx.AsyncClient() as client:
        for i, path in enumerate(remaining, 1):
            try:
                token = await measure_one(client, key, base, model, prompt,
                                        path.name, path.read_bytes())
                cost = sc04.cost_idr(price, token["prompt_tokens"],
                                      token["completion_tokens"], exchange_rate)
                row = {"file": path.name, "ok": True, "error": "",
                         "prompt_tokens": token["prompt_tokens"],
                         "completion_tokens": token["completion_tokens"]}
                status = f"Rp{cost:6.2f}"
            except Exception as e:  # noqa: BLE001
                row = {"file": path.name, "ok": False, "error": str(e)[:200],
                         "prompt_tokens": 0, "completion_tokens": 0}
                status = f"GAGAL {str(e)[:40]}"
            write_row(row)
            print(f"  [{i:3}/{len(remaining)}] {path.name:42} {status}", flush=True)

    # Ringkasan dari seluruh sampel yang ada, bukan hanya yang baru diukur.
    samples = []
    for r in read_samples().values():
        s = sc04.Sample(
            file=r["file"], ok=(r["ok"] == "True"), error=r.get("error", ""),
            prompt_tokens=int(r.get("prompt_tokens") or 0),
            completion_tokens=int(r.get("completion_tokens") or 0))
        # Biaya dihitung dari token dengan tarif yang berlaku sekarang, bukan
        # dibaca dari berkas. Ini yang membuat penyesuaian tarif berefek.
        s.cost_idr = sc04.cost_idr(price, s.prompt_tokens,
                                   s.completion_tokens, exchange_rate)
        samples.append(s)

    c = sc04.compute(samples, target=threshold, pricing=price, usd_to_idr=exchange_rate)
    sc04.write_report(c, OUT,
                      "Sumber data: diukur langsung ke penyedia model, "
                      "token dibaca dari field usage pada respons.")
    print()
    print(sc04.report(c))


if __name__ == "__main__":
    def parse_number(flag: str) -> float | None:
        if flag not in sys.argv:
            return None
        return float(sys.argv[sys.argv.index(flag) + 1])

    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    asyncio.run(run_all(
        limit=limit,
        restart="--restart" in sys.argv,
        target=parse_number("--target-idr"),
        prompt_usd=parse_number("--price-prompt"),
        completion_usd=parse_number("--price-completion"),
        usd_idr=parse_number("--usd-idr"),
    ))
