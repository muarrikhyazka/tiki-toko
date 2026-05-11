#!/usr/bin/env python3
"""
fb_edit_description.py — Tambahkan link WhatsApp ke deskripsi semua listing
                          yang sudah terpublish di Facebook Marketplace.

Install:
    pip install playwright
    playwright install chromium

Jalankan:
    python fb_edit_description.py
    python fb_edit_description.py --dry-run   # preview tanpa edit
"""

import argparse
import json
import random
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


# ── KONFIGURASI ───────────────────────────────────────────────
WHATSAPP_NUMBER = "6282265135379"
WA_SUFFIX       = f"\n\nHubungi via WhatsApp: https://wa.me/{WHATSAPP_NUMBER}"

SESSION_FILE = Path("fb_session.json")
FB_SELLING   = "https://web.facebook.com/marketplace/you/selling"
HEADLESS     = False
# ─────────────────────────────────────────────────────────────


# ── Helpers ───────────────────────────────────────────────────

def _delay(lo=0.5, hi=1.5):
    time.sleep(random.uniform(lo, hi))


def _dismiss_popup(page):
    for sel in ['[aria-label="Close"]', 'div[role="dialog"] [aria-label="Close"]']:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                el.click()
                _delay(0.5, 1)
                return True
        except Exception:
            continue
    return False


def _try_click(page, selectors: list[str], timeout=5000) -> bool:
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


# ── Session / Login ───────────────────────────────────────────

def load_session(context) -> bool:
    if SESSION_FILE.exists():
        context.add_cookies(json.loads(SESSION_FILE.read_text()))
        return True
    return False


def save_session(context):
    SESSION_FILE.write_text(json.dumps(context.cookies(), indent=2))


def ensure_logged_in(page, context):
    page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=30000)
    _delay(2, 3)
    try:
        page.get_by_role("button", name="Log In", exact=False).wait_for(timeout=4000)
        already = False
    except PlaywrightTimeout:
        already = True

    if already:
        print("✓ Sudah login ke Facebook.")
        save_session(context)
        return

    print("\n⚠  Belum login. Silakan login di browser, lalu tekan Enter...")
    input()
    save_session(context)
    print("✓ Login berhasil.")


# ── Kumpulkan semua listing published ─────────────────────────

def collect_published_listings(page) -> list[dict]:
    """
    Scroll halaman selling dan kumpulkan semua listing published
    (yang punya tombol 'More options for ...').
    Return list of {"title": str, "element_index": int}
    """
    print("  Scroll halaman untuk memuat semua listing...")
    prev_count = 0
    for _ in range(15):  # maks 15x scroll
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _delay(1.5, 2.5)
        count = page.locator('[aria-label^="More options for"]').count()
        if count == prev_count:
            break
        prev_count = count

    count = page.locator('[aria-label^="More options for"]').count()
    listings = []
    for i in range(count):
        try:
            btn = page.locator('[aria-label^="More options for"]').nth(i)
            label = btn.get_attribute("aria-label") or ""
            title = label.replace("More options for ", "").strip()
            listings.append({"title": title, "index": i})
        except Exception:
            continue

    print(f"  Ditemukan {len(listings)} listing published.")
    return listings


# ── Edit deskripsi satu listing ───────────────────────────────

def _open_more_details(page):
    """Klik 'More details' untuk membuka section deskripsi."""
    try:
        btn = page.get_by_role("button", name="More details", exact=False)
        if btn.is_visible(timeout=3000):
            btn.click()
            _delay(0.8, 1.5)
            return True
    except Exception:
        pass
    return _try_click(page, [':text("More details")', ':text("Detail lainnya")'], timeout=3000)


