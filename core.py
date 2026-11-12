# -*- coding: utf-8 -*-
"""Vidrop - inti: konstanta, utilitas, pengaturan, riwayat, komponen YouTube."""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from i18n import tr, set_lang, detect_lang, get_lang, LANG_NAMES   # noqa: F401

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# ---------------------------------------------------------------- warna tema "senja kaca"
TXT = (255, 255, 255)
MUTED = (226, 222, 242)
DIM = (180, 174, 208)
INK = (40, 34, 68)                 # teks gelap di atas tombol putih
PINK = (255, 156, 198)
VIOLET = (170, 148, 255)
BLUE = (108, 178, 255)
ORANGE = (255, 186, 124)
OK = (168, 246, 202)
ERR = (255, 164, 174)


def hx(c):
    return "#%02x%02x%02x" % tuple(c[:3])


# ---------------------------------------------------------------- platform (hanya yang bisa dibuka TANPA login)
PLATFORMS = [
    ("youtube", "YouTube", ("youtube.com", "youtu.be", "youtube-nocookie.com")),
    ("tiktok", "TikTok", ("tiktok.com",)),
    ("x", "X", ("twitter.com", "x.com", "t.co", "fxtwitter.com", "vxtwitter.com")),
    ("facebook", "Facebook", ("facebook.com", "fb.watch", "fb.com")),
    ("snapchat", "Snapchat", ("snapchat.com",)),
    ("reddit", "Reddit", ("reddit.com", "redd.it")),
    ("vimeo", "Vimeo", ("vimeo.com",)),
]
OTHER_KEY = "other"
PLATFORM_NAMES = {k: n for k, n, _ in PLATFORMS}
# Layanan yang selalu butuh login: tidak didukung di Vidrop.
BLOCKED_DOMAINS = ("instagram.com", "instagr.am", "cdninstagram.com")
BLOCKED_KEY = "blocked"
EXTRACTOR_TO_KEY = {"youtube": "youtube", "snapchat": "snapchat", "twitter": "x", "tiktok": "tiktok",
                    "facebook": "facebook", "reddit": "reddit", "vimeo": "vimeo"}

VIDEO_FORMATS = ["MP4", "MKV", "WEBM"]
AUDIO_FORMATS = ["MP3", "M4A", "OPUS", "FLAC", "WAV"]
THUMB_FORMATS = ["JPG", "PNG", "WEBP"]
LOSSLESS = {"FLAC", "WAV"}
LANG_CHOICES = ["auto", "id", "en"]


def audio_quality_options():
    return [(tr("aq_best"), "320"), (tr("aq_mid"), "192"), (tr("aq_low"), "128")]


# ---------------------------------------------------------------- utilitas
def resource(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def data_dir():
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.join(str(Path.home()), "AppData", "Local")
    elif IS_MAC:
        base = os.path.join(str(Path.home()), "Library", "Application Support")
    else:
        base = os.path.join(str(Path.home()), ".local", "share")
    p = Path(base) / "Vidrop"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def fmt_duration(sec):
    if not sec:
        return "-"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def safe_name(text):
    return re.sub(r'[\\/:*?"<>|]', "", text or "file").strip()[:150] or "file"


def open_folder(path):
    try:
        if IS_WIN:
            os.startfile(path)
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def reveal_file(path):
    """Buka folder file (di Windows/Mac file ikut disorot)."""
    try:
        if os.path.isfile(path):
            if IS_WIN:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
                return
            if IS_MAC:
                subprocess.Popen(["open", "-R", path])
                return
        open_folder(os.path.dirname(path) if os.path.isfile(path) else path)
    except Exception:
        pass


def ellipsize(font, text, maxw, left=False):
    if font.measure(text) <= maxw:
        return text
    while len(text) > 1:
        text = text[1:] if left else text[:-1]
        cand = ("…" + text) if left else (text + "…")
        if font.measure(cand) <= maxw:
            return cand
    return "…"


def friendly_error(err):
    e = err.lower()
    if "unsupported url" in e:
        return tr("err_unsupported")
    if "confirm you" in e and "bot" in e:
        return tr("err_bot")
    if any(k in e for k in ("login", "cookies", "sign in", "private", "rate-limit",
                            "requires authentication", "empty media", "log in")):
        return tr("err_login")
    if "requested format is not available" in e:
        return tr("err_format")
    if any(k in e for k in ("getaddrinfo", "urlopen", "timed out", "connection", "network")):
        return tr("err_network")
    if "http error 429" in e:
        return tr("err_429")
    if "ffmpeg" in e or "postprocess" in e:
        return tr("err_ffmpeg")
    return tr("err_prefix", msg=err.replace("ERROR: ", "")[:180])


def detect_platform(url):
    """-> kunci platform | 'other' | 'blocked' (butuh login) | None."""
    url = (url or "").strip()
    if not url:
        return None
    if not re.match(r"^\w+://", url):
        url = "https://" + url
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None
    if "." not in host:
        return None
    for d in BLOCKED_DOMAINS:
        if host == d or host.endswith("." + d):
            return BLOCKED_KEY
    for key, _, domains in PLATFORMS:
        for d in domains:
            if host == d or host.endswith("." + d):
                return key
    return OTHER_KEY


STANDARD = [144, 240, 360, 480, 540, 576, 720, 960, 1080, 1440, 1620, 2160, 2880, 4320]


def snap(s):
    best = min(STANDARD, key=lambda v: abs(v - s))
    return best if abs(best - s) <= max(6, best * 0.05) else s


def res_label(s):
    names = {1440: "2K", 2160: "4K", 2880: "5K", 4320: "8K"}
    return f"{names[s]} ({s}p)" if s in names else f"{s}p"


def build_quality_options(info):
    """-> [(label, batas_tinggi | None)]. Resolusi dihitung dari sisi terpendek
    supaya video vertikal (Shorts/TikTok) dilabeli dengan benar."""
    best_h = {}
    for f in info.get("formats") or []:
        if f.get("vcodec") in (None, "none"):
            continue
        w, h = f.get("width"), f.get("height")
        if not (w or h):
            continue
        short = snap(min(w, h) if (w and h) else (h or w))
        best_h[short] = max(best_h.get(short, 0), h or short)
    if not best_h:
        return [(tr("q_best"), None)]
    shorts = sorted(best_h, reverse=True)
    opts = [(tr("q_max", res=res_label(shorts[0])), None)]
    for s in shorts[1:]:
        opts.append((res_label(s), max(best_h[k] for k in best_h if k <= s)))
    return opts


# ---------------------------------------------------------------- Deno (wajib untuk YouTube)
def deno_url():
    base = "https://github.com/denoland/deno/releases/latest/download/"
    m = platform.machine().lower()
    if IS_WIN:
        return base + "deno-x86_64-pc-windows-msvc.zip"
    if IS_MAC:
        return base + ("deno-aarch64-apple-darwin.zip" if m in ("arm64", "aarch64")
                       else "deno-x86_64-apple-darwin.zip")
    return None


def find_deno():
    exe = "deno.exe" if IS_WIN else "deno"
    p = data_dir() / exe
    if p.exists():
        return str(p)
    return shutil.which("deno")


def download_deno(progress):
    import zipfile
    url = deno_url()
    if not url:
        raise RuntimeError("unsupported platform")
    exe = "deno.exe" if IS_WIN else "deno"
    dest = data_dir() / exe
    tmp = data_dir() / "deno.zip.part"
    req = urllib.request.Request(url, headers={"User-Agent": "Vidrop"})
    with urllib.request.urlopen(req, timeout=40) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            progress(done, total)
    with zipfile.ZipFile(tmp) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(exe))
        with z.open(name) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
    if not IS_WIN:
        os.chmod(dest, 0o755)
    try:
        tmp.unlink()
    except Exception:
        pass
    return str(dest)


