#!/usr/bin/env python3
"""
fb_marketplace.py — Post produk Tiki Toko ke Facebook Marketplace

Install:
    pip install playwright requests
    playwright install chromium

Jalankan:
    python fb_marketplace.py              # post semua produk belum dipost
    python fb_marketplace.py --dry-run   # preview tanpa posting
    python fb_marketplace.py --reset     # mulai ulang (hapus riwayat posted)
    python fb_marketplace.py --id 5      # post hanya produk ID 5
"""

import argparse
import csv as csv_module
import io
import json
import os
import random
import time
from pathlib import Path

import requests

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


# ── KONFIGURASI ───────────────────────────────────────────────
# Salin SHEET_CSV_URL dari config.js
SHEET_CSV_URL   = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQV0L-hM14XJNMDkqPi_9j3WV-zXIhzTm7-rRcVM8_XLavMXoeAV7T3Wv3V5s4rGuRvd6HtkMDuPw5r/pub?gid=457971488&single=true&output=csv"
TRACKER_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT3fxBlvLLcwJhhLwWGHTeFao9_FPnGPCUrs49FEm0JDJ1-oPdD02ys1_xE_jM9uKwrMgMHc0Z2-gl2/pub?gid=0&single=true&output=csv"
WHATSAPP_NUMBER = "6282265135379"

IMAGES_DIR    = Path("images")           # folder foto lokal (images/{no}/1.jpg ...)
SESSION_FILE  = Path("fb_session.json")  # cookies login tersimpan
POSTED_FILE   = Path("fb_posted.json")   # ID produk yang sudah dipost

DELAY_BETWEEN = (45, 90)   # jeda acak antar listing (detik) — jangan terlalu cepat
HEADLESS      = False       # False = lihat browser, True = background (tidak direkomendasikan)
# ─────────────────────────────────────────────────────────────

FB_MARKETPLACE = "https://www.facebook.com/marketplace/create/item"
IMAGE_EXTS     = {".jpg", ".jpeg", ".png", ".webp"}


# ── Data Produk ───────────────────────────────────────────────

def fetch_products() -> list[dict]:
    print("Mengambil data produk dari Google Sheet...")
    resp = requests.get(SHEET_CSV_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    text = resp.text

    rows = list(csv_module.reader(io.StringIO(text)))
    if len(rows) < 3:
        raise ValueError("Sheet terlalu sedikit baris (butuh minimal 3: judul, header, data)")

    headers = [h.strip().lower() for h in rows[1]]
    def col(name):
        try:
            return headers.index(name.lower())
        except ValueError:
            return -1

    iNo    = col("no")
    iName  = col("nama barang")
    iTreat = col("treatment")
    iBrand = col("merk/tipe")
    iDesc  = col("deskripsi")
    iPrice = col("harga")

    products = []
    for r in rows[2:]:
        if not r:
            continue
        name  = r[iName].strip()  if iName  >= 0 and iName  < len(r) else ""
        treat = r[iTreat].strip() if iTreat >= 0 and iTreat < len(r) else ""
        if not name or treat.lower() != "dijual":
            continue

        no    = r[iNo].strip()    if iNo    >= 0 and iNo    < len(r) else ""
        brand = r[iBrand].strip() if iBrand >= 0 and iBrand < len(r) else ""
        desc  = r[iDesc].strip()  if iDesc  >= 0 and iDesc  < len(r) else ""
        raw   = r[iPrice].strip() if iPrice >= 0 and iPrice < len(r) else ""
        price = int("".join(c for c in raw if c.isdigit()) or "0")

        products.append({
            "id"         : int(no) if no.isdigit() else 0,
            "no"         : no,
            "name"       : name,
            "brand"      : brand,
            "description": desc,
            "price"      : price,
        })

    print(f"  {len(products)} produk dijual ditemukan.")
    return products


def get_images(no: str) -> list[Path]:
    folder = IMAGES_DIR / no
    if not folder.is_dir():
        return []
    return sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS
    )


