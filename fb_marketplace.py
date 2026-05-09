#!/usr/bin/env python3
"""
fb_marketplace.py — Post produk Tiki Toko ke Facebook Marketplace

Install:
    pip install playwright python-dotenv requests
    playwright install chromium

Setup:
    cp .env.example .env
    # lalu isi FB_EMAIL dan FB_PASSWORD di file .env

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

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

load_dotenv()


# ── KONFIGURASI ───────────────────────────────────────────────
# Salin SHEET_CSV_URL dari config.js
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQV0L-hM14XJNMDkqPi_9j3WV-zXIhzTm7-rRcVM8_XLavMXoeAV7T3Wv3V5s4rGuRvd6HtkMDuPw5r/pub?gid=457971488&single=true&output=csv"

# Akun Facebook — dibaca dari .env (FB_EMAIL dan FB_PASSWORD)
FB_EMAIL      = os.getenv("FB_EMAIL", "")
FB_PASSWORD   = os.getenv("FB_PASSWORD", "")

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
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    _delay(2, 3)

    # Cek sudah login: kalau ada tombol Login, berarti belum
    try:
        page.get_by_role("button", name="Log In", exact=False).wait_for(timeout=4000)
        already = False
    except PlaywrightTimeout:
        already = True

    if already:
        print("✓ Sudah login ke Facebook.")
        save_session(context)
        return

    # Coba auto-login jika kredensial sudah diisi di konfigurasi
    has_creds = bool(FB_EMAIL and FB_PASSWORD)

    if has_creds:
        print("  Mencoba auto-login...")
        try:
            # Tunggu field email benar-benar muncul dan siap
            email_field = page.locator('input[name="email"]')
            email_field.wait_for(state="visible", timeout=8000)
            email_field.click()
            _delay(0.3, 0.6)
            email_field.fill(FB_EMAIL)
            _delay(0.5, 1)

            pass_field = page.locator('input[name="pass"]')
            pass_field.wait_for(state="visible", timeout=5000)
            pass_field.click()
            _delay(0.3, 0.6)
            pass_field.fill(FB_PASSWORD)
            _delay(0.5, 1)

            page.locator('button[name="login"]').click()
            _delay(5, 8)

            # Verifikasi berhasil login: tombol Login sudah hilang
            page.get_by_role("button", name="Log In", exact=False).wait_for(timeout=5000)
            # Masih ada tombol login → gagal
            print("  ⚠  Auto-login gagal (mungkin ada verifikasi tambahan).")
            has_creds = False
        except PlaywrightTimeout:
            # Tombol login sudah hilang → berhasil
            print("✓ Auto-login berhasil.")
            save_session(context)
            return
        except Exception as e:
            print(f"  ⚠  Auto-login error: {e}")
            has_creds = False

    if not has_creds:
        print("\n⚠  Belum login ke Facebook.")
        print("   Browser sudah terbuka — silakan login secara manual.")
        print("   Setelah berhasil masuk, tekan Enter di sini untuk melanjutkan...")
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


# ── Posting ───────────────────────────────────────────────────

def create_listing(page, product: dict, dry_run: bool = False) -> bool:
    no    = product["no"]
    name  = product["name"]
    brand = product["brand"]
    desc  = product["description"]
    price = product["price"]

    # FB max title 99 karakter
    title = f"{name} {brand}".strip()[:99]

    parts = [desc] if desc else []
    parts.append("Kondisi: Bekas (terawat)")
    parts.append("Hubungi via WhatsApp: wa.me/6282265135379")
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
        print("  ⚠  Tidak ada foto di folder images/{no}/ — dilewati.\n")
        return False

    try:
        page.goto(FB_MARKETPLACE, wait_until="domcontentloaded", timeout=30000)
        _delay(3, 5)

        # ── 1. Upload foto ────────────────────────────────────
        print("  Mengupload foto...")
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files([str(p) for p in images[:20]])  # FB max 20 foto
        _delay(4, 7)

        # ── 2. Judul ──────────────────────────────────────────
        print("  Mengisi judul...")
        title_sel = [
            '[aria-label="Title"]',
            '[placeholder*="title" i]',
            'input[name="title"]',
        ]
        for sel in title_sel:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=3000):
                    _type(el, title)
                    break
            except Exception:
                continue
        _delay(0.8, 1.5)

        # ── 3. Harga ──────────────────────────────────────────
        print("  Mengisi harga...")
        price_sel = [
            '[aria-label="Price"]',
            '[placeholder*="price" i]',
            'input[name="price"]',
        ]
        for sel in price_sel:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=3000):
                    el.click()
                    el.fill(str(price))
                    break
            except Exception:
                continue
        _delay(0.8, 1.5)

        # ── 4. Kondisi (Used - Good) ──────────────────────────
        print("  Memilih kondisi...")
        try:
            cond_sel = [
                '[aria-label="Condition"]',
                'select[name="condition"]',
            ]
            found = False
            for sel in cond_sel:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2000):
                        el.select_option(label="Used - Good")
                        found = True
                        break
                except Exception:
                    continue

            if not found:
                # Coba dropdown custom FB
                _try_click(page, ['[aria-label*="Condition" i]'], timeout=3000)
                _delay(0.5, 1)
                _try_click(page, [
                    ':text("Used - Good")',
                    ':text("Good")',
                ], timeout=3000)
        except Exception:
            pass  # kondisi bukan field wajib di semua kategori
        _delay(0.8, 1.5)

        # ── 5. Deskripsi ──────────────────────────────────────
        print("  Mengisi deskripsi...")
        desc_sel = [
            '[aria-label="Description"]',
            'textarea[name="description"]',
            '[placeholder*="description" i]',
        ]
        for sel in desc_sel:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=3000):
                    _type(el, full_desc)
                    break
            except Exception:
                continue
        _delay(1, 2)

        # ── 6. Next → Publish ─────────────────────────────────
        print("  Mempublish...")
        try:
            next_btn = page.get_by_role("button", name="Next", exact=False)
            if next_btn.is_visible(timeout=3000):
                next_btn.click()
                _delay(2, 4)
        except PlaywrightTimeout:
            pass

        pub_btn = None
        for name_try in ["Publish", "Post", "Done"]:
            try:
                btn = page.get_by_role("button", name=name_try, exact=False)
                if btn.is_visible(timeout=3000):
                    pub_btn = btn
                    break
            except PlaywrightTimeout:
                continue

        if pub_btn:
            pub_btn.click()
            _delay(4, 7)
            print("  ✓ Berhasil dipost!\n")
            return True
        else:
            print("  ✗ Tombol Publish tidak ditemukan — screenshot disimpan.\n")
            page.screenshot(path=f"fb_error_{no}.png")
            return False

    except PlaywrightTimeout as e:
        print(f"  ✗ Timeout: {e}\n")
        page.screenshot(path=f"fb_error_{no}.png")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}\n")
        try:
            page.screenshot(path=f"fb_error_{no}.png")
        except Exception:
            pass
        return False


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

    posted = set() if args.reset else load_posted()

    if args.id:
        products = [p for p in products if p["id"] == args.id]
        if not products:
            print(f"Produk ID {args.id} tidak ditemukan di sheet.")
            return
        to_post = products
    else:
        to_post = [p for p in products if p["id"] not in posted]

    if not to_post:
        print("Semua produk sudah pernah dipost.")
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

        browser.close()

    print("=" * 50)
    print(f"Selesai: {ok} berhasil, {fail} gagal.")
    if not args.dry_run and posted:
        print(f"Total sudah dipost: {len(posted)} produk.")


if __name__ == "__main__":
    main()
