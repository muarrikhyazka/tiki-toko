/**
 * TIKI TOKO — Google Apps Script (Tracker Klik WA)
 *
 * ═══════════════════════════════════════════════════
 *  CARA SETUP (lakukan sekali saja):
 * ═══════════════════════════════════════════════════
 *
 *  1. Buka Google Sheets → buka spreadsheet tracker
 *     Rename tab pertama menjadi persis: Clicks
 *     Isi baris 1 (header):
 *       A1: product_id  |  B1: product_name  |  C1: product_clicks
 *       D1: wa_clicks   |  E1: last_click     |  F1: sold
 *
 *  2. Di Google Sheets: Extensions → Apps Script
 *     Hapus semua kode yang ada
 *     Paste SELURUH kode di file ini
 *     Simpan dengan nama project: Tiki Toko Tracker  (Ctrl+S)
 *
 *  3. Klik "Deploy" → "New deployment"
 *       Type          : Web App
 *       Execute as    : Me
 *       Who has access: Anyone
 *     Klik "Deploy" → klik "Authorize access" jika muncul popup
 *
 *  4. Copy URL yang muncul (bentuknya: https://script.google.com/macros/s/.../exec)
 *
 *  5. Paste URL tersebut ke  config.js  →  APPS_SCRIPT_URL
 *
 * ⚠  Setiap kali kamu mengedit kode ini, buat deployment BARU
 *    (Deploy → New deployment), jangan edit yang lama.
 * ═══════════════════════════════════════════════════
 */

// ── PASTE KODE DI BAWAH INI KE APPS SCRIPT EDITOR ──────────

const SHEET_NAME        = "Clicks";
const EVENTS_SHEET_NAME = "Events";

function doGet(e) {
  const action = (e && e.parameter && e.parameter.action) || "ping";

  try {
    const sheet = SpreadsheetApp
      .getActiveSpreadsheet()
      .getSheetByName(SHEET_NAME);

    if (!sheet) {
      return jsonOut({
        error: `Sheet "${SHEET_NAME}" tidak ditemukan. Buat tab dengan nama persis "Clicks".`
      });
    }

    if (action === "click") {
      const id        = parseInt(e.parameter.id)        || 0;
      const name      = (e.parameter.name || "").trim();
      const clickType = (e.parameter.type || "wa").trim(); // "product" atau "wa"
      if (id > 0) recordClick(sheet, id, name, clickType);
      return jsonOut({ success: true });
    }

    if (action === "markSold") {
      const id   = parseInt(e.parameter.id) || 0;
      const name = (e.parameter.name || "").trim();
      if (id > 0) setSold(sheet, id, name, true);
      return jsonOut({ success: true });
    }

    if (action === "unmarkSold") {
      const id = parseInt(e.parameter.id) || 0;
      if (id > 0) setSold(sheet, id, "", false);
      return jsonOut({ success: true });
    }

    if (action === "getData") {
      return jsonOut(getAllData(sheet));
    }

    if (action === "reset") {
      clearData(sheet);
      return jsonOut({ success: true });
    }

    if (action === "setup") {
      setupFormats(sheet);
      getOrCreateEventsSheet();
      return jsonOut({ success: true, message: "Format kolom sudah diperbaiki." });
    }

    if (action === "resetEvents") {
      const ev = getOrCreateEventsSheet();
      const last = ev.getLastRow();
      if (last > 1) ev.getRange(2, 1, last - 1, 4).clearContent();
      return jsonOut({ success: true });
    }

    return jsonOut({ status: "ok", sheet: SHEET_NAME });

  } catch (err) {
    return jsonOut({ error: err.message });
  }
}

function getOrCreateEventsSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let ev = ss.getSheetByName(EVENTS_SHEET_NAME);
  if (!ev) {
    ev = ss.insertSheet(EVENTS_SHEET_NAME);
    ev.getRange("A1:D1").setValues([["timestamp", "product_id", "product_name", "click_type"]]);
    ev.getRange("A:A").setNumberFormat("@");  // simpan sebagai teks agar tidak diubah ke Date
    ev.getRange("B:B").setNumberFormat("0");
    ev.getRange("C:C").setNumberFormat("@");
    ev.getRange("D:D").setNumberFormat("@");
  }
  return ev;
}

function recordEvent(productId, productName, clickType) {
  const ev = getOrCreateEventsSheet();
  ev.appendRow([new Date().toISOString(), productId, productName, clickType]);
}

function safeInt(val) {
  // Aman membaca nilai dari sheet: tangani Date object, string, null, dll.
  if (val instanceof Date) return 0;
  const n = parseInt(val);
  return isNaN(n) || n < 0 ? 0 : n;
}

function setupFormats(sheet) {
  // Paksa format kolom agar tidak auto-convert angka jadi tanggal
  sheet.getRange("A:A").setNumberFormat("0");          // product_id  → angka
  sheet.getRange("B:B").setNumberFormat("@");          // product_name → teks
  sheet.getRange("C:C").setNumberFormat("0");          // product_clicks → angka
  sheet.getRange("D:D").setNumberFormat("0");          // wa_clicks → angka
  sheet.getRange("E:E").setNumberFormat("yyyy-MM-dd HH:mm:ss"); // last_click → datetime
  sheet.getRange("F:F").setNumberFormat("@");          // sold → teks
}

function recordClick(sheet, productId, productName, clickType) {
  const values = sheet.getDataRange().getValues();
  let found = false;

  for (let i = 1; i < values.length; i++) {
    if (Number(values[i][0]) === productId) {
      if (clickType === "product") {
        sheet.getRange(i + 1, 3).setValue(safeInt(values[i][2]) + 1); // product_clicks (col C)
      } else {
        sheet.getRange(i + 1, 4).setValue(safeInt(values[i][3]) + 1); // wa_clicks (col D)
      }
      sheet.getRange(i + 1, 5).setValue(new Date()); // last_click (col E)
      found = true;
      break;
    }
  }

  if (!found) {
    // Produk baru — append lalu pastikan format kolom benar
    const pClicks = clickType === "product" ? 1 : 0;
    const wClicks = clickType === "wa"      ? 1 : 0;
    sheet.appendRow([productId, productName, pClicks, wClicks, new Date(), false]);
    setupFormats(sheet); // cegah auto-format Date pada baris baru
  }

  recordEvent(productId, productName, clickType); // catat setiap event dengan timestamp
}

function setSold(sheet, productId, productName, isSold) {
  const values = sheet.getDataRange().getValues();

  for (let i = 1; i < values.length; i++) {
    if (Number(values[i][0]) === productId) {
      sheet.getRange(i + 1, 6).setValue(isSold); // sold (col F)
      return;
    }
  }

  // Produk belum ada di sheet — buat baris baru
  sheet.appendRow([productId, productName, 0, 0, new Date(), isSold]);
}

function getAllData(sheet) {
  const values = sheet.getDataRange().getValues();
  const result = [];

  for (let i = 1; i < values.length; i++) {
    const row = values[i];
    if (!row[0]) continue;
    result.push({
      productId    : Number(row[0]),
      productName  : String(row[1] || ""),
      productClicks: Number(row[2] || 0),
      waClicks     : Number(row[3] || 0),
      lastClick    : row[4] instanceof Date ? row[4].toISOString() : null,
      sold         : row[5] === true || row[5] === "TRUE",
    });
  }
  return result;
}

function clearData(sheet) {
  const last = sheet.getLastRow();
  if (last > 1) sheet.getRange(2, 1, last - 1, 6).clearContent();
  setupFormats(sheet); // reset format setelah clear agar kolom tidak kembali ke Date
}

function jsonOut(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
