/**
 * Apps Script Web App — pengganti OAuth untuk operasi Drive yang membuat file.
 *
 * Latar: service account tidak bisa membuat file (kuota 0, storageQuotaExceeded),
 * dan OAuth user status Testing kedaluwarsa tiap 7 hari. Web App ini berjalan
 * sebagai akun pemilik (Execute as: Me) tanpa token yang kedaluwarsa.
 *
 * Tanggung jawab (4 aksi — operasi sel spreadsheet tetap di service account):
 *   folder         cari/buat folder tahun di dalam folder induk
 *   copy_template  cari/buat "Cash Report {tahun}" dari template (LockService:
 *                  dua upload bersamaan tidak boleh membuat file ganda)
 *   upload         simpan foto bukti (base64) ke folder Receipts
 *   create_sheet   spreadsheet kosong (bootstrap TEMPLATE di build_template.py)
 *
 * Setup (sekali, ±5 menit):
 *   1. script.google.com → New project → tempel file ini.
 *   2. Project Settings → Script Properties → tambah SECRET = <nilai rahasia>.
 *   3. Deploy → New deployment → Web app:
 *      Execute as: Me · Who has access: Anyone → Deploy → salin /exec URL.
 *   4. Env bot: APPS_SCRIPT_URL=<URL /exec> dan APPS_SCRIPT_SECRET=<SECRET>.
 *
 * Kontrak: POST JSON {secret, action, ...payload} → balasan JSON
 *   sukses: {ok:true, data:{...}}
 *   gagal : {ok:false, error:"..."} (HTTP tetap 200 — isi yang menentukan)
 */

var SCRIPT_PROP_SECRET = 'SECRET';

function doPost(e) {
  var res;
  try {
    var req = JSON.parse(e.postData.contents);
    var expected = PropertiesService.getScriptProperties().getProperty(SCRIPT_PROP_SECRET);
    if (!expected || req.secret !== expected) {
      res = { ok: false, error: 'secret salah / tidak diset di Script Properties' };
    } else {
      var data;
      if (req.action === 'folder') {
        data = aksiFolder(req);
      } else if (req.action === 'copy_template') {
        data = aksiCopyTemplate(req);
      } else if (req.action === 'upload') {
        data = aksiUpload(req);
      } else if (req.action === 'create_sheet') {
        data = aksiCreateSheet(req);
      } else {
        data = null;
        res = { ok: false, error: 'action tidak dikenal: ' + req.action };
      }
      if (data) res = { ok: true, data: data };
    }
  } catch (err) {
    res = { ok: false, error: String(err && err.message ? err.message : err) };
  }
  return ContentService.createTextOutput(JSON.stringify(res))
    .setMimeType(ContentService.MimeType.JSON);
}

function folderInduk(parentId) {
  if (!parentId) throw new Error('parent_id kosong');
  return DriveApp.getFolderById(parentId);
}

/** {action:"folder", name, parent_id} -> {id, name} */
function aksiFolder(req) {
  var parent = folderInduk(req.parent_id);
  var it = parent.getFoldersByName(req.name);
  while (it.hasNext()) {
    var f = it.next();
    if (!f.isTrashed()) return { id: f.getId(), name: f.getName() };
  }
  var baru = parent.createFolder(req.name);
  return { id: baru.getId(), name: baru.getName() };
}

/** {action:"copy_template", name, parent_id, template_id} ->
 *  {id, name, link, created} — LockService mencegah file ganda saat deploy/
 *  upload ganda. created=false bila file sudah ada (idempoten). */
function aksiCopyTemplate(req) {
  if (!req.template_id) throw new Error('template_id kosong');
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var parent = folderInduk(req.parent_id);
    var files = parent.getFilesByName(req.name);
    while (files.hasNext()) {
      var f = files.next();
      if (!f.isTrashed() && f.getMimeType() === MimeType.GOOGLE_SHEETS) {
        return { id: f.getId(), name: f.getName(), link: f.getUrl(), created: false };
      }
    }
    var copy = DriveApp.getFileById(req.template_id).makeCopy(req.name, parent);
    return { id: copy.getId(), name: copy.getName(), link: copy.getUrl(), created: true };
  } finally {
    lock.releaseLock();
  }
}

/** {action:"upload", filename, folder_id, content_base64} -> {id, link} */
function aksiUpload(req) {
  var folder = folderInduk(req.folder_id);
  var bytes = Utilities.base64Decode(req.content_base64);
  var blob = Utilities.newBlob(bytes, req.mime || 'image/jpeg', req.filename);
  var file = folder.createFile(blob);
  return { id: file.getId(), link: file.getUrl() };
}

/** {action:"create_sheet", name, parent_id} -> {id, link, created}
 *  Spreadsheet kosong (bootstrap TEMPLATE; spreadsheet operasional memakai
 *  copy_template). created=false bila sudah ada (idempoten). */
function aksiCreateSheet(req) {
  var parent = folderInduk(req.parent_id);
  var files = parent.getFilesByName(req.name);
  while (files.hasNext()) {
    var f = files.next();
    if (!f.isTrashed() && f.getMimeType() === MimeType.GOOGLE_SHEETS) {
      return { id: f.getId(), link: f.getUrl(), created: false };
    }
  }
  var ss = SpreadsheetApp.create(req.name);
  DriveApp.getFileById(ss.getId()).moveTo(parent);
  return { id: ss.getId(), link: ss.getUrl(), created: true };
}
