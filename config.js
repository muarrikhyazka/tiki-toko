// ═══════════════════════════════════════════════════════════
//  KONFIGURASI TIKI TOKO — isi semua nilai di bawah ini
// ═══════════════════════════════════════════════════════════

// Nomor WhatsApp penjual (format: 62 + nomor tanpa 0 depan)
const WHATSAPP_NUMBER = "6282265135379";

// URL CSV Google Sheet yang sudah dipublish
// Cara: File → Share → Publish to web → pilih sheet → pilih CSV → Publish → copy link
const SHEET_CSV_URL =
  "https://docs.google.com/spreadsheets/d/e/2PACX-1vQV0L-hM14XJNMDkqPi_9j3WV-zXIhzTm7-rRcVM8_XLavMXoeAV7T3Wv3V5s4rGuRvd6HtkMDuPw5r/pub?gid=457971488&single=true&output=csv";

// URL Google Apps Script untuk tracking klik WA (lihat apps-script.js)
const APPS_SCRIPT_URL =
  "https://script.google.com/macros/s/AKfycbxmfbibCQck5LveWHjyMCbMnN1BKOcVE1LoUsdmzG0ng0EM_jyJ8pWDI3dHKULbeqe7/exec";

// URL CSV sheet tracker (File → Share → Publish to web → pilih tab Clicks → CSV)
const TRACKER_CSV_URL =
  "https://docs.google.com/spreadsheets/d/e/2PACX-1vT3fxBlvLLcwJhhLwWGHTeFao9_FPnGPCUrs49FEm0JDJ1-oPdD02ys1_xE_jM9uKwrMgMHc0Z2-gl2/pub?gid=0&single=true&output=csv";

// URL CSV sheet events (File → Share → Publish to web → pilih tab Events → CSV)
// Sheet Events dibuat otomatis oleh Apps Script saat pertama kali ada klik
const EVENTS_CSV_URL =
  "https://docs.google.com/spreadsheets/d/e/2PACX-1vT3fxBlvLLcwJhhLwWGHTeFao9_FPnGPCUrs49FEm0JDJ1-oPdD02ys1_xE_jM9uKwrMgMHc0Z2-gl2/pub?gid=744777442&single=true&output=csv";

// Password halaman dashboard
const DASHBOARD_PASSWORD = "tiki123";
