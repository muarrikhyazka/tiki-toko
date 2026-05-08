#!/usr/bin/env python3
"""
Tambahkan watermark ke semua gambar dan video dalam folder (mengganti file asli).

Install:
    pip install Pillow
    ffmpeg (untuk video):
        macOS  : brew install ffmpeg
        Ubuntu : sudo apt install ffmpeg
        Windows: https://ffmpeg.org/download.html

Jalankan:
    python watermark.py /path/ke/folder
    python watermark.py          ← akan ditanya foldernya
"""

import os
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
POSITION       = "bottom-right"     # top-left | top-right | bottom-left | bottom-right | center
MARGIN         = 20                 # jarak dari tepi (px)
TEXT_COLOR     = (255, 255, 255)    # warna teks RGB (putih)
# ─────────────────────────────────────────────────────────────

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".3gp"}


def get_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",                              # macOS
        "/System/Library/Fonts/Arial.ttf",                                  # macOS
        "/Library/Fonts/Arial.ttf",                                         # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",             # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Linux
        "C:/Windows/Fonts/arial.ttf",                                       # Windows
        "C:/Windows/Fonts/Arial.ttf",                                       # Windows
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)  # Pillow 10.1+
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


def watermark_image(path: Path) -> None:
    img = Image.open(path)
    orig_mode = img.mode
    img_rgba = img.convert("RGBA")

    overlay = Image.new("RGBA", img_rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = get_font(FONT_SIZE)

    bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = calc_xy(img_rgba.width, img_rgba.height, tw, th)

    # Shadow
    draw.text((x + 2, y + 2), WATERMARK_TEXT, font=font,
              fill=(0, 0, 0, min(OPACITY // 2, 255)))
    # Teks utama
    draw.text((x, y), WATERMARK_TEXT, font=font,
              fill=(*TEXT_COLOR, OPACITY))

    result = Image.alpha_composite(img_rgba, overlay)

    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        result.convert("RGB").save(path, "JPEG", quality=95, optimize=True)
    elif ext == ".webp":
        result.save(path, "WEBP", quality=90)
    elif ext == ".bmp":
        result.convert(orig_mode).save(path, "BMP")
    else:
        result.save(path)


def ffmpeg_pos_expr() -> str:
    m = MARGIN
    return {
        "top-left":     f"x={m}:y={m}",
        "top-right":    f"x=w-tw-{m}:y={m}",
        "bottom-left":  f"x={m}:y=h-th-{m}",
        "bottom-right": f"x=w-tw-{m}:y=h-th-{m}",
        "center":       f"x=(w-tw)/2:y=(h-th)/2",
    }.get(POSITION, f"x=w-tw-{m}:y=h-th-{m}")


def find_system_font() -> str:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for f in candidates:
        if os.path.exists(f):
            return f
    return ""


def watermark_video(path: Path) -> None:
    tmp = path.with_suffix(".wm_tmp" + path.suffix)

    # Escape karakter khusus ffmpeg
    text = WATERMARK_TEXT.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    alpha = f"{OPACITY / 255:.2f}"
    shadow_alpha = f"{OPACITY / 255 / 2:.2f}"

    drawtext = (
        f"drawtext="
        f"text='{text}':"
        f"fontsize={FONT_SIZE}:"
        f"fontcolor=white@{alpha}:"
        f"{ffmpeg_pos_expr()}:"
        f"shadowcolor=black@{shadow_alpha}:shadowx=2:shadowy=2"
    )

    font_path = find_system_font()
    if font_path:
        drawtext = f"fontfile='{font_path}':" + drawtext

    cmd = [
        "ffmpeg", "-i", str(path),
        "-vf", drawtext,
        "-c:a", "copy",   # audio tidak di-encode ulang
        "-crf", "23",     # kualitas video (18=terbaik, 28=terkecil)
        "-preset", "fast",
        "-loglevel", "error",
        "-y", str(tmp),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        msg = proc.stderr.strip().splitlines()
        raise RuntimeError(msg[-1] if msg else "ffmpeg error")

    os.replace(tmp, path)


def rename_sequentially(folder_path: Path, images: list[Path], videos: list[Path]) -> None:
    """Rename watermarked files to 1.jpg/2.jpg/... and 1.mp4/2.mp4/..."""
    if not images and not videos:
        return

    # Pass 1: rename to unique temp names to avoid collisions
    img_temps, vid_temps = [], []
    for i, p in enumerate(images):
        tmp = folder_path / f"__wm_img_{i}{p.suffix.lower()}"
        p.rename(tmp)
        img_temps.append((tmp, p.suffix.lower()))
    for i, p in enumerate(videos):
        tmp = folder_path / f"__wm_vid_{i}{p.suffix.lower()}"
        p.rename(tmp)
        vid_temps.append((tmp, p.suffix.lower()))

    # Pass 2: rename to final sequential names
    for i, (tmp, ext) in enumerate(img_temps, 1):
        tmp.rename(folder_path / f"{i}{ext}")
    for i, (tmp, ext) in enumerate(vid_temps, 1):
        tmp.rename(folder_path / f"{i}{ext}")

    print(f"Rename   : {len(img_temps)} gambar → 1{img_temps[0][1]}…  |  "
          f"{len(vid_temps)} video → 1{vid_temps[0][1]}…" if img_temps and vid_temps else
          f"Rename   : {len(img_temps)} gambar → 1{img_temps[0][1]}…" if img_temps else
          f"Rename   : {len(vid_temps)} video → 1{vid_temps[0][1]}…")


def main() -> None:
    # Ambil path folder dari argumen atau tanya user
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

    images = sorted(f for f in folder_path.iterdir()
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTS)
    videos = sorted(f for f in folder_path.iterdir()
                    if f.is_file() and f.suffix.lower() in VIDEO_EXTS) if ffmpeg_ok else []

    total = len(images) + len(videos)
    if total == 0:
        print("Tidak ada file gambar/video yang ditemukan.")
        return

    print(f"Folder   : {folder_path.resolve()}")
    print(f"Ditemukan: {len(images)} gambar, {len(videos)} video")
    print(f"Watermark: \"{WATERMARK_TEXT}\"  |  {POSITION}  |  opacity {OPACITY}/255")
    print("-" * 55)

    ok = fail = 0
    ok_images: list[Path] = []
    ok_videos: list[Path] = []
    for i, path in enumerate(images + videos, 1):
        kind = "IMG" if path.suffix.lower() in IMAGE_EXTS else "VID"
        print(f"[{i:3}/{total}] {kind}  {path.name[:45]:<45} ", end="", flush=True)
        try:
            if kind == "IMG":
                watermark_image(path)
                ok_images.append(path)
            else:
                watermark_video(path)
                ok_videos.append(path)
            print("✓")
            ok += 1
        except Exception as e:
            print(f"✗  {e}")
            fail += 1

    print("-" * 55)
    print(f"Selesai: {ok} berhasil, {fail} gagal.")

    rename_sequentially(folder_path, ok_images, ok_videos)


if __name__ == "__main__":
    main()
