"""Tanya-jawab Cash Report (milestone 3).

Command / (deterministik, tanpa LLM) + bahasa bebas lewat satu panggilan
LLM tool-calling. Semua tool baca-saja: angka dihitung kode, LLM hanya
merangkai kalimat dan wajib menyebut sumber. Angka verified dan draft
selalu disebut terpisah; transfer antar kantong dikecualikan dari total
(cocok dengan RECAP di Sheet).
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from datetime import date, datetime

import httpx

from cash_report import categories as KAT

log = logging.getLogger(__name__)

BULAN = {
    "jan": 1, "januari": 1, "feb": 2, "februari": 2, "mar": 3, "maret": 3,
    "apr": 4, "april": 4, "mei": 5, "may": 5, "jun": 6, "juni": 6,
    "jul": 7, "juli": 7, "agu": 8, "aug": 8, "agustus": 8,
    "sep": 9, "september": 9, "okt": 10, "oct": 10, "oktober": 10, "october": 10,
    "nov": 11, "november": 11, "des": 12, "dec": 12, "desember": 12, "december": 12,
}

# &lt;/&gt; wajib: balasan dikirim dengan parse_mode=HTML, "<bulan>" ditolak
# Telegram sebagai tag tak dikenal (error 400 saat /help).
HELP = (
    "Tanya-jawab Cash Report:\n"
    "/total [bulan] — total masuk/keluar, default bulan ini (contoh: /total Nov)\n"
    "/rekap [bulan] — rincian per kategori (default bulan ini)\n"
    "/help — bantuan ini\n"
    'Atau tulis bebas, mis. "berapa pengeluaran November kategori Listrik?"'
)

FALLBACK = "AI sedang tidak tersedia. Coba /total &lt;bulan&gt; atau /rekap."

_FORMAT_ERROR = "Format: /total &lt;bulan&gt; — contoh: /total Nov, /total 2026-11"


def _ai() -> tuple[str, str, str]:
    # Dibaca saat dipanggil (bukan saat import): load_dotenv() main berjalan
    # setelah impor modul ini.
    return (
        os.getenv("AI_API_KEY", "").strip(),
        os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        os.getenv("AI_MODEL", "gpt-4o-mini").strip(),
    )


# ---------- periode & baris (murni, bisa dites tanpa jaringan) ----------

def parse_period(s: str, today: date | None = None) -> tuple[date, date] | None:
    """'2026-11' | 'Nov' | 'November' | '' -> (awal, akhir-eksklusif); None bila tak dikenal."""
    today = today or date.today()
    s = (s or "").strip().lower()
    if not s:
        y, m = today.year, today.month
    else:
        mm = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", s)
        if mm:
            y, m = int(mm.group(1)), int(mm.group(2))
            if not 1 <= m <= 12:
                return None
        else:
            m = BULAN.get(s) or BULAN.get(s[:3])
            if not m:
                return None
            y = today.year
    awal = date(y, m, 1)
    akhir = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return awal, akhir


def _tgl(v) -> date | None:
    s = str(v or "").strip()
    if not s:
        return None
    # %d-%b-%y = tampilan default Sheets en_US ("6-Jan-26") — format yang
    # paling sering muncul di TRANSAKSI; tanpa ini filter periode nihil.
    for f in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y",
              "%d-%b-%y", "%d-%b-%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def _num(v) -> float:
    """Terima angka mentah maupun tampilan 'Rp40,400' / '40.400' (get_values
    mengembalikan hasil render sel, bukan nilai mentah)."""
    s = re.sub(r"[^\d.,-]", "", str(v or ""))
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    elif "." in s and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _recs(rows: list) -> list[dict]:
    out = []
    for r in rows:
        r = (list(r) + [""] * 11)[:11]
        if not any(str(c).strip() for c in r):
            continue
        out.append({
            "tanggal": _tgl(r[0]),
            "kantong": str(r[1]).strip(),
            "masuk": _num(r[2]),
            "keluar": _num(r[3]),
            "kategori": str(r[4]).strip(),
            "keterangan": str(r[5]).strip(),
            "status": str(r[6]).strip().lower(),
            "ref_id": str(r[8]).strip(),
            "link": str(r[10]).strip(),
        })
    return out


def _pilih(rows: list, awal: date, akhir: date, arah: str | None = None,
           kategori: str | None = None) -> list[dict]:
    kf = (kategori or "").strip()
    kn = KAT.normalize(kf) if kf else ""
    for x in _recs(rows):
        if x["tanggal"] is None or not (awal <= x["tanggal"] < akhir):
            continue
        if kf:
            kanon = KAT.normalize(x["kategori"]) if x["kategori"] else ""
            if not (
                x["kategori"].casefold() == kf.casefold()
                or (kn != KAT.PERLU_DITINJAU and kanon == kn)
            ):
                continue
        if arah == "masuk" and x["masuk"] <= 0:
            continue
        if arah == "keluar" and x["keluar"] <= 0:
            continue
        yield x


def _is_transfer(kategori: str) -> bool:
    return kategori in KAT.PERPINDAHAN or KAT.normalize(kategori) in KAT.PERPINDAHAN


def aggregate(rows: list, awal: date, akhir: date,
              arah: str | None = None, kategori: str | None = None) -> dict:
    """Total per status; transfer dikecualikan dari masuk/keluar (seperti RECAP)."""
    tot = {
        "verified": {"masuk": 0.0, "keluar": 0.0, "n": 0},
        "draft": {"masuk": 0.0, "keluar": 0.0, "n": 0},
        "transfer": {"verified": 0.0, "draft": 0.0, "n_verified": 0, "n_draft": 0},
    }
    for x in _pilih(rows, awal, akhir, None, kategori):
        if _is_transfer(x["kategori"]):
            st = "verified" if x["status"] == "verified" else "draft"
            # sisi masuk pasangan; sisi keluar ikut sama
            tot["transfer"][st] += x["masuk"]
            tot["transfer"]["n_" + st] += 1
            continue
        if arah == "masuk" and x["masuk"] <= 0:
            continue
        if arah == "keluar" and x["keluar"] <= 0:
            continue
        st = "verified" if x["status"] == "verified" else "draft"
        if arah != "keluar":
            tot[st]["masuk"] += x["masuk"]
        if arah != "masuk":
            tot[st]["keluar"] += x["keluar"]
        tot[st]["n"] += 1
    return tot


def rekap(rows: list, awal: date, akhir: date) -> list[tuple[str, dict]]:
    """Per kategori (transfer dikecualikan, konsisten dengan total)."""
    g: dict[str, dict] = {}
    for x in _pilih(rows, awal, akhir):
        if _is_transfer(x["kategori"]):
            continue
        k = x["kategori"] or "(kosong)"
        e = g.setdefault(k, {"vm": 0.0, "vk": 0.0, "dm": 0.0, "dk": 0.0, "vn": 0, "dn": 0})
        st = "v" if x["status"] == "verified" else "d"
        e[st + "m"] += x["masuk"]
        e[st + "k"] += x["keluar"]
        e[st + "n"] += 1
    return sorted(g.items(), key=lambda kv: -(kv[1]["vm"] + kv[1]["vk"] + kv[1]["dm"] + kv[1]["dk"]))


def list_rows(rows: list, awal: date, akhir: date, arah: str | None = None,
              kategori: str | None = None, limit: int = 15) -> list[dict]:
    out = []
    for x in _pilih(rows, awal, akhir, arah, kategori):
        out.append({
            "tanggal": x["tanggal"].isoformat() if x["tanggal"] else "",
            "kantong": x["kantong"],
            "kategori": x["kategori"],
            "masuk": x["masuk"],
            "keluar": x["keluar"],
            "status": x["status"],
            "keterangan": x["keterangan"],
            "ref_id": x["ref_id"],
        })
        if len(out) >= max(1, min(int(limit or 15), 50)):
            break
    return out


def find_receipt(rows: list, ref_id: str) -> str | None:
    ref = (ref_id or "").strip()
    for x in _recs(rows):
        if ref and x["ref_id"] == ref:
            return x["link"] or None
    return None


# ---------- format balasan ----------

def _rp(n: float) -> str:
    return f"Rp{n:,.0f}"


def _periode_label(awal: date) -> str:
    nama = [k for k, v in BULAN.items() if v == awal.month and len(k) > 3]
    return f"{nama[0].capitalize()} {awal.year}" if nama else f"{awal.month:02d}/{awal.year}"


def format_total(awal: date, tot: dict) -> str:
    v, d = tot["verified"], tot["draft"]
    saldo = v["masuk"] - v["keluar"]
    lines = [
        f"📊 <b>Total {_periode_label(awal)}</b>",
        f"Verified: masuk {_rp(v['masuk'])} · keluar {_rp(v['keluar'])} · saldo {_rp(saldo)}",
        f"Draft: masuk {_rp(d['masuk'])} · keluar {_rp(d['keluar'])} ({d['n']} baris — belum verified)",
    ]
    tr = tot["transfer"]
    if tr["n_verified"] or tr["n_draft"]:
        lines.append(
            f"Transfer antar kantong: verified {_rp(tr['verified'])} ({tr['n_verified']} baris) · "
            f"draft {_rp(tr['draft'])} ({tr['n_draft']} baris) — di luar total"
        )
    lines.append("<i>Sumber: TRANSAKSI (Cash Report)</i>")
    return "\n".join(lines)


def format_rekap(awal: date, items: list[tuple[str, dict]], tot: dict) -> str:
    lines = [f"📋 <b>Rekap {_periode_label(awal)}</b> per kategori"]
    for k, e in items[:15]:
        bagian = []
        if e["vn"] or e["dn"]:
            if e["vn"]:
                bagian.append(f"v {_rp(e['vm'] - e['vk'])}")
            if e["dn"]:
                bagian.append(f"d {_rp(e['dm'] - e['dk'])}")
            lines.append(f"• {html.escape(k)} — {' · '.join(bagian)}")
    v, d = tot["verified"], tot["draft"]
    lines.append(f"Total verified: masuk {_rp(v['masuk'])} · keluar {_rp(v['keluar'])}")
    lines.append(f"Total draft: masuk {_rp(d['masuk'])} · keluar {_rp(d['keluar'])} ({d['n']} baris)")
    tr = tot["transfer"]
    if tr["n_verified"] or tr["n_draft"]:
        lines.append(
            f"Transfer: verified {_rp(tr['verified'])} · draft {_rp(tr['draft'])} (di luar total)"
        )
    lines.append("<i>Sumber: TRANSAKSI (Cash Report)</i>")
    return "\n".join(lines)


def format_rows(awal: date, rows: list[dict]) -> str:
    if not rows:
        return f"Tidak ada baris pada {_periode_label(awal)}."
    lines = [f"🧾 <b>{len(rows)} baris</b> — {_periode_label(awal)}"]
    for x in rows:
        nominal = _rp(x["masuk"]) if x["masuk"] else _rp(x["keluar"])
        arah = "+" if x["masuk"] else "-"
        st = "v" if x["status"] == "verified" else "d"
        lines.append(
            f"{x['tanggal']} {arah}{nominal} {html.escape(x['kategori'] or '-')} "
            f"[{st}] {html.escape(x['keterangan'][:40])}"
        )
    lines.append("<i>Sumber: TRANSAKSI (Cash Report)</i>")
    return "\n".join(lines)


# ---------- command / ----------

def command_reply(text: str, load_rows) -> str | None:
    """Handler command (sinkron). load_rows(year) -> list baris sheet A2:K."""
    if not text.startswith("/"):
        return None
    parts = text.split()
    cmd = parts[0].split("@")[0].lower()
    if cmd == "/help":
        return HELP
    if cmd not in ("/total", "/rekap"):
        return HELP
    # Tanpa argumen = bulan berjalan. Telegram mengirim command dari menu
    # otomatis sebelum user sempat mengetik bulannya, jadi /total polos
    # harus tetap memberi jawaban berguna.
    arg = parts[1] if len(parts) > 1 else ""
    periode = parse_period(arg)
    if periode is None:
        return _FORMAT_ERROR if cmd == "/total" else "Format: /rekap [bulan] — contoh: /rekap Nov"
    awal, akhir = periode
    rows = load_rows(str(awal.year))
    tot = aggregate(rows, awal, akhir)
    if cmd == "/total":
        return format_total(awal, tot)
    return format_rekap(awal, rekap(rows, awal, akhir), tot)


# ---------- bahasa bebas: satu panggilan tool-calling ----------

TOOLS = [
    {"type": "function", "function": {
        "name": "aggregate",
        "description": "Total masuk/keluar suatu periode; angka verified & draft terpisah; "
                       "transfer antar kantong dikecualikan dari total.",
        "parameters": {"type": "object", "properties": {
            "period": {"type": "string", "description": "'2026-11' atau nama bulan, mis. 'Nov'"},
            "arah": {"type": "string", "enum": ["masuk", "keluar"]},
            "kategori": {"type": "string", "description": "satu kategori, mis. 'Listrik'"},
        }, "required": ["period"]},
    }},
    {"type": "function", "function": {
        "name": "list_rows",
        "description": "Daftar baris transaksi suatu periode (tanggal, nominal, kategori, status).",
        "parameters": {"type": "object", "properties": {
            "period": {"type": "string"},
            "arah": {"type": "string", "enum": ["masuk", "keluar"]},
            "kategori": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        }, "required": ["period"]},
    }},
    {"type": "function", "function": {
        "name": "get_receipt",
        "description": "Tautan foto bukti dari Ref ID (mis. 'tg:xyz').",
        "parameters": {"type": "object", "properties": {
            "ref_id": {"type": "string"},
        }, "required": ["ref_id"]},
    }},
]

SYSTEM = (
    "Kamu penjawab pertanyaan keuangan dari Cash Report (sheet TRANSAKSI). Aturan:\n"
    "1. Angka HANYA dari hasil tool — jangan menghitung atau mengingat angka sendiri.\n"
    "2. Angka verified dan draft disebut terpisah; draft bukan angka resmi.\n"
    "3. Transfer antar kantong bukan pemasukan/pengeluaran.\n"
    "4. Sebut sumbernya: periode dan TRANSAKSI.\n"
    "5. Tidak ada data → bilang tidak ada. Singkat, bahasa Indonesia, format Rp40,400.\n"
    "6. Jangan pakai tag HTML atau karakter < > di dalam jawaban."
)


async def _jalankan(name: str, args: dict, load_rows) -> str:
    """Eksekusi tool -> JSON string untuk LLM. Error jadi pesan, bukan exception."""
    try:
        if name == "get_receipt":
            rows = load_rows(str(date.today().year))
            link = find_receipt(rows, str(args.get("ref_id", "")))
            return json.dumps({"link": link} if link else {"error": "Ref ID tidak ditemukan / link kosong"})
        periode = parse_period(str(args.get("period", "")))
        if periode is None:
            return json.dumps({"error": f"periode tidak dikenal: {args.get('period')!r}"})
        awal, akhir = periode
        rows = await asyncio.to_thread(load_rows, str(awal.year))
        if name == "aggregate":
            return json.dumps(aggregate(rows, awal, akhir, args.get("arah"), args.get("kategori")))
        if name == "list_rows":
            return json.dumps(list_rows(
                rows, awal, akhir, args.get("arah"), args.get("kategori"),
                int(args.get("limit") or 15),
            ))
        return json.dumps({"error": f"tool tidak dikenal: {name}"})
    except Exception as e:
        log.warning("Tool %s gagal: %s: %s", name, type(e).__name__, e)
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


async def answer_question(client: httpx.AsyncClient, text: str, load_rows) -> str:
    """Satu percakapan tool-calling (maks 3 putaran) -> balasan teks."""
    key, base, model = _ai()
    if not key:
        return FALLBACK
    messages: list = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": text},
    ]
    for _ in range(3):
        r = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": messages, "tools": TOOLS, "temperature": 0},
            timeout=60,
        )
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        if msg.get("tool_calls"):
            messages.append(msg)
            for tc in msg["tool_calls"]:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                hasil = await _jalankan(tc["function"]["name"], args, load_rows)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": hasil})
            continue
        return (msg.get("content") or "").strip() or FALLBACK
    return "Pertanyaan terlalu rumit — coba lebih spesifik (periode/kategori), atau /rekap."
