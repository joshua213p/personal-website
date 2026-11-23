#!/usr/bin/env python3
"""
Turns the originals in "media for website/" into small web-friendly files
and writes media/manifest.js, which photos.html and videos.html read.

  photos (.jpg .jpeg .png .heic .tif ...) -> media/photos/<name>.jpg  (max 1200px, sRGB)
  videos (.mov .mp4 .mpg .m4v ...)        -> media/videos/<name>.mp4  (H.264, 540p) + poster .jpg

Run it again whenever you add or remove files in "media for website/":

    python3 scripts/build_media.py

Needs macOS (uses the built-in `sips` and `avconvert`) and ffmpeg (`brew install ffmpeg`).
iPhone HDR videos are converted to normal colour so they don't look washed out.
Location and other metadata are stripped from videos.
Files that are already converted are skipped, so re-running is quick.
"""

import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "media for website"
OUT = ROOT / "media"
PHOTO_OUT = OUT / "photos"
VIDEO_OUT = OUT / "videos"

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".webp"}
VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mpg", ".mpeg", ".avi", ".mts"}

PHOTO_MAX = 1200          # longest edge, px
VIDEO_HEIGHT = 540        # px
SRGB = "/System/Library/ColorSync/Profiles/sRGB Profile.icc"


def slug(stem: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return s or "file"


def caption(stem: str) -> str:
    # "001542170019 copy" -> "001542170019" (macOS adds " copy" when duplicating)
    return re.sub(r"\s+copy(\s+\d+)?$", "", stem, flags=re.IGNORECASE)


def fresh(out: Path, src: Path) -> bool:
    return out.exists() and out.stat().st_mtime >= src.stat().st_mtime


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-800:]}")
    return r.stdout


def photo(src: Path, out: Path):
    if fresh(out, src):
        return
    dims = run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(src)])
    w = int(re.search(r"pixelWidth: (\d+)", dims).group(1))
    h = int(re.search(r"pixelHeight: (\d+)", dims).group(1))
    cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80"]
    if max(w, h) > PHOTO_MAX:          # never upscale small photos
        cmd += ["-Z", str(PHOTO_MAX)]
    if Path(SRGB).exists():
        cmd += ["--matchTo", SRGB]
    run(cmd + [str(src), "--out", str(out)])


HDR_TRANSFERS = {"arib-std-b67", "smpte2084"}   # HLG (iPhone) and PQ


def video(src: Path, out: Path, poster: Path):
    if fresh(out, src) and fresh(poster, src):
        return
    info = json.loads(run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=field_order,color_transfer", "-of", "json", str(src)]))
    stream = (info.get("streams") or [{}])[0]
    field = stream.get("field_order", "progressive")

    with tempfile.TemporaryDirectory() as tmp:
        source = src
        if stream.get("color_transfer") in HDR_TRANSFERS:
            # iPhone HDR looks grey and washed out once squeezed into normal video.
            # macOS's own converter tone-maps it to regular (SDR) colour first.
            source = Path(tmp) / "sdr.mov"
            run(["avconvert", "-s", str(src), "-p", "Preset1920x1080",
                 "-o", str(source), "--replace"])
        encode(source, out, field)

    run(["ffmpeg", "-y", "-v", "error", "-ss", "0.3", "-i", str(out),
         "-frames:v", "1", "-q:v", "4", str(poster)])


def encode(src: Path, out: Path, field: str):
    vf = []
    if field not in ("progressive", "unknown"):
        vf.append("yadif")                        # old camcorder footage is interlaced
    # square pixels, 540p, even dimensions
    vf.append(f"scale=-2:{VIDEO_HEIGHT}:flags=lanczos,setsar=1"
              if field in ("progressive", "unknown")
              else "scale=trunc(ih*dar/2)*2:ih:flags=lanczos,setsar=1")
    vf = ",".join(vf)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-map_metadata", "-1",                   # drop GPS location, dates, device info
         "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "24",
         "-profile:v", "high", "-pix_fmt", "yuv420p",
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         "-c:a", "aac", "-b:a", "96k", "-ac", "2",
         "-movflags", "+faststart", str(out)])


def main():
    if not SRC.is_dir():
        sys.exit(f'Folder not found: {SRC}')
    PHOTO_OUT.mkdir(parents=True, exist_ok=True)
    VIDEO_OUT.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in SRC.iterdir() if p.is_file() and not p.name.startswith("."))
    photos, videos, used = [], [], set()

    def unique(name, kind):
        base, n = name, 2
        while (kind, name) in used:
            name, n = f"{base}-{n}", n + 1
        used.add((kind, name))
        return name

    for p in files:
        ext = p.suffix.lower()
        if ext in PHOTO_EXT:
            name = unique(slug(p.stem), "p")
            photos.append((p, PHOTO_OUT / f"{name}.jpg"))
        elif ext in VIDEO_EXT:
            name = unique(slug(p.stem), "v")
            videos.append((p, VIDEO_OUT / f"{name}.mp4", VIDEO_OUT / f"{name}.jpg"))

    print(f"{len(photos)} photos, {len(videos)} videos")
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda a: photo(*a), photos))
    print("photos done")
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(lambda a: video(*a), videos))
    print("videos done")

    # remove web files whose originals were deleted
    keep = {o for _, o in photos} | {o for _, o, _ in videos} | {q for _, _, q in videos}
    for d in (PHOTO_OUT, VIDEO_OUT):
        for f in d.iterdir():
            if f not in keep and not f.name.startswith("."):
                f.unlink()

    rel = lambda f: f.relative_to(ROOT).as_posix()
    manifest = {
        "photos": [{"src": rel(o), "caption": caption(s.stem)} for s, o in photos],
        "videos": [{"src": rel(o), "poster": rel(q), "caption": caption(s.stem)} for s, o, q in videos],
    }
    (OUT / "manifest.js").write_text(
        "// generated by scripts/build_media.py, do not edit by hand\n"
        "window.MEDIA = " + json.dumps(manifest, indent=1, ensure_ascii=False) + ";\n")
    print("wrote media/manifest.js")


if __name__ == "__main__":
    main()