def edit_description(page, title: str, dry_run: bool) -> bool:
    """
    Buka More options → Edit listing, tambahkan WA di deskripsi, lalu Save.
    """
    print(f"\n  Edit: {title[:60]}")

    # Klik More options untuk listing ini (cari berdasarkan aria-label exact)
    try:
        more_btn = page.locator(f'[aria-label="More options for {title}"]').first
        more_btn.wait_for(state="visible", timeout=5000)
        more_btn.click()
        _delay(0.8, 1.5)
    except Exception as e:
        print(f"    ✗ Gagal klik More options: {e}")
        return False

    # Klik "Edit listing" di dialog yang muncul
    edit_clicked = _try_click(page, [
        ':text("Edit listing")',
        ':text("Edit Listing")',
        '[role="menuitem"]:has-text("Edit")',
    ], timeout=5000)

    if not edit_clicked:
        print("    ✗ Opsi 'Edit listing' tidak ditemukan.")
        page.keyboard.press("Escape")
        _delay(0.5, 1)
        return False

    _delay(3, 5)
    _dismiss_popup(page)

    # Pastikan sudah di halaman edit
    if "edit" not in page.url and "create" not in page.url:
        print(f"    ✗ Tidak di halaman edit. URL: {page.url}")
        return False

    # Buka More details untuk akses deskripsi
    _open_more_details(page)

    # Ambil isi deskripsi saat ini
    current_desc = ""
    desc_el = None
    try:
        desc_el = page.get_by_label("Description", exact=True)
        desc_el.wait_for(state="visible", timeout=5000)
        current_desc = desc_el.input_value()
    except Exception:
        try:
            desc_el = page.locator('label:has-text("Description") textarea').first
            if desc_el.is_visible(timeout=3000):
                current_desc = desc_el.input_value()
        except Exception:
            pass

    if desc_el is None:
        print("    ✗ Field Description tidak ditemukan.")
        return False

    # Cek apakah WA sudah ada
    wa_url = f"wa.me/{WHATSAPP_NUMBER}"
    if wa_url in current_desc:
        print("    ℹ  Link WA sudah ada di deskripsi, dilewati.")
        page.keyboard.press("Escape")
        return True

    new_desc = current_desc.rstrip() + WA_SUFFIX

    if dry_run:
        print(f"    [DRY-RUN] Deskripsi baru:\n      {new_desc[-120:]}")
        page.keyboard.press("Escape")
        return True

    # Isi deskripsi baru
    try:
        desc_el.click()
        _delay(0.2, 0.4)
        desc_el.fill(new_desc)
        _delay(1, 2)
    except Exception as e:
        print(f"    ✗ Gagal mengisi deskripsi: {e}")
        return False

    # Klik Save / Update
    saved = False
    for name_try in ["Save", "Update", "Simpan", "Publish", "Done"]:
        try:
            btn = page.get_by_role("button", name=name_try, exact=False)
            if btn.is_visible(timeout=3000):
                btn.click()
                _delay(3, 5)
                saved = True
                break
        except PlaywrightTimeout:
            continue

    if saved:
        print("    ✓ Deskripsi berhasil diupdate!")
    else:
        print("    ✗ Tombol Save tidak ditemukan.")
        page.screenshot(path=f"fb_edit_error_{title[:20].replace(' ','_')}.png")

    return saved


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Tambah link WA ke deskripsi listing Facebook Marketplace"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview perubahan tanpa benar-benar menyimpan")
    args = parser.parse_args()

    label = " (DRY-RUN)" if args.dry_run else ""
    print(f"FB Edit Description{label}")
    print("=" * 50)

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

        load_session(context)
        ensure_logged_in(page, context)

        # Buka halaman selling
        print(f"\nMembuka halaman selling...")
        page.goto(FB_SELLING, wait_until="domcontentloaded", timeout=30000)
        _delay(3, 5)
        _dismiss_popup(page)

        listings = collect_published_listings(page)
        if not listings:
            print("Tidak ada listing published yang ditemukan.")
            browser.close()
            return

        print(f"\nAkan mengupdate {len(listings)} listing{label}:\n")
        for l in listings:
            print(f"  - {l['title'][:70]}")

        if not args.dry_run:
            print("\nTekan Enter untuk mulai, Ctrl+C untuk batal...")
            try:
                input()
            except KeyboardInterrupt:
                print("\nDibatalkan.")
                browser.close()
                return

        ok = fail = skip = 0
        for listing in listings:
            title = listing["title"]

            # Pastikan kembali ke halaman selling sebelum setiap edit
            if FB_SELLING not in page.url:
                page.goto(FB_SELLING, wait_until="domcontentloaded", timeout=30000)
                _delay(2, 4)
                _dismiss_popup(page)

            result = edit_description(page, title, dry_run=args.dry_run)

            if result is True:
                ok += 1
            elif "dilewati" in str(result):
                skip += 1
            else:
                fail += 1

            # Kembali ke halaman selling
            page.goto(FB_SELLING, wait_until="domcontentloaded", timeout=30000)
            _delay(2, 3)
            _dismiss_popup(page)

        browser.close()

    print("\n" + "=" * 50)
    print(f"Selesai: {ok} berhasil, {fail} gagal, {skip} dilewati (WA sudah ada).")


if __name__ == "__main__":
    main()