# ---------------------------------------------------------------- pengaturan tersimpan
DEFAULTS = {"video_fmt": "MP4", "audio_fmt": "MP3", "thumb_fmt": "JPG", "lang": "auto",
            "save_dir": str(Path.home() / "Downloads"), "convert_dir": ""}


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(data_dir() / "settings.json", "r", encoding="utf-8") as f:
            s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except Exception:
        pass
    if s["video_fmt"] not in VIDEO_FORMATS:
        s["video_fmt"] = "MP4"
    if s["audio_fmt"] not in AUDIO_FORMATS:
        s["audio_fmt"] = "MP3"
    if s["thumb_fmt"] not in THUMB_FORMATS:
        s["thumb_fmt"] = "JPG"
    if s["lang"] not in LANG_CHOICES:
        s["lang"] = "auto"
    if not os.path.isdir(s["save_dir"]):
        s["save_dir"] = DEFAULTS["save_dir"]
    if s["convert_dir"] and not os.path.isdir(s["convert_dir"]):
        s["convert_dir"] = ""
    return s


def save_settings(s):
    try:
        with open(data_dir() / "settings.json", "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def resolve_lang(setting):
    return detect_lang() if setting == "auto" else setting


# ---------------------------------------------------------------- riwayat aktivitas
HISTORY_MAX = 40


def load_history():
    try:
        with open(data_dir() / "history.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return [h for h in data if isinstance(h, dict) and "name" in h][:HISTORY_MAX]
    except Exception:
        return []


def save_history(items):
    try:
        with open(data_dir() / "history.json", "w", encoding="utf-8") as f:
            json.dump(items[:HISTORY_MAX], f, ensure_ascii=False)
    except Exception:
        pass


def ago_text(ts):
    d = max(0, int(time.time() - ts))
    if d < 60:
        return tr("ago_now")
    if d < 3600:
        return tr("ago_min", n=d // 60)
    if d < 86400:
        return tr("ago_hour", n=d // 3600)
    return tr("ago_day", n=d // 86400)


# ---------------------------------------------------------------- Windows: DPI, title bar, ikon
def enable_dpi():
    if not IS_WIN:
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("vidrop.app")
    except Exception:
        pass


def dark_titlebar(win):
    if not IS_WIN:
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        one = ctypes.c_int(1)
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(one), 4)
        cap = ctypes.c_int(0x0046242C)   # warna caption (Windows 11): ungu gelap
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), 4)
    except Exception:
        pass


def set_win_icon(win, ico_path):
    """Pasang ikon jendela lewat Win32 (WM_SETICON): ikon di title bar & taskbar."""
    if not IS_WIN or not os.path.isfile(ico_path):
        return
    try:
        import ctypes
        from ctypes import c_void_p, c_wchar_p, c_uint, c_int
        user32 = ctypes.windll.user32
        user32.LoadImageW.argtypes = [c_void_p, c_wchar_p, c_uint, c_int, c_int, c_uint]
        user32.LoadImageW.restype = c_void_p
        user32.SendMessageW.argtypes = [c_void_p, c_uint, c_void_p, c_void_p]
        user32.GetParent.restype = c_void_p
        win.update_idletasks()
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        for kind, metric in ((0, 49), (1, 11)):      # ICON_SMALL / ICON_BIG
            size = user32.GetSystemMetrics(metric)
            h = user32.LoadImageW(None, ico_path, 1, size, size, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
            if h:
                user32.SendMessageW(hwnd, 0x0080, kind, h)               # WM_SETICON
    except Exception:
        pass
