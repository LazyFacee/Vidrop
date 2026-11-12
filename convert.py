# -*- coding: utf-8 -*-
"""Vidrop - konversi format video, audio, dan gambar (offline, tanpa internet)."""
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

from i18n import tr

IS_WIN = sys.platform.startswith("win")
NO_WINDOW = 0x08000000 if IS_WIN else 0

VIDEO_EXT = {"mp4", "mkv", "webm", "mov", "avi", "flv", "wmv", "m4v", "mpg", "mpeg", "ts", "3gp", "mts"}
AUDIO_EXT = {"mp3", "m4a", "aac", "wav", "flac", "ogg", "opus", "wma", "aiff", "aif"}
IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "bmp", "gif", "tif", "tiff", "ico"}

VIDEO_TARGETS = ["MP4", "MKV", "WEBM", "MOV", "AVI", "GIF"]
AUDIO_TARGETS = ["MP3", "M4A", "WAV", "FLAC", "OGG", "OPUS"]
IMAGE_TARGETS = ["JPG", "PNG", "WEBP", "BMP", "GIF", "TIFF", "ICO"]
LOSSLESS = {"WAV", "FLAC"}


def cat_label(cat):
    return tr("cat_" + cat)


# nilai (bukan label) tetap; label diterjemahkan saat dibutuhkan
_VQ = [("cq_high", 18), ("cq_mid", 23), ("cq_low", 28)]
_VS = [("sz_orig", None), ("1080p", 1080), ("720p", 720), ("480p", 480), ("360p", 360)]
_GQ = [("gif_1", 15), ("gif_2", 12), ("gif_3", 8)]
_AQ = [("aq_best", 320), ("aq_mid", 192), ("aq_low", 128)]
_AC = [("ch_orig", None), ("ch_stereo", 2), ("ch_mono", 1)]
_IQ = [("cq_high", 95), ("cq_mid", 85), ("cq_low", 70)]
_IS = [("sz_orig", None), ("iw_3840", 3840), ("iw_1920", 1920), ("iw_1280", 1280), ("iw_800", 800)]


def _t(lst):
    return [(tr(k) if not k[0].isdigit() else k, v) for k, v in lst]


def file_filters():
    ext = lambda S: " ".join("*." + e for e in sorted(S))
    return [(tr("ft_all"), ext(VIDEO_EXT | AUDIO_EXT | IMAGE_EXT)), (tr("ft_video"), ext(VIDEO_EXT)),
            (tr("ft_audio"), ext(AUDIO_EXT)), (tr("ft_image"), ext(IMAGE_EXT))]


def category_of(path):
    ext = Path(path).suffix.lower().lstrip(".")
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in IMAGE_EXT:
        return "image"
    return None


def target_values(category):
    """Daftar pilihan format hasil untuk sebuah kategori file sumber."""
    if category == "video":
        return VIDEO_TARGETS + [t + tr("audio_only") for t in AUDIO_TARGETS]
    if category == "audio":
        return list(AUDIO_TARGETS)
    if category == "image":
        return list(IMAGE_TARGETS)
    return ["-"]


def target_key(value):
    return value.split(" ")[0].upper()


def option_sets(category, target):
    """-> (kualitas, ukuran, kualitas_aktif, caption_kualitas, caption_ukuran); label sudah diterjemahkan."""
    t = target_key(target)
    if category == "image":
        return _t(_IQ), _t(_IS), t in ("JPG", "WEBP"), tr("cap_quality"), tr("cap_size")
    if t in AUDIO_TARGETS:                     # audio, atau ambil audio dari video
        return _t(_AQ), _t(_AC), t not in LOSSLESS, tr("cap_quality"), tr("cap_channels")
    if t == "GIF":
        return _t(_GQ), _t(_VS), True, tr("cap_smooth"), tr("cap_gif_size")
    return _t(_VQ), _t(_VS), True, tr("cap_quality"), tr("cap_size")