# ── Sold IDs dari Tracker Sheet ──────────────────────────────

def fetch_sold_ids() -> set:
    """Kembalikan set product_id yang sudah terjual (sold=TRUE) dari tracker sheet."""
    print("Mengecek produk terjual dari tracker sheet...")
    try:
        resp = requests.get(TRACKER_CSV_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        rows = list(csv_module.reader(io.StringIO(resp.text)))
        if len(rows) < 2:
            return set()
        headers = [h.strip().lower() for h in rows[0]]
        i_id   = headers.index("product_id") if "product_id" in headers else -1
        i_sold = headers.index("sold")        if "sold"       in headers else -1
        if i_id < 0 or i_sold < 0:
            return set()
        sold = set()
        for r in rows[1:]:
            if i_sold < len(r) and r[i_sold].strip().upper() == "TRUE":
                try:
                    sold.add(int(r[i_id]))
                except ValueError:
                    pass
        print(f"  {len(sold)} produk sudah terjual (akan dilewati).")
        return sold
    except Exception as e:
        print(f"  ⚠  Gagal ambil tracker: {e} — tidak ada filter sold.")
        return set()


# ── Riwayat Posted ────────────────────────────────────────────

def load_posted() -> set:
    if POSTED_FILE.exists():
        return set(json.loads(POSTED_FILE.read_text()))
    return set()


def save_posted(posted: set):
    POSTED_FILE.write_text(json.dumps(sorted(posted), indent=2))


# ── Session / Login ───────────────────────────────────────────

def load_session(context) -> bool:
    if SESSION_FILE.exists():
        context.add_cookies(json.loads(SESSION_FILE.read_text()))
        return True
    return False


def save_session(context):
    SESSION_FILE.write_text(json.dumps(context.cookies(), indent=2))
    print("  Session disimpan.")


def ensure_logged_in(page, context):
    page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=30000)
    _delay(2, 3)

    # Kalau session tersimpan sudah valid, FB langsung redirect ke home
    try:
        page.get_by_role("button", name="Log In", exact=False).wait_for(timeout=4000)
        already = False
    except PlaywrightTimeout:
        already = True

    if already:
        print("✓ Sudah login ke Facebook (session tersimpan).")
        save_session(context)
        return

    print("\n⚠  Belum login ke Facebook.")
    print("   Browser sudah terbuka di halaman login.")
    print("   Silakan login secara manual, lalu tekan Enter di sini untuk melanjutkan...")
    input()
    save_session(context)
    print("✓ Login berhasil.")


# ── Helpers ───────────────────────────────────────────────────

def _delay(lo=0.5, hi=1.5):
    time.sleep(random.uniform(lo, hi))


def _type(locator, text: str):
    """Ketik teks dengan jeda acak seperti manusia."""
    locator.click()
    _delay(0.2, 0.5)
    for ch in text:
        locator.type(ch)
        time.sleep(random.uniform(0.03, 0.1))


def _try_click(page, selectors: list[str], timeout=5000) -> bool:
    """Coba klik salah satu selector, return True jika berhasil."""
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=timeout)
            if el and el.is_visible():
                _delay(0.3, 0.6)
                el.click()
                _delay(0.3, 0.6)
                return True
        except PlaywrightTimeout:
            continue
    return False


def _dismiss_popup(page):
    """Tutup popup login atau interstitial yang menghalangi form."""
    for sel in [
        '[aria-label="Close"]',
        'div[role="dialog"] [aria-label="Close"]',
    ]:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                el.click()
                _delay(0.5, 1)
                return True
        except Exception:
            continue
    return False


def _fill_field(page, label: str, value: str) -> bool:
    """Isi input field yang diasosiasikan dengan label teks tertentu."""
    try:
        el = page.get_by_label(label, exact=True)
        el.wait_for(state="visible", timeout=5000)
        el.click()
        _delay(0.2, 0.4)
        el.fill("")
        _type(el, value)
        return True
    except Exception:
        pass
    # Fallback: cari input di dalam label yang mengandung teks tersebut
    try:
        el = page.locator(f'label:has-text("{label}") input, label:has-text("{label}") textarea').first
        if el.is_visible(timeout=3000):
            el.click()
            _delay(0.2, 0.4)
            el.fill("")
            _type(el, value)
            return True
    except Exception:
        pass
    return False


