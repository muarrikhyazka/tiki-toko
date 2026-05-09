#!/usr/bin/env python3
"""
Tambahkan watermark ke semua gambar dan video, lalu rename ke urutan angka.

Install:
    pip install Pillow
    ffmpeg (untuk video):
        macOS  : brew install ffmpeg
        Ubuntu : sudo apt install ffmpeg
        Windows: https://ffmpeg.org/download.html

Jalankan (BATCH — proses semua subfolder sekaligus):
    python watermark.py images/
    → memproses images/1. Motor/, images/2. Smart TV/, dst.
    → setelah selesai folder direname ke images/1/, images/2/, dst.

Jalankan (SINGLE — satu folder saja):
    python watermark.py images/1/
    python watermark.py          ← akan ditanya foldernya
"""

import os
import re
import sys
import shutil
import subprocess
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow belum terinstall. Jalankan: pip install Pillow")


# ── KONFIGURASI ───────────────────────────────────────────────
WATERMARK_TEXT = "© Tiki Toko"     # teks watermark
FONT_SIZE      = 36                 # ukuran font (px)
OPACITY        = 180                # transparansi: 0 (tidak terlihat) – 255 (solid)
POSITION       = "center"           # top-left | top-right | bottom-left | bottom-right | center
MARGIN         = 20                 # jarak dari tepi (px)
TEXT_COLOR     = (255, 255, 255)    # warna teks RGB (putih)
# ─────────────────────────────────────────────────────────────

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".3gp"}


# ── Font & posisi ─────────────────────────────────────────────