def unique_path(folder, stem, ext):
    p = Path(folder) / f"{stem}.{ext}"
    n = 1
    while p.exists():
        p = Path(folder) / f"{stem} ({n}).{ext}"
        n += 1
    return str(p)


# ---------------------------------------------------------------- ffmpeg
def probe_duration(ffmpeg, src):
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-i", src], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def build_ffmpeg_cmd(ffmpeg, src, dst, category, target, qi, si, quality_list, size_list):
    t = target_key(target)
    q = quality_list[qi][1] if quality_list else None
    s = size_list[si][1] if size_list else None
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", src,
           "-progress", "pipe:1", "-nostats", "-map_metadata", "0"]

    if t in AUDIO_TARGETS:                                  # audio / ambil audio dari video
        cmd += ["-vn", "-map", "0:a:0"]
        codec = {"MP3": ["-c:a", "libmp3lame"], "M4A": ["-c:a", "aac"], "WAV": ["-c:a", "pcm_s16le"],
                 "FLAC": ["-c:a", "flac"], "OGG": ["-c:a", "libvorbis"], "OPUS": ["-c:a", "libopus"]}[t]
        cmd += codec
        if t == "OGG" and q:                                 # libvorbis: mode kualitas (VBR)
            cmd += ["-q:a", {320: "8", 192: "5", 128: "4"}.get(q, "5")]
        elif t == "OPUS" and q:                              # Opus maksimal ±256k per kanal
            cmd += ["-b:a", f"{min(q, 192)}k"]
        elif t not in LOSSLESS and q:
            cmd += ["-b:a", f"{q}k"]
        if s:                                               # jumlah kanal
            cmd += ["-ac", str(s)]
        cmd.append(dst)
        return cmd

    if t == "GIF":
        h = s or 480
        vf = (f"fps={q or 12},scale=-2:'min(ih,{h})':flags=lanczos,split[s0][s1];"
              f"[s0]palettegen[p];[s1][p]paletteuse")
        return cmd + ["-map", "0:v:0", "-an", "-vf", vf, "-loop", "0", dst]

    cmd += ["-map", "0:v:0", "-map", "0:a:0?"]
    if s:
        vf = f"scale='trunc(iw*min(1,{s}/ih)/2)*2':'trunc(min(ih,{s})/2)*2'"
    else:
        vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2"           # lebar/tinggi harus genap
    crf = q or 23
    if t in ("MP4", "MOV", "MKV"):
        cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
        if t != "MKV":
            cmd += ["-movflags", "+faststart"]
    elif t == "WEBM":
        cmd += ["-vf", vf, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(crf + 8), "-row-mt", "1",
                "-deadline", "good", "-cpu-used", "4", "-pix_fmt", "yuv420p",
                "-c:a", "libopus", "-b:a", "160k"]
    elif t == "AVI":
        qv = {18: 2, 23: 4, 28: 7}.get(crf, 4)
        cmd += ["-vf", vf, "-c:v", "mpeg4", "-q:v", str(qv), "-c:a", "libmp3lame", "-b:a", "192k"]
    cmd.append(dst)
    return cmd