def _select_combobox(page, label: str, options: list[str]) -> bool:
    """Klik combobox dengan label tertentu lalu pilih salah satu opsi yang tersedia."""
    # Coba get_by_label untuk combobox (mendeteksi via aria-labelledby)
    try:
        box = page.get_by_label(label, exact=True)
        box.wait_for(state="visible", timeout=5000)
        box.click()
        _delay(0.5, 1)
    except Exception:
        # Fallback: cari [role="combobox"] di dekat teks label
        try:
            box = page.locator(f'[role="combobox"]:near(:text-is("{label}"))').first
            box.wait_for(state="visible", timeout=3000)
            box.click()
            _delay(0.5, 1)
        except Exception:
            return False

    # Pilih opsi dari dropdown yang muncul
    for opt in options:
        try:
            item = page.locator(f'[role="option"]:has-text("{opt}"), li:has-text("{opt}")').first
            if item.is_visible(timeout=3000):
                item.click()
                _delay(0.3, 0.6)
                return True
        except Exception:
            continue
    # Kalau tidak ada opsi yang cocok, tekan Escape untuk tutup
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    return False


# ── Posting ───────────────────────────────────────────────────

def create_listing(page, product: dict, dry_run: bool = False) -> bool:
    no    = product["no"]
    name  = product["name"]
    brand = product["brand"]
    desc  = product["description"]
    price = product["price"]

    # FB max title 99 karakter
    title = f"{name} {brand}".strip()[:99]

    parts = [brand] if brand else []
    if desc:
        parts.append(desc)
    full_desc = "\n\n".join(parts)

    images = get_images(no)

    print(f"  Judul   : {title}")
    print(f"  Harga   : Rp {price:,}")
    print(f"  Foto    : {len(images)} file")
    print(f"  Deskripsi: {full_desc[:60]}{'...' if len(full_desc) > 60 else ''}")

    if dry_run:
        print("  [DRY-RUN] Dilewati.\n")
        return True

    if not images:
        print(f"  ⚠  Tidak ada foto di folder images/{no}/ — dilewati.\n")
        return False

    try:
        page.goto(FB_MARKETPLACE, wait_until="domcontentloaded", timeout=30000)
        _delay(3, 5)

        # Tutup popup login jika muncul
        _dismiss_popup(page)

        # Pastikan sudah di halaman create (bukan redirect ke browse)
        if "create" not in page.url:
            print("  ✗ FB redirect ke halaman lain, bukan form create listing.")
            print(f"     URL saat ini: {page.url}")
            page.screenshot(path=f"fb_error_{no}.png")
            return False

        # ── 1. Upload foto ────────────────────────────────────
        print("  Mengupload foto...")
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files([str(p) for p in images[:20]])  # FB max 20 foto
        _delay(5, 8)
        _dismiss_popup(page)

        # ── 2. Judul ──────────────────────────────────────────
        print("  Mengisi judul...")
        if not _fill_field(page, "Title", title):
            print("  ⚠  Field Title tidak ditemukan, coba lanjut...")
        _delay(0.8, 1.5)

        # ── 3. Harga ──────────────────────────────────────────
        print("  Mengisi harga...")
        if not _fill_field(page, "Price", str(price)):
            print("  ⚠  Field Price tidak ditemukan, coba lanjut...")
        _delay(0.8, 1.5)

        # ── 4. Kondisi (Used - Good) ──────────────────────────
        print("  Memilih kondisi...")
        _select_combobox(page, "Condition", ["Used - Good", "Good", "Bekas - Bagus"])
        _delay(0.8, 1.5)

        # ── 5. Deskripsi (via More details) ──────────────────
        print("  Mengisi deskripsi...")
        try:
            more = page.get_by_role("button", name="More details", exact=False)
            if not more.is_visible(timeout=3000):
                raise Exception("tidak visible")
            more.click()
            _delay(0.8, 1.5)
        except Exception:
            # Coba text selector sebagai fallback
            _try_click(page, [':text("More details")', ':text("Detail lainnya")'], timeout=3000)
            _delay(0.8, 1.5)

        if not _fill_field(page, "Description", full_desc):
            try:
                ta = page.locator("textarea").first
                if ta.is_visible(timeout=3000):
                    ta.click()
                    _delay(0.2, 0.4)
                    ta.fill(full_desc)
            except Exception:
                print("  ⚠  Field Description tidak ditemukan, lanjut tanpa deskripsi...")
        _delay(1, 2)

        # ── 6. Availability ───────────────────────────────────
        print("  Memilih availability...")
        _select_combobox(page, "Availability", ["List as Single Item"])
        _delay(0.8, 1.5)

        # ── 7. Lokasi ─────────────────────────────────────────
        print("  Mengisi lokasi...")
        try:
            loc_el = page.get_by_label("Location", exact=True)
            if not loc_el.is_visible(timeout=4000):
                raise Exception("tidak visible")
            loc_el.click()
            _delay(0.3, 0.6)
            loc_el.fill("")
            loc_el.type("Kendari", delay=80)
            _delay(1.5, 2.5)
            suggestion = page.locator('[role="option"]:has-text("Kendari"), li:has-text("Kendari")').first
            suggestion.wait_for(state="visible", timeout=5000)
            suggestion.click()
            _delay(0.5, 1)
        except Exception:
            print("  ⚠  Field Location tidak ditemukan atau 'Kendari' tidak muncul, lanjut...")

        # ── 7. Save draft ─────────────────────────────────────
        print("  Menyimpan draft...")
        saved = _try_click(page, [
            '[aria-label="Save draft"]',
            '[role="button"][aria-label="Save draft"]',
        ], timeout=5000)

        if not saved:
            try:
                btn = page.get_by_role("button", name="Save draft", exact=False)
                if btn.is_visible(timeout=3000):
                    btn.click()
                    saved = True
            except Exception:
                pass

        if saved:
            _delay(3, 5)
            print("  ✓ Draft disimpan!\n")
            return True
        else:
            print("  ✗ Tombol Save draft tidak ditemukan — screenshot disimpan.\n")
            page.screenshot(path=f"fb_error_{no}.png")
            return False

    except PlaywrightTimeout as e:
        print(f"  ✗ Timeout: {e}\n")
        try:
            page.screenshot(path=f"fb_error_{no}.png")
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}\n")
        try:
            page.screenshot(path=f"fb_error_{no}.png")
        except Exception:
            pass
        return False


