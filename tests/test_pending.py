"""Test antrean pending: retry, notifikasi sekali, dan ketahanan baris rusak."""
import asyncio
import json

import main


def _tulis(file, *records):
    file.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def test_sukses_mengosongkan_antrean_dan_memberi_notif(tmp_path, monkeypatch):
    f = tmp_path / "pending.jsonl"
    _tulis(f, {"keterangan": "kopi", "nominal": 12000, "chat_id": 42})
    monkeypatch.setattr(main, "PENDING", f)
    monkeypatch.setattr(
        main, "write_cash_report",
        lambda rec, *a, **k: {"status": "ok", "worksheet": "TRANSAKSI", "row": 9, "link": ""},
    )
    kirim = []
    monkeypatch.setattr(
        main, "tg_send",
        lambda client, chat_id, text: kirim.append((chat_id, text)) or asyncio.sleep(0),
    )

    sisa = asyncio.run(main.flush_pending(None))

    assert sisa == 0
    assert not f.exists()  # antrean kosong -> file dihapus (health pending=false)
    assert len(kirim) == 1
    assert kirim[0][0] == 42
    assert "berhasil tercatat" in kirim[0][1] and "baris 9" in kirim[0][1]


def test_gagal_diberi_tahu_sekali_saja(tmp_path, monkeypatch):
    f = tmp_path / "pending.jsonl"
    _tulis(f, {"keterangan": "kopi", "chat_id": 7})
    monkeypatch.setattr(main, "PENDING", f)

    def gagal(rec, *a, **k):
        raise RuntimeError("sheet mati")

    monkeypatch.setattr(main, "write_cash_report", gagal)
    kirim = []
    monkeypatch.setattr(
        main, "tg_send",
        lambda client, chat_id, text: kirim.append((chat_id, text)) or asyncio.sleep(0),
    )

    asyncio.run(main.flush_pending(None))
    asyncio.run(main.flush_pending(None))
    asyncio.run(main.flush_pending(None))

    assert f.exists()  # masih mengantre
    rec = json.loads(f.read_text(encoding="utf-8").splitlines()[0])
    assert rec["_notif"] is True          # penanda sudah pernah diberi tahu
    assert "retry gagal" in rec["_error"]
    gagal_kirim = [t for _, t in kirim if "gagal" in t]
    assert len(gagal_kirim) == 1          # notif sekali, siklus berikutnya senyap


def test_record_tanpa_chat_id_lewat_tanpa_notif(tmp_path, monkeypatch):
    f = tmp_path / "pending.jsonl"
    _tulis(f, {"keterangan": "via API", "nominal": 5000})  # jalur /api/extract
    monkeypatch.setattr(main, "PENDING", f)
    monkeypatch.setattr(
        main, "write_cash_report",
        lambda rec, *a, **k: {"status": "ok", "worksheet": "TRANSAKSI", "row": 3, "link": ""},
    )
    kirim = []
    monkeypatch.setattr(
        main, "tg_send",
        lambda client, chat_id, text: kirim.append((chat_id, text)) or asyncio.sleep(0),
    )

    sisa = asyncio.run(main.flush_pending(None))

    assert sisa == 0
    assert kirim == []  # tidak ada chat asal -> tidak ada notifikasi


def test_baris_rusak_disimpan_bukan_dibuang(tmp_path, monkeypatch):
    f = tmp_path / "pending.jsonl"
    f.write_text("{json rusak\n", encoding="utf-8")
    monkeypatch.setattr(main, "PENDING", f)

    sisa = asyncio.run(main.flush_pending(None))

    assert sisa == 1
    assert f.read_text(encoding="utf-8").strip() == "{json rusak"


def test_push_pending_menyimpan_chat_id(tmp_path, monkeypatch):
    f = tmp_path / "pending.jsonl"
    monkeypatch.setattr(main, "PENDING", f)

    main.push_pending({"keterangan": "x"}, "boom", chat_id=555)

    rec = json.loads(f.read_text(encoding="utf-8").splitlines()[0])
    assert rec["chat_id"] == 555
    assert rec["_error"] == "boom"