# ---------------------------------------------------------------- gambar
def convert_image(src, dst, target, quality, max_w):
    t = target_key(target)
    im = Image.open(src)
    animated = getattr(im, "is_animated", False) and t in ("GIF", "WEBP")

    def prep(fr):
        fr = ImageOps.exif_transpose(fr)
        if max_w and fr.width > max_w:
            fr = fr.resize((max_w, max(1, int(fr.height * max_w / fr.width))), Image.Resampling.LANCZOS)
        return fr

    if animated:
        dur = im.info.get("duration", 100)
        frames = [prep(f.copy().convert("RGBA")) for f in ImageSequence.Iterator(im)]
        extra = {"quality": quality} if t == "WEBP" else {"disposal": 2}
        frames[0].save(dst, save_all=True, append_images=frames[1:], duration=dur, loop=0, **extra)
        return

    fr = prep(im)
    if t == "JPG":
        if fr.mode in ("RGBA", "LA", "P"):
            rgba = fr.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.getchannel("A"))
            fr = bg
        fr.convert("RGB").save(dst, "JPEG", quality=quality, optimize=True)
    elif t == "PNG":
        fr.save(dst, "PNG", optimize=True)
    elif t == "WEBP":
        fr.save(dst, "WEBP", quality=quality, method=4)
    elif t == "BMP":
        fr.convert("RGB").save(dst, "BMP")
    elif t == "GIF":
        fr.convert("RGBA").convert("P", palette=Image.Palette.ADAPTIVE).save(dst, "GIF")
    elif t == "TIFF":
        fr.save(dst, "TIFF", compression="tiff_lzw")
    elif t == "ICO":
        sq = ImageOps.pad(fr.convert("RGBA"), (256, 256), color=(0, 0, 0, 0))
        sq.save(dst, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    else:
        raise ValueError("Format gambar tidak didukung: " + t)


# ---------------------------------------------------------------- pengelola konversi
class ConvertCancelled(Exception):
    pass


class Converter:
    def __init__(self, ffmpeg):
        self.ffmpeg = ffmpeg
        self.cancel_flag = threading.Event()
        self.proc = None

    def cancel(self):
        self.cancel_flag.set()
        p = self.proc
        if p is not None:
            try:
                p.terminate()
            except Exception:
                pass

    def run(self, files, category, target, qi, si, out_dir, on_progress):
        """Konversi berurutan. on_progress(fraksi_total, teks). Mengembalikan (hasil, gagal)."""
        os.makedirs(out_dir, exist_ok=True)
        t = target_key(target)
        qlist, slist, _, _, _ = option_sets(category, target)
        ext = {"JPG": "jpg", "TIFF": "tiff"}.get(t, t.lower())
        results, failed = [], []
        n = len(files)
        for i, src in enumerate(files):
            if self.cancel_flag.is_set():
                raise ConvertCancelled()
            name = os.path.basename(src)
            dst = unique_path(out_dir, Path(src).stem, ext)

            def prog(frac, i=i, name=name):
                on_progress((i + frac) / n, f"{i + 1}/{n} · {name} · {int(frac * 100)}%")

            try:
                prog(0.0)
                if category == "image":
                    convert_image(src, dst, target, qlist[qi][1], slist[si][1])
                else:
                    self._run_ffmpeg(src, dst, category, target, qi, si, qlist, slist, prog)
                results.append(dst)
            except ConvertCancelled:
                self._remove(dst)
                raise
            except Exception as e:
                self._remove(dst)
                failed.append((name, str(e)))
            prog(1.0)
        return results, failed

    @staticmethod
    def _remove(path):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass

    def _run_ffmpeg(self, src, dst, category, target, qi, si, qlist, slist, prog):
        dur = probe_duration(self.ffmpeg, src)
        cmd = build_ffmpeg_cmd(self.ffmpeg, src, dst, category, target, qi, si, qlist, slist)
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                     encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        err_lines = []
        t_err = threading.Thread(target=lambda: err_lines.extend(self.proc.stderr.readlines()), daemon=True)
        t_err.start()
        last = 0.0
        for line in self.proc.stdout:
            if self.cancel_flag.is_set():
                break
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    secs = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                if dur > 0:
                    last = max(last, min(0.99, secs / dur))     # tidak pernah turun
                    prog(last)
        code = self.proc.wait()
        t_err.join(timeout=2)
        self.proc = None
        if self.cancel_flag.is_set():
            raise ConvertCancelled()
        if code != 0:
            tail = "".join(err_lines).strip().splitlines()[-3:]
            raise RuntimeError(" ".join(tail) or f"ffmpeg gagal (kode {code})")