# ── Publish Drafts ────────────────────────────────────────────

FB_SELLING = "https://web.facebook.com/marketplace/you/selling"


def publish_drafts(page):
    """Buka halaman selling, klik Continue satu per satu pada semua draft."""
    print("\n" + "=" * 50)
    print("Membuka halaman daftar draft...")
    page.goto(FB_SELLING, wait_until="domcontentloaded", timeout=30000)
    _delay(3, 5)
    _dismiss_popup(page)

    published = 0
    while True:
        # Ambil semua tombol Continue yang ada di halaman saat ini
        continue_btns = page.locator('[aria-label="Continue"]')
        count = continue_btns.count()
        if count == 0:
            print("  Tidak ada draft lagi yang perlu dipublish.")
            break

        print(f"  Ditemukan {count} draft — klik Continue pertama...")
        btn = continue_btns.first
        try:
            btn.wait_for(state="visible", timeout=5000)
            href = btn.get_attribute("href") or ""
            btn.click()
            _delay(3, 5)
            _dismiss_popup(page)

            # Klik Publish jika muncul di halaman edit
            pub_found = False
            for name_try in ["Publish", "Post", "Done", "Selesai"]:
                try:
                    pub = page.get_by_role("button", name=name_try, exact=False)
                    if pub.is_visible(timeout=5000):
                        pub.click()
                        _delay(3, 5)
                        pub_found = True
                        published += 1
                        print(f"  ✓ Draft dipublish! (total: {published})")
                        break
                except PlaywrightTimeout:
                    continue

            if not pub_found:
                print("  ⚠  Tombol Publish tidak ditemukan setelah Continue.")
                page.screenshot(path=f"fb_publish_error_{published+1}.png")

            # Kembali ke halaman selling untuk proses draft berikutnya
            page.goto(FB_SELLING, wait_until="domcontentloaded", timeout=30000)
            _delay(2, 4)
            _dismiss_popup(page)

        except Exception as e:
            print(f"  ✗ Error saat publish draft: {e}")
            page.screenshot(path=f"fb_publish_error_{published+1}.png")
            page.goto(FB_SELLING, wait_until="domcontentloaded", timeout=30000)
            _delay(2, 4)

    print(f"Selesai publish draft: {published} listing dipublish.")
    return published


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Post produk Tiki Toko ke Facebook Marketplace"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview produk tanpa benar-benar posting")
    parser.add_argument("--reset", action="store_true",
                        help="Hapus riwayat posted dan mulai dari awal")
    parser.add_argument("--id", type=int, metavar="PRODUCT_ID",
                        help="Post hanya satu produk dengan ID tertentu")
    args = parser.parse_args()

    if SHEET_CSV_URL == "YOUR_SHEET_CSV_URL_HERE":
        print("ERROR: Isi SHEET_CSV_URL di bagian KONFIGURASI atas script ini.")
        return

    products = fetch_products()
    if not products:
        print("Tidak ada produk untuk dipost.")
        return

    sold_ids = fetch_sold_ids()
    products = [p for p in products if p["id"] not in sold_ids]
    if not products:
        print("Semua produk sudah terjual.")
        return

    posted = set() if args.reset else load_posted()

    if args.id:
        products = [p for p in products if p["id"] == args.id]
        if not products:
            print(f"Produk ID {args.id} tidak ditemukan atau sudah terjual.")
            return
        to_post = products
    else:
        to_post = [p for p in products if p["id"] not in posted]

    if not to_post:
        print("Semua produk (yang belum terjual) sudah pernah dipost.")
        print("Gunakan --reset untuk memulai ulang dari awal.")
        return

    label = " (DRY-RUN)" if args.dry_run else ""
    print(f"\nAkan mempost {len(to_post)} produk{label}:\n")
    for p in to_post:
        imgs = len(get_images(p["no"]))
        status = "(sudah posted)" if p["id"] in posted else ""
        print(f"  [{p['id']:3}] {p['name'][:45]:<45}  {imgs} foto  {status}")

    if not args.dry_run:
        print("\nTekan Enter untuk mulai, Ctrl+C untuk batal...")
        try:
            input()
        except KeyboardInterrupt:
            print("\nDibatalkan.")
            return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=HEADLESS, slow_mo=60)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        if not args.dry_run:
            load_session(context)
            ensure_logged_in(page, context)

        ok = fail = 0
        for i, product in enumerate(to_post, 1):
            print(f"\n[{i}/{len(to_post)}] {product['name']}")
            print("-" * 50)

            success = create_listing(page, product, dry_run=args.dry_run)

            if success:
                ok += 1
                if not args.dry_run:
                    posted.add(product["id"])
                    save_posted(posted)
            else:
                fail += 1

            if i < len(to_post) and not args.dry_run:
                delay = random.randint(*DELAY_BETWEEN)
                print(f"  Menunggu {delay} detik sebelum listing berikutnya...")
                time.sleep(delay)

        if not args.dry_run and ok > 0:
            publish_drafts(page)

        browser.close()

    print("=" * 50)
    print(f"Selesai: {ok} berhasil disimpan draft, {fail} gagal.")
    if not args.dry_run and posted:
        print(f"Total sudah dipost: {len(posted)} produk.")


if __name__ == "__main__":
    main()