def get_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def calc_xy(img_w: int, img_h: int, tw: int, th: int) -> tuple[int, int]:
    m = MARGIN
    options = {
        "top-left":     (m, m),
        "top-right":    (img_w - tw - m, m),
        "bottom-left":  (m, img_h - th - m),
        "bottom-right": (img_w - tw - m, img_h - th - m),
        "center":       ((img_w - tw) // 2, (img_h - th) // 2),
    }
    return options.get(POSITION, options["bottom-right"])


# ── Watermark ─────────────────────────────────────────────────

def watermark_image(path: Path) -> Path:
    """Tambah watermark dan simpan sebagai JPEG. Return path output (selalu .jpg)."""
    img = Image.open(path)
    img_rgba = img.convert("RGBA")

    overlay = Image.new("RGBA", img_rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = get_font(FONT_SIZE)

    bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = calc_xy(img_rgba.width, img_rgba.height, tw, th)

    draw.text((x + 2, y + 2), WATERMARK_TEXT, font=font,
              fill=(0, 0, 0, min(OPACITY // 2, 255)))
    draw.text((x, y), WATERMARK_TEXT, font=font,
              fill=(*TEXT_COLOR, OPACITY))

    result = Image.alpha_composite(img_rgba, overlay)

    # Selalu simpan sebagai JPEG agar konsisten dengan yang diharapkan website (1.jpg, 2.jpg, ...)
    jpg_path = path.with_suffix(".jpg")
    result.convert("RGB").save(jpg_path, "JPEG", quality=95, optimize=True)

    # Hapus file asli kalau ekstensinya berbeda (misal .png, .webp)
    if path != jpg_path:
        path.unlink()

    return jpg_path


def _make_watermark_png(out: Path) -> None:
    """Buat PNG transparan berisi teks watermark (pakai Pillow, bukan ffmpeg freetype)."""
    font = get_font(FONT_SIZE)
    pad  = 12

    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = dummy_draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    img  = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((pad + 2, pad + 2), WATERMARK_TEXT, font=font,
              fill=(0, 0, 0, min(OPACITY // 2, 255)))
    draw.text((pad, pad), WATERMARK_TEXT, font=font,
              fill=(*TEXT_COLOR, OPACITY))
    img.save(out, "PNG")


def _overlay_expr() -> str:
    """Posisi overlay ffmpeg berdasarkan POSITION."""
    m = MARGIN
    return {
        "top-left":     f"x={m}:y={m}",
        "top-right":    "x=W-w-{m}:y={m}".format(m=m),
        "bottom-left":  f"x={m}:y=H-h-{m}",
        "bottom-right": f"x=W-w-{m}:y=H-h-{m}",
        "center":       "x=(W-w)/2:y=(H-h)/2",
    }.get(POSITION, "x=(W-w)/2:y=(H-h)/2")


def watermark_video(path: Path) -> None:
    """Tambah watermark ke video menggunakan ffmpeg overlay (tidak butuh freetype)."""
    wm_png = path.with_name("__wm_overlay.png")
    tmp    = path.with_suffix(".wm_tmp" + path.suffix)
    try:
        _make_watermark_png(wm_png)
        cmd = [
            "ffmpeg",
            "-i", str(path),
            "-i", str(wm_png),
            "-filter_complex", f"overlay={_overlay_expr()}",
            "-c:a", "copy",
            "-crf", "23",
            "-preset", "fast",
            "-loglevel", "error",
            "-y", str(tmp),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            msg = proc.stderr.strip().splitlines()
            raise RuntimeError(msg[-1] if msg else "ffmpeg error")
        os.replace(tmp, path)
    finally:
        wm_png.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


# ── Rename sequential ─────────────────────────────────────────

def rename_sequentially(folder_path: Path, images: list[Path], videos: list[Path]) -> None:
    """Rename ke 1.jpg/2.jpg/... dan 1.mp4/2.mp4/... dengan two-pass untuk hindari konflik."""
    if not images and not videos:
        return

    img_temps, vid_temps = [], []
    for i, p in enumerate(images):
        tmp = folder_path / f"__wm_img_{i}{p.suffix.lower()}"
        p.rename(tmp)
        img_temps.append((tmp, p.suffix.lower()))
    for i, p in enumerate(videos):
        tmp = folder_path / f"__wm_vid_{i}{p.suffix.lower()}"
        p.rename(tmp)
        vid_temps.append((tmp, p.suffix.lower()))

    for i, (tmp, ext) in enumerate(img_temps, 1):
        tmp.rename(folder_path / f"{i}{ext}")
    for i, (tmp, ext) in enumerate(vid_temps, 1):
        tmp.rename(folder_path / f"{i}{ext}")

    parts = []
    if img_temps:
        parts.append(f"{len(img_temps)} gambar → 1{img_temps[0][1]}…")
    if vid_temps:
        parts.append(f"{len(vid_temps)} video → 1{vid_temps[0][1]}…")
    print(f"  Rename   : {' | '.join(parts)}")


# ── Folder rename (batch mode) ────────────────────────────────

def extract_number(folder_name: str) -> str | None:
    """Ekstrak angka di awal nama folder. '14. Kulkas' → '14', '2' → '2'."""
    m = re.match(r'^(\d+)', folder_name.strip())
    return m.group(1) if m else None


def rename_folder_to_number(folder_path: Path) -> Path | None:
    """Rename 'images/14. Kulkas' → 'images/14'. Return path baru atau None jika gagal."""
    number = extract_number(folder_path.name)
    if not number:
        print(f"  ⚠  Tidak bisa ekstrak nomor dari nama folder '{folder_path.name}' — dilewati.")
        return None

    new_path = folder_path.parent / number
    if new_path == folder_path:
        return folder_path  # sudah benar

    if new_path.exists():
        print(f"  ⚠  Folder '{new_path.name}' sudah ada — folder tidak direname.")
        return None

    folder_path.rename(new_path)
    print(f"  Folder   : '{folder_path.name}' → '{new_path.name}'")
    return new_path


# ── Proses satu folder ────────────────────────────────────────

def process_folder(folder_path: Path, ffmpeg_ok: bool) -> tuple[int, int]:
    """Watermark semua gambar/video di folder_path. Return (ok, fail)."""
    images = sorted(f for f in folder_path.iterdir()
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTS)
    videos = sorted(f for f in folder_path.iterdir()
                    if f.is_file() and f.suffix.lower() in VIDEO_EXTS) if ffmpeg_ok else []

    total = len(images) + len(videos)
    if total == 0:
        print("  Tidak ada file gambar/video.")
        return 0, 0

    ok = fail = 0
    ok_images: list[Path] = []
    ok_videos: list[Path] = []

    for i, path in enumerate(images + videos, 1):
        kind = "IMG" if path.suffix.lower() in IMAGE_EXTS else "VID"
        print(f"  [{i:2}/{total}] {kind}  {path.name[:42]:<42} ", end="", flush=True)
        try:
            if kind == "IMG":
                out = watermark_image(path)
                ok_images.append(out)
            else:
                watermark_video(path)
                ok_videos.append(path)
            print("✓")
            ok += 1
        except Exception as e:
            print(f"✗  {e}")
            fail += 1

    rename_sequentially(folder_path, ok_images, ok_videos)
    return ok, fail


# ── Main ──────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) >= 2:
        folder = " ".join(sys.argv[1:]).strip().strip('"')
    else:
        folder = input("Path folder: ").strip().strip('"')

    folder_path = Path(folder)
    if not folder_path.is_dir():
        sys.exit(f"Folder tidak ditemukan: {folder}")

    ffmpeg_ok = shutil.which("ffmpeg") is not None
    if not ffmpeg_ok:
        print("⚠  ffmpeg tidak ditemukan — video dilewati.")
        print("   Install: brew install ffmpeg  (Mac) | sudo apt install ffmpeg  (Linux)\n")

    # ── Deteksi mode: batch (ada subfolder) atau single ───────
    subdirs = sorted(d for d in folder_path.iterdir() if d.is_dir())

    if subdirs:
        # BATCH MODE — proses semua subfolder
        print(f"Batch mode : {len(subdirs)} folder produk")
        print(f"Watermark  : \"{WATERMARK_TEXT}\"  |  {POSITION}  |  opacity {OPACITY}/255")
        print("=" * 55)

        total_ok = total_fail = 0
        for subdir in subdirs:
            print(f"\n📁 {subdir.name}")
            ok, fail = process_folder(subdir, ffmpeg_ok)
            total_ok   += ok
            total_fail += fail

            # Rename folder ke angka saja (misal "1. Motor" → "1")
            rename_folder_to_number(subdir)

        print("\n" + "=" * 55)
        print(f"Selesai: {total_ok} file berhasil, {total_fail} gagal.")

    else:
        # SINGLE MODE — proses langsung file di folder ini
        has_images = any(f.suffix.lower() in IMAGE_EXTS
                         for f in folder_path.iterdir() if f.is_file())
        has_videos = any(f.suffix.lower() in VIDEO_EXTS
                         for f in folder_path.iterdir() if f.is_file())

        if not has_images and not has_videos:
            sys.exit("Tidak ada file gambar/video dan tidak ada subfolder ditemukan.")

        print(f"Folder   : {folder_path.resolve()}")
        print(f"Watermark: \"{WATERMARK_TEXT}\"  |  {POSITION}  |  opacity {OPACITY}/255")
        print("-" * 55)

        ok, fail = process_folder(folder_path, ffmpeg_ok)

        print("-" * 55)
        print(f"Selesai: {ok} berhasil, {fail} gagal.")


if __name__ == "__main__":
    main()
