# -*- coding: utf-8 -*-
"""
Vidrop - Download videos, music and thumbnails from YouTube, TikTok, X and 1000+ sites that need
no login, plus convert video, audio and images. Windows & macOS. Indonesian / English.

Engine: yt-dlp + ffmpeg  |  UI: Tkinter + Pillow ("sunset glass" design)
"""
import io
import os
import queue
import re
import sys
import threading
import time
import urllib.request
import tkinter as tk
from tkinter import filedialog, messagebox

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import yt_dlp
from yt_dlp.utils import DownloadCancelled

from core import *            # noqa: F401,F403
from gfx import *             # noqa: F401,F403
import convert as CV

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = None

BASE_W, BASE_H = 980, 700
APP_VERSION = "2.0.0"


class Cancelled(DownloadCancelled):
    pass


class QuietLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def ease_out_back_soft(t):
    return ease_out_back(t, 0.55)


# ======================================================================
#  Komponen UI kecil
# ======================================================================
class ChipRow:
    """Baris chip (platform / jenis file). Chip aktif berubah jadi pil putih dengan transisi halus."""

    OFF, ON = (232, 228, 246), INK

    def __init__(self, app, specs, x0, y, chip_h):
        g, u, cv = app.g, app.g.u, app.cv
        self.app, self.items, self.active = app, {}, None
        f = g.font(11)
        x, p = x0, u(10)
        for key, label in specs:
            w = f.measure(label) + u(18)
            off, on = g.chip_img(w, chip_h, False), g.chip_img(w, chip_h, True)
            it = cv.create_image(x - p, y - p, anchor="nw")
            fade = Crossfade(cv, it)
            fade.show(off)
            tx = cv.create_text(x + w // 2, y + chip_h // 2, text=label, font=f, fill=hx(self.OFF), state="disabled")
            self.items[key] = (it, tx, off, on, fade)
            x += w + u(6)
        self.end_x = x

    def set(self, key):
        if key is not None and key not in self.items:
            key = OTHER_KEY if OTHER_KEY in self.items else None
        if key == self.active:
            return
        app = self.app
        if self.active in self.items:
            it, tx, off, on, fade = self.items[self.active]
            fade.to(off, 0.26)
            app.cv.itemconfigure(tx, font=app.g.font(11))
            app.text_anim(tx, self.ON, self.OFF, 0.26)
        if key in self.items:
            it, tx, off, on, fade = self.items[key]
            fade.to(on, 0.26)
            app.cv.itemconfigure(tx, font=app.g.font(11, True))
            app.text_anim(tx, self.OFF, self.ON, 0.26)
        self.active = key


class Segmented:
    """Kontrol segmen 3 pilihan dengan 'pill' putih yang meluncur."""

    def __init__(self, app, x, y, w, h, labels, on_change):
        g, u, cv = app.g, app.g.u, app.cv
        self.app, self.x, self.y, self.w, self.h = app, x, y, w, h
        self.n, self.on_change, self.idx, self.pos, self.anim = len(labels), on_change, 0, 0.0, None
        self.track_photo = ImageTk.PhotoImage(g.track_img(w, h))
        self.track = cv.create_image(x, y, anchor="nw", image=self.track_photo)
        pad4 = u(4)
        self.pw, self.ph = (w - 2 * pad4) // self.n, h - 2 * pad4
        self.pp = u(16)
        self.pill_photo = ImageTk.PhotoImage(g.button_img(self.pw, self.ph, "primary", "normal"))
        self.pill = cv.create_image(0, 0, anchor="nw", image=self.pill_photo)
        self.texts = [cv.create_text(x + pad4 + i * self.pw + self.pw // 2, y + h // 2, text=lb,
                                     font=g.font(12, True), fill=hx(TXT), state="disabled")
                      for i, lb in enumerate(labels)]
        for it in (self.track, self.pill):
            cv.tag_bind(it, "<ButtonRelease-1>", self._click)
            cv.tag_bind(it, "<Enter>", lambda e: cv.configure(cursor="hand2"))
            cv.tag_bind(it, "<Leave>", lambda e: cv.configure(cursor=""))
        self._place(0.0)

    def _place(self, pos):
        self.pos = pos
        pad4 = self.app.g.u(4)
        self.app.cv.coords(self.pill, self.x + pad4 + pos * self.pw - self.pp, self.y + pad4 - self.pp)
        for i, t in enumerate(self.texts):
            k = max(0.0, 1 - abs(pos - i))
            self.app.cv.itemconfigure(t, fill=hx(lerp_color(TXT, INK, k)))

    def select(self, idx, animate=True):
        self.idx = idx
        if self.anim:
            self.anim.cancel()
        if not animate:
            return self._place(float(idx))
        p0 = self.pos
        self.anim = Anim(self.app.cv, 0.34, lambda t: self._place(p0 + (idx - p0) * t), ease_out_back_soft)

    def _click(self, e):
        if self.app.busy:
            return
        i = max(0, min(self.n - 1, int((e.x - self.x) / (self.w / self.n))))
        if i != self.idx:
            self.select(i)
            self.on_change(i)


class Meter:
    """Bar progress + angka persen yang bergerak halus (tidak pernah mundur), kilau saat aktif,
    dan grafik kecepatan opsional."""

    def __init__(self, app, bar_xywh, pct_item, active_fn, chart_item=None, chart_wh=None):
        self.app, self.pct_item, self.active_fn = app, pct_item, active_fn
        self.x, self.y, self.w, self.h = bar_xywh
        cv = app.cv
        self.track_photo = ImageTk.PhotoImage(app.g.bar_img(self.w, self.h, None))
        cv.create_image(self.x, self.y, anchor="nw", image=self.track_photo)
        self.item = cv.create_image(self.x, self.y, anchor="nw", state="hidden")
        self.photo, self.target, self.shown, self.phase, self.job = None, 0.0, 0.0, 0.0, None
        self.t = time.perf_counter()
        self.chart_item, self.chart_wh, self.samples, self.chart_photo, self._chart_t = chart_item, chart_wh, [], None, 0
        self.redraw_chart(force=True)

    def reset(self):
        self.target = self.shown = 0.0
        self.app.cv.itemconfigure(self.item, state="hidden")
        self.app.cv.itemconfigure(self.pct_item, text="0%")
        self.samples = []
        self.redraw_chart(force=True)

    def set(self, frac):
        if frac <= 0:
            return self.reset()
        self.target = max(self.target, min(1.0, frac))
        if self.job is None:
            self.t = time.perf_counter()
            self._tick()

    def add_sample(self, mbps):
        self.samples.append(mbps)
        self.samples = self.samples[-48:]
        self.redraw_chart()

    def redraw_chart(self, force=False):
        if not self.chart_item:
            return
        now = time.perf_counter()
        if not force and now - self._chart_t < 0.22:
            return
        self._chart_t = now
        w, h = self.chart_wh
        try:
            self.chart_photo = ImageTk.PhotoImage(self.app.g.chart_img(w, h, self.samples))
            self.app.cv.itemconfigure(self.chart_item, image=self.chart_photo)
        except tk.TclError:
            pass

    def _tick(self):
        self.job = None
        now = time.perf_counter()
        dt = min(0.08, now - self.t)
        self.t = now
        d = self.target - self.shown
        self.shown = self.target if abs(d) < 0.0015 else self.shown + d * (1 - 2.718 ** (-dt * 9))
        self.phase = (self.phase + dt * 0.8) % 1.0
        active = self.active_fn()
        w = max(self.h, int(self.w * self.shown))
        try:
            self.photo = ImageTk.PhotoImage(self.app.g.bar_img(self.w, self.h, self.shown, self.phase if active else None))
            self.app.cv.itemconfigure(self.item, image=self.photo, state="normal")
            self.app.cv.itemconfigure(self.pct_item, text=f"{int(self.shown * 100 + 0.5)}%")
            if active or self.shown != self.target:
                self.job = self.app.cv.after(30, self._tick)
        except tk.TclError:
            pass


# ======================================================================
#  Aplikasi
# ======================================================================
class Vidrop:
    def __init__(self):
        enable_dpi()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Vidrop")
        self.root.resizable(False, False)

        self.settings = load_settings()
        set_lang(resolve_lang(self.settings["lang"]))
        self.history = load_history()

        dpi = 1.0 if IS_MAC else self.root.winfo_fpixels("1i") / 96.0
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        fit = min((sw - 40) / BASE_W, (sh - (130 if IS_WIN else 110)) / BASE_H)
        self.S = max(0.65, min(dpi, fit, 2.0))
        self.g = Gfx(self.root, self.S)
        self.W, self.H = self.g.u(BASE_W), self.g.u(BASE_H)

        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.engine_ready = threading.Event()
        self.deno_path = None
        self.popup, self.popup_owner, self.last_closed = None, None, (None, 0)
        self.dialog, self.keep = None, []
        self._text_jobs, self.cv, self.entry = {}, None, None

        # --- unduh ---
        self.info, self.platform, self.info_img = None, None, None
        self.quality_limits = {tr("q_best"): None}
        self.dstate, self.mode = "idle", "video"           # idle | analyzing | ready | downloading
        self.touched, self._last_ui = set(), 0
        self._streams, self._weights, self._overall, self._split = [], [1.0], 0.0, False
        self.last_dir = self.settings["save_dir"]
        self.placeholder_on, self.url_text = True, ""
        self.status_d_text, self.status_d_color = None, MUTED
        # --- konversi ---
        self.cstate = "idle"                                # idle | ready | converting
        self.files, self.ccat, self.converter = [], None, None
        self.last_cdir = self.settings["save_dir"]
        self.status_c_text, self.status_c_color = None, MUTED
        self.page = "download"

        self._set_window_icon()
        self._build()

        sw_, sh_ = sw, sh
        x = (sw_ - self.W) // 2
        y = max(0, (sh_ - self.H) // 2 - self.g.u(20))
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self.root.deiconify()
        dark_titlebar(self.root)
        self.root.after(150, lambda: set_win_icon(self.root, resource("assets", "vidrop.ico")))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Button-1>", self._outside_click, add="+")
        self.root.bind("<Configure>", self._on_window_moved, add="+")
        self.root.after(30, self._pump)
        threading.Thread(target=self._prepare_engine, daemon=True).start()

    # ---------------------------------------------------------------- util
    @property
    def busy(self):
        return self.dstate in ("analyzing", "downloading") or self.cstate == "converting"

    def post(self, fn, *a):
        self.q.put((fn, a))

    def _pump(self):
        try:
            while True:
                fn, a = self.q.get_nowait()
                fn(*a)
        except queue.Empty:
            pass
        self.root.after(30, self._pump)

    def _set_window_icon(self):
        try:
            logo = Image.open(resource("assets", "vidrop.png")).convert("RGBA")
            self.keep.append(ImageTk.PhotoImage(logo.resize((128, 128), RS.LANCZOS)))
            self.root.iconphoto(True, self.keep[-1])
        except Exception:
            pass
        if IS_WIN:
            try:
                self.root.iconbitmap(default=resource("assets", "vidrop.ico"))
            except Exception:
                pass

    def text_anim(self, item, c0, c1, dur=0.25):
        old = self._text_jobs.pop(item, None)
        if old:
            old.cancel()
        self._text_jobs[item] = Anim(self.cv, dur, lambda t: self.cv.itemconfigure(item, fill=hx(lerp_color(c0, c1, t))), ease_out)

    # ---------------------------------------------------------------- popup dropdown
    def popup_in(self, pop):
        rx, ry, off = pop._anim

        def fn(t):
            try:
                pop.attributes("-alpha", t)
            except Exception:
                pass
            pop.geometry(f"+{rx}+{int(ry + off * (1 - t))}")

        Anim(pop, 0.22, fn, ease_out5)

    def popup_out(self, pop):
        rx, ry, off = pop._anim

        def fn(t):
            try:
                pop.attributes("-alpha", max(0.0, 1 - t))
            except Exception:
                pass
            pop.geometry(f"+{rx}+{int(ry + off * t * 0.8)}")

        def done():
            try:
                pop.destroy()
            except Exception:
                pass

        Anim(pop, 0.13, fn, ease_in, done)

    def close_popup(self):
        if self.popup is not None:
            pop, owner = self.popup, self.popup_owner
            self.popup, self.popup_owner = None, None
            self.last_closed = (owner, time.time())
            if owner is not None:
                owner.on_popup_closed()
            self.popup_out(pop)

    def _outside_click(self, e):
        if self.popup is not None:
            self.close_popup()

    def _on_window_moved(self, e):
        if e.widget is self.root:
            self.close_popup()

    def _on_close(self):
        if self.busy and self.dstate != "analyzing":
            if not messagebox.askyesno("Vidrop", tr("busy_close")):
                return
            self.cancel.set()
            if self.converter:
                self.converter.cancel()
        save_settings(self.settings)
        self.root.destroy()

    # ---------------------------------------------------------------- membangun UI
    def _build(self):
        g, u = self.g, self.g.u
        W, H = self.W, self.H
        if self.entry is not None:
            self.entry.destroy()
        if self.cv is not None:
            self.cv.destroy()
        self._text_jobs = {}
        self.cv = cv = tk.Canvas(self.root, width=W, height=H, bg=hx((84, 70, 130)), highlightthickness=0, bd=0)
        cv.pack()

        px, py, pw, ph, rail = u(28), u(28), u(924), u(644), u(76)
        self.L = L = dict(px=px, py=py, pw=pw, ph=ph, rail=rail, lx=u(130), lw=u(252), rx=u(396), rw=u(530),
                          y0=u(120), r1=(u(120), u(116)), r2=(u(250), u(120)), r3=(u(384), u(124)), r4=(u(522), u(122)),
                          colh=u(524), ip=u(16))
        scene = g.make_bg(W, H)
        g.panel(scene, px, py, pw, ph, u(36), rail)
        g.card(scene, L["lx"], L["y0"], L["lw"], L["colh"], u(24))
        for (y, h) in (L["r1"], L["r2"], L["r3"], L["r4"]):
            g.card(scene, L["rx"], y, L["rw"], h, u(22))
        L["fw"], L["fh"] = L["rw"] - 2 * L["ip"] - u(48) - u(12), u(48)
        L["fx"], L["fy"] = L["rx"] + L["ip"], L["r1"][0] + L["ip"]
        self.field_color = g.inset(scene, L["fx"], L["fy"], L["fw"], L["fh"], u(14))
        self.scene = scene
        self.scene_img = ImageTk.PhotoImage(scene)
        cv.create_image(0, 0, anchor="nw", image=self.scene_img)

        self._build_sidebar()
        self._build_header_shared()
        self._build_history()

        self.page_items, self.saved = {}, {}
        before = set(cv.find_all())
        self._build_download_page()
        self.page_items["download"] = sorted(set(cv.find_all()) - before)
        before = set(cv.find_all())
        self._build_convert_page()
        self.page_items["convert"] = sorted(set(cv.find_all()) - before)

        cv.create_text(L["rx"] + L["rw"] // 2 - u(133), py + ph - u(16), text=tr("legal"), font=g.font(10), fill=hx(DIM))

        # tirai transisi halaman: strip header + kolom kanan
        self.curtains = []
        for (x0, y0, x1, y1) in ((L["lx"] - u(4), py + u(10), L["rx"] + L["rw"] + u(4), L["y0"] - u(8)),
                                 (L["rx"] - u(6), L["y0"] - u(6), L["rx"] + L["rw"] + u(6), L["y0"] + L["colh"] + u(6))):
            img = scene.crop((x0, y0, x1, y1)).convert("RGBA")
            item = cv.create_image(x0, y0, anchor="nw", state="hidden")
            self.curtains.append([img, item, None])

        self._restore_after_build()

    def _restore_after_build(self):
        """Isi ulang tampilan dari state yang tersimpan (dipakai juga saat ganti bahasa)."""
        self._update_seg_labels()
        self._render_download_info()
        self._refresh_quality()
        self._update_convert_view(restore=True)
        self.refresh_history()
        self.set_status_d(self.status_d_text or tr("st_ready"), self.status_d_color)
        if self.status_c_text:
            self.set_status_c(self.status_c_text, self.status_c_color)
        if self.url_text:
            self.set_url(self.url_text)
        self._apply_page(self.page)

    # ---------------------------------------------------------------- sidebar + header + riwayat
    def _build_sidebar(self):
        g, u, cv, L = self.g, self.g.u, self.cv, self.L
        cx = L["px"] + L["rail"] // 2
        self.rail_cx = cx
        try:
            logo = Image.open(resource("assets", "vidrop.png")).convert("RGBA")
            self.logo_img = ImageTk.PhotoImage(logo.resize((u(44), u(44)), RS.LANCZOS))
            cv.create_image(cx, L["py"] + u(46), anchor="center", image=self.logo_img)
        except Exception:
            pass
        self.nav_y = {"download": L["py"] + u(130), "convert": L["py"] + u(200), "folder": L["py"] + u(270)}
        self.nav_active = self.page
        self.nav_pill_photo = ImageTk.PhotoImage(g.button_img(u(42), u(42), "glass", "normal"))
        self.nav_pill = cv.create_image(cx, self.nav_y[self.page] - u(9), anchor="center", image=self.nav_pill_photo)
        bar = Image.new("RGBA", (u(4), u(30)), (0, 0, 0, 0))
        bar.alpha_composite(tint((255, 255, 255), g.rr_mask(u(4), u(30), u(2))))
        self.nav_bar_photo = ImageTk.PhotoImage(bar)
        self.nav_bar = cv.create_image(L["px"] + u(8), self.nav_y[self.page] - u(9), anchor="w", image=self.nav_bar_photo)
        self.nav_items = {}
        for key, icon, label in (("download", "download", "nav_download"), ("convert", "convert", "nav_convert"),
                                 ("folder", "folder", "nav_folder")):
            cy = self.nav_y[key]
            dim = ImageTk.PhotoImage(g.icon(icon, u(24), (255, 255, 255), 170))
            bright = ImageTk.PhotoImage(g.icon(icon, u(24), (255, 255, 255), 255))
            self.keep += [dim, bright]
            ic = cv.create_image(cx, cy - u(8), anchor="center", image=dim, state="disabled")
            tx = cv.create_text(cx, cy + u(19), text=tr(label), font=g.font(10), fill=hx(MUTED), state="disabled")
            hit_img = ImageTk.PhotoImage(Image.new("RGBA", (L["rail"] - u(8), u(62)), (0, 0, 0, 0)))
            self.keep.append(hit_img)
            hit = cv.create_image(cx, cy, anchor="center", image=hit_img)
            cv.tag_bind(hit, "<ButtonRelease-1>", lambda e, k=key: self._nav_click(k))
            cv.tag_bind(hit, "<Enter>", lambda e, k=key: self._nav_hover(k, True))
            cv.tag_bind(hit, "<Leave>", lambda e, k=key: self._nav_hover(k, False))
            self.nav_items[key] = dict(icon=ic, text=tx, dim=dim, bright=bright)
        # tombol bahasa (cincin gradien seperti avatar pada referensi)
        ay = L["py"] + L["ph"] - u(54)
        self.ring_photo = ImageTk.PhotoImage(g.ring_avatar(u(44)))
        ring = cv.create_image(cx, ay, anchor="center", image=self.ring_photo)
        cv.create_text(cx, ay, text=get_lang().upper(), font=g.font(11, True), fill="white", state="disabled")
        cv.tag_bind(ring, "<ButtonRelease-1>", lambda e: self.toggle_language())
        cv.tag_bind(ring, "<Enter>", lambda e: cv.configure(cursor="hand2"))
        cv.tag_bind(ring, "<Leave>", lambda e: cv.configure(cursor=""))
        self._nav_style()

    def _nav_style(self):
        for k, it in self.nav_items.items():
            on = (k == self.nav_active)
            self.cv.itemconfigure(it["icon"], image=it["bright"] if on else it["dim"])
            self.cv.itemconfigure(it["text"], fill="white" if on else hx(MUTED))

    def _nav_hover(self, key, on):
        it = self.nav_items[key]
        self.cv.configure(cursor="hand2" if on else "")
        if key != self.nav_active:
            self.cv.itemconfigure(it["icon"], image=it["bright"] if on else it["dim"])
            self.cv.itemconfigure(it["text"], fill="white" if on else hx(MUTED))

    def _nav_click(self, key):
        if key == "folder":
            return open_folder(self._current_dir())
        if key == self.page:
            return
        if self.busy:
            return self._flash(tr("busy"))
        self.switch_page(key)

    def _current_dir(self):
        return self.settings["save_dir"] if self.page == "download" else self._convert_dir()

    def _flash(self, text):
        (self.set_status_d if self.page == "download" else self.set_status_c)(text, ERR, remember=False)

    def toggle_language(self):
        if self.busy:
            return self._flash(tr("busy"))
        self.set_language("en" if get_lang() == "id" else "id")

    def set_language(self, code):
        """code: 'auto' | 'id' | 'en'."""
        self.settings["lang"] = code
        save_settings(self.settings)
        set_lang(resolve_lang(code))
        dlg = self.dialog is not None
        if dlg:
            self.dialog.close()
        self.status_d_text = None
        self.status_c_text = None
        self._text_jobs = {}
        self.close_popup()
        self._build()
        if dlg:
            self.root.after(60, self.open_settings)

    def _build_header_shared(self):
        g, u, cv, L = self.g, self.g.u, self.cv, self.L
        self.gear = Button(g, cv, L["rx"] + L["rw"] - u(40), u(54), u(40), u(40), "", "glass", self.open_settings, icon="gear")

    def _build_history(self):
        g, u, cv, L = self.g, self.g.u, self.cv, self.L
        lx, lw, y0 = L["lx"], L["lw"], L["y0"]
        cv.create_text(lx + u(20), y0 + u(30), anchor="w", text=tr("recent"), font=g.font(15, True), fill="white")
        self.btn_dots = Button(g, cv, lx + lw - u(52), y0 + u(12), u(36), u(36), "", "glass", self.clear_history, icon="dots")
        self.rows = []
        row_h = u(62)
        top = y0 + u(58)
        self.row_h = row_h
        hov_img = ImageTk.PhotoImage(g.row_hover(lw - u(24), row_h - u(6)))
        self.keep.append(hov_img)
        for i in range(6):
            y = top + i * row_h
            hov = cv.create_image(lx + u(12), y, anchor="nw", image=hov_img, state="hidden")
            av = cv.create_image(lx + u(24), y + row_h // 2 - u(3), anchor="w", state="hidden")
            t1 = cv.create_text(lx + u(76), y + row_h // 2 - u(12), anchor="w", text="", font=g.font(12, True), fill="white", state="disabled")
            t2 = cv.create_text(lx + u(76), y + row_h // 2 + u(8), anchor="w", text="", font=g.font(11), fill=hx(MUTED), state="disabled")
            hit_img = ImageTk.PhotoImage(Image.new("RGBA", (lw - u(24), row_h - u(6)), (0, 0, 0, 0)))
            self.keep.append(hit_img)
            hit = cv.create_image(lx + u(12), y, anchor="nw", image=hit_img)
            cv.tag_bind(hit, "<Enter>", lambda e, i=i: self._row_hover(i, True))
            cv.tag_bind(hit, "<Leave>", lambda e, i=i: self._row_hover(i, False))
            cv.tag_bind(hit, "<ButtonRelease-1>", lambda e, i=i: self._row_click(i))
            self.rows.append(dict(hov=hov, av=av, t1=t1, t2=t2, photo=None, has=False))
        # keadaan kosong
        ey = top + u(110)
        self.empty_icon_photo = ImageTk.PhotoImage(g.icon("download", u(40), (255, 255, 255), 90))
        self.empty_icon = cv.create_image(lx + lw // 2, ey, anchor="center", image=self.empty_icon_photo)
        self.empty_t1 = cv.create_text(lx + lw // 2, ey + u(44), text=tr("recent_empty"), font=g.font(13, True), fill=hx(MUTED))
        self.empty_t2 = cv.create_text(lx + lw // 2, ey + u(66), text=tr("recent_empty_sub"), font=g.font(11), fill=hx(DIM),
                                       width=lw - u(48), justify="center")
        self.btn_folder_h = Button(g, cv, lx + u(16), y0 + L["colh"] - u(16) - u(44), lw - u(32), u(44), tr("open_folder"),
                                   "primary", lambda: open_folder(self._current_dir()), size=13)

    def refresh_history(self):
        g, u, cv = self.g, self.g.u, self.cv
        show = self.history[:6]
        names = {"dl_video": "h_video", "dl_audio": "h_audio", "dl_thumb": "h_thumb", "conv": "h_conv"}
        for i, row in enumerate(self.rows):
            if i < len(show):
                h = show[i]
                row["photo"] = ImageTk.PhotoImage(g.avatar(u(40), h.get("t", "dl_video")))
                cv.itemconfigure(row["av"], image=row["photo"], state="normal")
                cv.itemconfigure(row["t1"], text=ellipsize(g.font(12, True), h["name"], self.L["lw"] - u(100)), state="disabled")
                cv.itemconfigure(row["t2"], text=f"{tr(names.get(h.get('t'), 'h_video'))} · {ago_text(h.get('ts', time.time()))}", state="disabled")
                row["has"] = True
            else:
                for k in ("av", "t1", "t2", "hov"):
                    cv.itemconfigure(row[k], state="hidden")
                row["has"] = False
        empty = not show
        for it in (self.empty_icon, self.empty_t1, self.empty_t2):
            cv.itemconfigure(it, state="normal" if empty else "hidden")

    def _row_hover(self, i, on):
        if self.rows[i]["has"]:
            self.cv.itemconfigure(self.rows[i]["hov"], state="normal" if on else "hidden")
            self.cv.configure(cursor="hand2" if on else "")

    def _row_click(self, i):
        if i < len(self.history):
            reveal_file(self.history[i].get("path", ""))

    def add_activity(self, kind, name, path):
        self.history.insert(0, {"t": kind, "name": name, "path": path, "ts": time.time()})
        self.history = self.history[:HISTORY_MAX]
        save_history(self.history)
        self.refresh_history()

    def clear_history(self):
        if self.history and messagebox.askyesno("Vidrop", tr("clear_history_q")):
            self.history = []
            save_history(self.history)
            self.refresh_history()

    # ---------------------------------------------------------------- transisi halaman
    def _apply_page(self, name):
        self.page = name
        self.nav_active = name
        self._nav_style()
        y = self.nav_y[name] - self.g.u(9)
        self.cv.coords(self.nav_pill, self.rail_cx, y)
        self.cv.coords(self.nav_bar, self.L["px"] + self.g.u(8), y)
        other = "convert" if name == "download" else "download"
        self._hide_page(other)
        if name == "convert" and self.entry_item is not None:
            self.cv.itemconfigure(self.entry_item, state="hidden")

    def _hide_page(self, name):
        saved = {}
        for i in self.page_items[name]:
            saved[i] = self.cv.itemcget(i, "state") or "normal"
            self.cv.itemconfigure(i, state="hidden")
        if name == "download":
            saved[self.entry_item] = "normal"
        self.saved[name] = saved

    def _show_page(self, name):
        for i, st in self.saved.get(name, {}).items():
            self.cv.itemconfigure(i, state=st)
        if name == "convert":
            for i in self.page_items["convert"]:
                pass

    def switch_page(self, new):
        old, self.page = self.page, new
        self.nav_active = new
        self._nav_style()
        y0 = self.cv.coords(self.nav_bar)[1]
        y1 = self.nav_y[new] - self.g.u(9)
        bx = self.cv.coords(self.nav_bar)[0]

        def mv(t):
            y = y0 + (y1 - y0) * t
            self.cv.coords(self.nav_bar, bx, y)
            self.cv.coords(self.nav_pill, self.rail_cx, y)

        Anim(self.cv, 0.38, mv, ease_out_back_soft)
        if old == "download":
            self.cv.itemconfigure(self.entry_item, state="hidden")
        for c in self.curtains:
            self.cv.itemconfigure(c[1], state="normal")

        def veil(a):
            for c in self.curtains:
                img = c[0].copy()
                img.putalpha(Image.new("L", img.size, int(255 * a)))
                c[2] = ImageTk.PhotoImage(img)
                self.cv.itemconfigure(c[1], image=c[2])

        def swap():
            self._hide_page(old)
            self._show_page(new)
            for c in self.curtains:
                self.cv.tag_raise(c[1])
            Anim(self.cv, 0.26, lambda t: veil(1 - t), ease_out,
                 lambda: [self.cv.itemconfigure(c[1], state="hidden") for c in self.curtains])

        Anim(self.cv, 0.15, veil, ease_in, swap)

    # ---------------------------------------------------------------- bantu halaman
    def _title(self, key):
        g, u, cv, L = self.g, self.g.u, self.cv, self.L
        cv.create_text(L["lx"] + u(2), u(74), anchor="w", text=tr(key), font=g.font(28, True), fill="white")

    def _folder_row(self, y, get_dir, on_change):
        g, u, cv, L = self.g, self.g.u, self.cv, self.L
        h = u(34)
        x0 = L["rx"] + L["ip"]
        cv.create_text(x0 + u(2), y + h // 2, anchor="w", text=tr("save_in"), font=g.font(12), fill=hx(MUTED))
        fx = x0 + u(74)
        item = cv.create_text(fx, y + h // 2, anchor="w", text="", font=g.font(12), fill="white")
        bw = u(84)
        btn = Button(g, cv, L["rx"] + L["rw"] - L["ip"] - bw, y, bw, h, tr("change"), "glass", on_change, size=12, bold=False)
        maxw = (L["rx"] + L["rw"] - L["ip"] - bw) - fx - u(14)

        def refresh():
            cv.itemconfigure(item, text=ellipsize(g.font(12), get_dir(), maxw, left=True))

        refresh()
        return refresh, btn

    def _action_card(self, with_chart):
        """Kartu kanan-bawah: (grafik/status) + persen + tombol aksi + progress."""
        g, u, cv, L = self.g, self.g.u, self.cv, self.L
        y4, h4 = L["r4"]
        x0 = L["rx"] + L["ip"]
        lw_ = u(296)
        zx = x0 + lw_ + u(20)
        zw = L["rx"] + L["rw"] - L["ip"] - zx
        status = cv.create_text(x0, y4 + u(14), anchor="nw", width=lw_, text="", font=g.font(12), fill=hx(MUTED))
        chart_item = chart_wh = None
        if with_chart:
            chart_wh = (lw_, u(40))
            chart_item = cv.create_image(x0, y4 + u(48), anchor="nw")
        pct = cv.create_text(zx, y4 + u(12), anchor="nw", text="0%", font=g.font(30, True), fill="white")
        cap = cv.create_text(zx, y4 + u(54), anchor="nw", width=zw, text="", font=g.font(11), fill=hx(MUTED))
        btn = Button(g, cv, zx, y4 + h4 - u(14) - u(40), zw, u(40), "", "primary", None, size=13)
        meter = Meter(self, (x0, y4 + h4 - u(26), lw_, u(6)), pct, None, chart_item, chart_wh)
        return dict(status=status, pct=pct, cap=cap, btn=btn, meter=meter, zw=zw, lw=lw_)

    # ================================================================ HALAMAN UNDUH
    def _build_download_page(self):
        g, u, cv, L = self.g, self.g.u, self.cv, self.L
        ip, fh = L["ip"], L["fh"]
        self._title("title_download")
        self.btn_paste_h = Button(g, cv, L["rx"] + L["rw"] - u(40) - u(12) - u(150), u(54), u(150), u(40), tr("paste_link"),
                                  "primary", self.paste_and_analyze, size=13)

        # --- R1: link ---
        self.url_var = tk.StringVar()
        self.link_icon_photo = ImageTk.PhotoImage(g.icon("link", u(20), (255, 255, 255), 190))
        cv.create_image(L["fx"] + u(18), L["fy"] + fh // 2, anchor="w", image=self.link_icon_photo)
        self.entry = tk.Entry(self.root, textvariable=self.url_var, bd=0, relief="flat", bg=hx(self.field_color), fg="white",
                              insertbackground="white", selectbackground=hx((120, 96, 190)), selectforeground="white",
                              highlightthickness=0, font=g.font(13))
        self.entry_item = cv.create_window(L["fx"] + u(48), L["fy"] + u(9), anchor="nw", window=self.entry,
                                           width=L["fw"] - u(64), height=fh - u(18))
        self.entry.bind("<Return>", lambda e: self.analyze())
        self.entry.bind("<FocusIn>", self._entry_focus_in)
        self.entry.bind("<FocusOut>", self._entry_focus_out)
        self.entry.bind("<<Paste>>", lambda e: self.root.after(120, self._auto_after_paste), add="+")
        for seq in (("<Button-3>", "<Button-2>", "<Control-Button-1>") if IS_MAC else ("<Button-3>",)):
            self.entry.bind(seq, self._entry_menu)
        self.placeholder_on = True
        self._set_placeholder()
        self.url_var.trace_add("write", lambda *a: self._on_url_change())
        self.btn_check = Button(g, cv, L["fx"] + L["fw"] + u(12), L["fy"], u(48), u(48), "", "primary", self.analyze, icon="send")
        specs = [(k, n) for k, n, _ in PLATFORMS] + [(OTHER_KEY, tr("other_sites"))]
        self.chips = ChipRow(self, specs, L["fx"], L["fy"] + fh + u(12), u(26))

        # --- R2: preview ---
        y2, h2 = L["r2"]
        tw, th = u(160), u(90)
        tx0, ty0 = L["rx"] + ip, y2 + (h2 - th) // 2
        self.thumb_w, self.thumb_h = tw, th
        self.thumb_item = cv.create_image(tx0, ty0, anchor="nw")
        self.thumb_fade = Crossfade(cv, self.thumb_item)
        self.thumb_fade.show(g.round_thumb(None, tw, th, u(14)))
        mx = tx0 + tw + u(20)
        mw = L["rx"] + L["rw"] - ip - mx
        self.meta_w = mw
        self.title_item = cv.create_text(mx, ty0 + u(2), anchor="nw", text=tr("no_video"), font=g.font(15, True), fill=hx(MUTED), width=mw)
        self.line2 = cv.create_text(mx, ty0 + u(52), anchor="nw", text=tr("preview_hint"), font=g.font(12), fill=hx(MUTED), width=mw)
        self.line3 = cv.create_text(mx, ty0 + u(72), anchor="nw", text="", font=g.font(12, True), fill="white", width=mw)

        # --- R3: format + folder ---
        y3, h3 = L["r3"]
        sy = y3 + u(18)
        sw_ = u(300)
        self.seg = Segmented(self, L["rx"] + ip, sy, sw_, u(40), ["", "", ""], self._on_mode_changed)
        qx = L["rx"] + ip + sw_ + u(12)
        self.quality_dd = Dropdown(self, cv, qx, sy, L["rx"] + L["rw"] - ip - qx, u(40), [tr("q_best")], tr("q_best"), None, size=12)
        self.refresh_dir_d, self.btn_folder_d = self._folder_row(sy + u(40) + u(16), lambda: self.settings["save_dir"], self.choose_folder)

        # --- R4: grafik kecepatan + persen + aksi ---
        a = self._action_card(with_chart=True)
        self.ad = a
        self.status_d, self.cap_d, self.btn_main, self.prog_d = a["status"], a["cap"], a["btn"], a["meter"]
        self.prog_d.active_fn = lambda: self.dstate == "downloading"
        self.btn_main.cmd = self._main_action
        self.btn_main.configure(enabled=False, text=tr("dl_video", fmt=self.settings["video_fmt"]))

    # ---- entry ----
    def _set_placeholder(self):
        self.placeholder_on = True
        self.entry.delete(0, "end")
        self.entry.insert(0, tr("link_placeholder"))
        self.entry.configure(fg=hx(DIM))

    def _entry_focus_in(self, e):
        if self.placeholder_on:
            self.placeholder_on = False
            self.entry.delete(0, "end")
            self.entry.configure(fg="white")

    def _entry_focus_out(self, e):
        if not self.entry.get().strip():
            self._set_placeholder()

    def _entry_menu(self, e):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Paste" if get_lang() == "en" else "Tempel", command=lambda: self.entry.event_generate("<<Paste>>"))
        m.add_command(label="Copy" if get_lang() == "en" else "Salin", command=lambda: self.entry.event_generate("<<Copy>>"))
        m.add_command(label="Clear" if get_lang() == "en" else "Hapus", command=lambda: (self.entry.focus_set(), self.entry.delete(0, "end")))
        m.tk_popup(e.x_root, e.y_root)

    def get_url(self):
        return "" if self.placeholder_on else self.entry.get().strip()

    def set_url(self, text):
        self.placeholder_on = False
        self.entry.configure(fg="white")
        self.entry.delete(0, "end")
        self.entry.insert(0, text)

    def _on_url_change(self):
        self.url_text = self.get_url()
        if self.dstate in ("analyzing", "downloading"):
            return
        key = detect_platform(self.get_url())
        self.set_platform(key if key != BLOCKED_KEY else None)

    def _auto_after_paste(self):
        url = self.get_url()
        if url and detect_platform(url):
            self.analyze()

    def set_platform(self, key):
        self.chips.set(key)
        self.platform = self.chips.active

    # ---- segmen & kualitas ----
    def _update_seg_labels(self):
        for t, k in zip(self.seg.texts, ("seg_video", "seg_audio", "seg_thumb")):
            self.cv.itemconfigure(t, text=tr(k))

    def _on_mode_changed(self, idx):
        self.mode = ("video", "audio", "thumb")[idx]
        self._refresh_quality()

    def _refresh_quality(self):
        s = self.settings
        self.seg.select(("video", "audio", "thumb").index(self.mode), animate=False)
        if self.mode == "video":
            labels = list(self.quality_limits.keys())
            self.quality_dd.set_values(labels, labels[0])
            self.quality_dd.set_enabled(True)
            self.btn_main.configure(text=tr("dl_video", fmt=s["video_fmt"]))
        elif self.mode == "audio":
            if s["audio_fmt"] in LOSSLESS:
                self.quality_dd.set_values(["Lossless"])
                self.quality_dd.set_enabled(False)
            else:
                vals = [a for a, _ in audio_quality_options()]
                self.quality_dd.set_values(vals, vals[0])
                self.quality_dd.set_enabled(True)
            self.btn_main.configure(text=tr("dl_audio", fmt=s["audio_fmt"]))
        else:
            self.quality_dd.set_values([tr("thumb_best")])
            self.quality_dd.set_enabled(False)
            self.btn_main.configure(text=tr("dl_thumb", fmt=s["thumb_fmt"]))

    def choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.settings["save_dir"])
        if d:
            self.settings["save_dir"] = d
            self.last_dir = d
            save_settings(self.settings)
            self.refresh_dir_d()
            self.refresh_dir_c()

    def set_status_d(self, text, color=MUTED, remember=True):
        if remember:
            self.status_d_text, self.status_d_color = text, color
        self.cv.itemconfigure(self.status_d, text=ellipsize(self.g.font(12), text, self.ad["lw"] * 2 - self.g.u(28)), fill=hx(color))

    # ---- komponen YouTube ----
    def _prepare_engine(self):
        try:
            path = find_deno()
            if not path and deno_url():
                self.post(self.set_status_d, tr("st_engine_prep"), MUTED)

                def prog(done, total):
                    if total:
                        self.post(self.set_status_d, tr("st_engine_prep_pct", pct=done * 100 // total), MUTED)

                path = download_deno(prog)
            self.deno_path = path
        except Exception:
            self.deno_path = None
        finally:
            self.engine_ready.set()
            self.post(self._engine_done)

    def _engine_done(self):
        if self.dstate == "idle":
            if self.deno_path or not deno_url():
                self.set_status_d(tr("st_ready"), MUTED)
            else:
                self.set_status_d(tr("st_engine_fail"), ERR)

    def base_opts(self):
        o = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
             "windowsfilenames": True, "retries": 5, "fragment_retries": 5, "socket_timeout": 30,
             "logger": QuietLogger(), "playlist_items": "1"}
        if FFMPEG:
            o["ffmpeg_location"] = FFMPEG
        if self.deno_path:
            o["js_runtimes"] = {"deno": {"path": self.deno_path}}
        return o

    # ---- cek link ----
    def paste_and_analyze(self):
        if self.busy:
            return
        try:
            text = self.root.clipboard_get().strip()
        except Exception:
            text = ""
        if text:
            self.set_url(text)
            self.analyze()

    def analyze(self):
        if self.busy:
            return
        url = self.get_url()
        if not url:
            return self.set_status_d(tr("st_empty_link"), ERR)
        if not re.match(r"^https?://", url):
            url = "https://" + url
            self.set_url(url)
        plat = detect_platform(url)
        if plat == BLOCKED_KEY:                       # layanan yang selalu butuh login: tidak didukung
            self.set_platform(None)
            return self.set_status_d(tr("st_blocked"), ERR)
        self.set_platform(plat)
        self.dstate = "analyzing"
        self.btn_check.configure(enabled=False)
        self.btn_paste_h.configure(enabled=False)
        self.btn_main.configure(enabled=False)
        self.prog_d.reset()
        self.cv.itemconfigure(self.cap_d, text="")
        self.set_status_d(tr("st_fetch"), MUTED)
        threading.Thread(target=self._analyze_worker, args=(url, plat), daemon=True).start()

    def _analyze_worker(self, url, plat):
        try:
            if not self.engine_ready.is_set() and plat == "youtube":
                self.post(self.set_status_d, tr("st_wait_engine"), MUTED)
                self.engine_ready.wait(timeout=180)
            opts = self.base_opts()
            opts["skip_download"] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info.get("entries"):
                info = next(e for e in info["entries"] if e)
            img = None
            if info.get("thumbnail"):
                try:
                    data = urllib.request.urlopen(urllib.request.Request(
                        info["thumbnail"], headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read()
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                except Exception:
                    img = None
            self.post(self._analyze_done, info, img)
        except Exception as e:
            self.post(self._analyze_fail, str(e))

    def _analyze_done(self, info, img):
        self.info, self.info_img = info, img
        self.dstate = "ready"
        self.btn_check.configure(enabled=True)
        self.btn_paste_h.configure(enabled=True)
        self.btn_main.configure(enabled=True)
        key = EXTRACTOR_TO_KEY.get((info.get("extractor_key") or "").lower().split(":")[0])
        self.set_platform(key or (self.platform or OTHER_KEY))
        self._render_download_info(animate=True)
        self.set_status_d(tr("st_valid"), OK)

    def _render_download_info(self, animate=False):
        """Isi kartu preview dari self.info (juga dipakai saat ganti bahasa)."""
        info, g = self.info, self.g
        if not info:
            return
        title = info.get("title") or tr("no_title")
        self.cv.itemconfigure(self.title_item, text=ellipsize(g.font(15, True), title, self.meta_w * 2 - g.u(40)))
        who = info.get("uploader") or info.get("channel") or "-"
        self.cv.itemconfigure(self.line2, text=f"{who}  ·  {fmt_duration(info.get('duration'))}")
        opts = build_quality_options(info)
        self.quality_limits = {lab: lim for lab, lim in opts}
        self._split = any(f.get("vcodec") not in (None, "none") and f.get("acodec") in (None, "none") for f in info.get("formats") or [])
        plat = PLATFORM_NAMES.get(self.platform, info.get("extractor_key") or "")
        top = re.sub(r"^[^·]*·\s*", "", opts[0][0]) if "·" in opts[0][0] else opts[0][0]
        self.cv.itemconfigure(self.line3, text=f"{plat}  ·  {tr('up_to', res=top)}")
        pil = g.round_thumb(self.info_img, self.thumb_w, self.thumb_h, g.u(14))
        if animate:
            for it, c0, c1, d in ((self.title_item, (150, 130, 200), "white", 0.4), (self.line2, (150, 130, 200), MUTED, 0.4),
                                  (self.line3, (150, 130, 200), "white", 0.5)):
                self.text_anim(it, c0, (255, 255, 255) if c1 == "white" else c1, d)
            self.thumb_fade.to(pil, 0.4)
        else:
            self.cv.itemconfigure(self.title_item, fill="white")
            self.cv.itemconfigure(self.line2, fill=hx(MUTED))
            self.thumb_fade.show(pil)
        self._refresh_quality()

    def _analyze_fail(self, err):
        self.dstate = "idle"
        self.btn_check.configure(enabled=True)
        self.btn_paste_h.configure(enabled=True)
        self.set_status_d(friendly_error(err), ERR)

    # ---- unduh / batal ----
    def _main_action(self):
        if self.dstate == "downloading":
            self.cancel.set()
            self.btn_main.configure(text=tr("cancelling"), enabled=False)
            self.set_status_d(tr("st_cancelling_dl"), MUTED)
        elif self.dstate == "ready":
            self.start_download()

    def start_download(self):
        if not self.info:
            return
        self.dstate = "downloading"
        self.cancel.clear()
        self.touched, self._last_ui = set(), 0
        mode, quality = self.mode, self.quality_dd.get()
        self._streams, self._overall = [], 0.0
        self._weights = [0.9, 0.1] if (mode == "video" and self._split) else [1.0]
        self.btn_main.configure(text=tr("cancel"), style="danger", enabled=True)
        self.btn_check.configure(enabled=False)
        self.btn_paste_h.configure(enabled=False)
        self.prog_d.reset()
        self.cv.itemconfigure(self.cap_d, text="")
        self.set_status_d(tr("st_start"), MUTED)
        url = self.info.get("webpage_url") or self.get_url()
        threading.Thread(target=self._download_worker, args=(mode, quality, url), daemon=True).start()

    def _overall_for(self, d):
        """Progress gabungan (video+audio) yang monoton naik."""
        name = d.get("filename")
        if name and name not in self._streams:
            self._streams.append(name)
        idx = self._streams.index(name) if name in self._streams else 0
        w = self._weights
        base = sum(w[:idx]) if idx < len(w) else sum(w)
        wi = w[idx] if idx < len(w) else 0.0
        if d["status"] == "finished":
            frac = 1.0
        else:
            fc, fi = d.get("fragment_count"), d.get("fragment_index")
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if fc and fi:
                frac = fi / fc
            else:
                frac = (d.get("downloaded_bytes", 0) / total) if total else 0.0
        self._overall = max(self._overall, min(1.0, base + wi * min(1.0, frac)))
        return self._overall

    def _hook(self, d):
        if self.cancel.is_set():
            raise Cancelled()
        for k in ("tmpfilename", "filename"):
            if d.get(k):
                self.touched.add(d[k])
        if d["status"] == "downloading":
            now = time.time()
            overall = self._overall_for(d)
            if now - self._last_ui < 0.12:
                return
            self._last_ui = now
            info = d.get("info_dict") or {}
            v = info.get("vcodec") not in (None, "none")
            a = info.get("acodec") not in (None, "none")
            kind = tr("kind_video") if v else (tr("kind_audio") if a else tr("kind_file"))
            speed = d.get("speed")
            cap = (f"{fmt_size(speed)}/s" if speed else "") + (f"  ·  {tr('st_eta', t=fmt_duration(d['eta']))}" if d.get("eta") is not None else "")
            self.post(self._show_progress_d, overall, tr("st_downloading", kind=kind, pct=int(overall * 100)), cap, speed)
        elif d["status"] == "finished":
            self.post(self._show_progress_d, self._overall_for(d), None, None, None)

    def _pp_hook(self, d):
        if d.get("status") == "started":
            self.post(self._on_processing)

    def _show_progress_d(self, frac, text, cap, speed):
        if self.dstate == "downloading":
            self.prog_d.set(frac)
            if text:
                self.set_status_d(text, MUTED)
            if cap is not None:
                self.cv.itemconfigure(self.cap_d, text=cap)
            if speed:
                self.prog_d.add_sample(speed / 1048576)

    def _on_processing(self):
        if self.dstate == "downloading":
            self.prog_d.set(1.0)
            self.set_status_d(tr("st_proc_file"), MUTED)
            self.btn_main.configure(text=tr("processing"), enabled=False)

    def _download_worker(self, mode, quality, url):
        try:
            out_dir = self.settings["save_dir"]
            os.makedirs(out_dir, exist_ok=True)
            if mode == "thumb":
                path = self._get_thumbnail(out_dir)
            else:
                try:
                    path = self._run_ydl(mode, quality, url, out_dir, self.settings["video_fmt"])
                except Exception as e:
                    msg = str(e).lower()
                    retry = (mode == "video" and self.settings["video_fmt"] != "MKV" and not self.cancel.is_set()
                             and any(k in msg for k in ("ffmpeg", "merge", "postprocess", "conversion")))
                    if not retry:
                        raise
                    self.post(self.set_status_d, tr("st_try_mkv"), MUTED)
                    path = self._run_ydl(mode, quality, url, out_dir, "MKV")
            self.post(self._download_done, mode, path or out_dir)
        except Exception as e:
            if self.cancel.is_set() or isinstance(e, DownloadCancelled):
                self._cleanup_partial()
                self.post(self._download_cancelled)
            else:
                self.post(self._download_fail, str(e))

    def _run_ydl(self, mode, quality, url, out_dir, vfmt):
        s = self.settings
        opts = self.base_opts()
        opts.update({"progress_hooks": [self._hook], "postprocessor_hooks": [self._pp_hook],
                     "outtmpl": os.path.join(out_dir, "%(title).150B.%(ext)s"), "concurrent_fragment_downloads": 4})
        if mode == "video":
            limit = self.quality_limits.get(quality)
            opts["format"] = f"bv*[height<={limit}]+ba/b[height<={limit}]/b" if limit else "bv*+ba/b"
            extra = {"MP4": ["ext:mp4:m4a"], "MKV": [], "WEBM": ["ext:webm:webm"]}[vfmt]
            opts["format_sort"] = ["res", "fps"] + extra
            opts["merge_output_format"] = vfmt.lower()
            if vfmt in ("MP4", "MKV"):
                opts["postprocessors"] = [{"key": "FFmpegVideoRemuxer", "preferedformat": vfmt.lower()}]
        else:
            pp = {"key": "FFmpegExtractAudio", "preferredcodec": s["audio_fmt"].lower()}
            if s["audio_fmt"] not in LOSSLESS:
                pp["preferredquality"] = dict(audio_quality_options()).get(quality, "320")
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [pp]
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info.get("entries"):
                info = next(e for e in info["entries"] if e)
            path = None
            for rd in info.get("requested_downloads") or []:
                path = rd.get("filepath") or path
        return path

    def _get_thumbnail(self, out_dir):
        info = self.info
        thumbs = [t for t in info.get("thumbnails", []) if t.get("url")]
        thumbs.sort(key=lambda t: ((t.get("preference") or 0), (t.get("width") or 0) * (t.get("height") or 0)), reverse=True)
        urls = [t["url"] for t in thumbs] or ([info["thumbnail"]] if info.get("thumbnail") else [])
        if not urls:
            raise RuntimeError("no thumbnail")
        fmt = self.settings["thumb_fmt"]
        ext = {"JPG": "jpg", "PNG": "png", "WEBP": "webp"}[fmt]
        last = None
        for u_ in urls[:8]:
            if self.cancel.is_set():
                raise Cancelled()
            try:
                self.post(self._show_progress_d, 0.4, tr("st_thumb"), "", None)
                data = urllib.request.urlopen(urllib.request.Request(u_, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
                img = Image.open(io.BytesIO(data)).convert("RGB")
                path = os.path.join(out_dir, safe_name(info.get("title")) + " - thumbnail." + ext)
                img.save(path, {"JPG": "JPEG", "PNG": "PNG", "WEBP": "WEBP"}[fmt], **({"quality": 95} if fmt != "PNG" else {}))
                return path
            except Exception as e:
                last = e
        raise RuntimeError(f"thumbnail: {last}")

    def _cleanup_partial(self):
        import glob
        for name in list(self.touched):
            for cand in (name + ".part", name + ".ytdl", name if name.endswith(".part") else None):
                if cand and os.path.isfile(cand):
                    try:
                        os.remove(cand)
                    except Exception:
                        pass
            for frag in glob.glob(glob.escape(name) + ".part-Frag*"):
                try:
                    os.remove(frag)
                except Exception:
                    pass

    def _finish_ui_d(self):
        self.dstate = "ready" if self.info else "idle"
        self.btn_main.configure(style="primary", enabled=True)
        self._refresh_quality()
        self.btn_check.configure(enabled=True)
        self.btn_paste_h.configure(enabled=True)

    def _download_done(self, mode, path):
        self._finish_ui_d()
        self.last_dir = os.path.dirname(path) if os.path.isfile(path) else path
        self.prog_d.set(1.0)
        name = os.path.basename(path) if os.path.isfile(path) else (self.info.get("title") or "")
        self.set_status_d(tr("st_done", name=ellipsize(self.g.font(12), name, self.g.u(260))), OK)
        self.cv.itemconfigure(self.cap_d, text="")
        self.add_activity({"video": "dl_video", "audio": "dl_audio", "thumb": "dl_thumb"}[mode], name, path)

    def _download_cancelled(self):
        self._finish_ui_d()
        self.prog_d.reset()
        self.cv.itemconfigure(self.cap_d, text="")
        self.set_status_d(tr("st_dl_cancelled"), MUTED)

    def _download_fail(self, err):
        self._finish_ui_d()
        self.prog_d.reset()
        self.cv.itemconfigure(self.cap_d, text="")
        self.set_status_d(friendly_error(err), ERR)

    # ================================================================ HALAMAN KONVERSI
    def _build_convert_page(self):
        g, u, cv, L = self.g, self.g.u, self.cv, self.L
        ip, fh = L["ip"], L["fh"]
        self._title("title_convert")
        self.btn_pick_h = Button(g, cv, L["rx"] + L["rw"] - u(40) - u(12) - u(150), u(54), u(150), u(40), tr("choose_file"),
                                 "primary", self.pick_files, size=13)

        # --- R1: pilih file ---
        self.folder_icon_photo = ImageTk.PhotoImage(g.icon("folder", u(20), (255, 255, 255), 190))
        cv.create_image(L["fx"] + u(18), L["fy"] + fh // 2, anchor="w", image=self.folder_icon_photo)
        self.file_text = cv.create_text(L["fx"] + u(48), L["fy"] + fh // 2, anchor="w", text=tr("cv_no_file"),
                                        font=g.font(13), fill=hx(DIM))
        hit_img = ImageTk.PhotoImage(Image.new("RGBA", (L["fw"], fh), (0, 0, 0, 0)))
        self.keep.append(hit_img)
        hit = cv.create_image(L["fx"], L["fy"], anchor="nw", image=hit_img)
        cv.tag_bind(hit, "<ButtonRelease-1>", lambda e: self.pick_files())
        cv.tag_bind(hit, "<Enter>", lambda e: cv.configure(cursor="hand2"))
        cv.tag_bind(hit, "<Leave>", lambda e: cv.configure(cursor=""))
        self.btn_clear = Button(g, cv, L["fx"] + L["fw"] + u(12), L["fy"], u(48), u(48), "", "glass", self.clear_files, icon="close")
        self.cchips = ChipRow(self, [("video", tr("cat_video")), ("audio", tr("cat_audio")), ("image", tr("cat_image"))],
                              L["fx"], L["fy"] + fh + u(12), u(26))
        cv.create_text(L["rx"] + L["rw"] - ip - u(2), L["fy"] + fh + u(12) + u(13), anchor="e",
                       text="MP4 · MKV · WEBM · GIF · MP3 · FLAC · JPG · PNG · WEBP …", font=g.font(9), fill=hx(DIM))

        # --- R2: ringkasan ---
        y2, h2 = L["r2"]
        tw, th = u(160), u(90)
        tx0, ty0 = L["rx"] + ip, y2 + (h2 - th) // 2
        self.tile_size = (tw, th)
        self.ctile_item = cv.create_image(tx0, ty0, anchor="nw")
        self.ctile_fade = Crossfade(cv, self.ctile_item)
        self.ctile_fade.show(g.glyph_tile(tw, th, u(14), "video"))
        mx = tx0 + tw + u(20)
        mw = L["rx"] + L["rw"] - ip - mx
        self.ctitle = cv.create_text(mx, ty0 + u(4), anchor="nw", text=tr("cv_no_files_title"), font=g.font(15, True), fill=hx(MUTED), width=mw)
        self.cline2 = cv.create_text(mx, ty0 + u(34), anchor="nw", text=tr("cv_pick_hint"), font=g.font(12), fill=hx(MUTED), width=mw)
        self.cline3 = cv.create_text(mx, ty0 + u(58), anchor="nw", text="", font=g.font(11), fill=hx(DIM), width=mw)

        # --- R3: opsi ---
        y3, h3 = L["r3"]
        cap_y, dd_y = y3 + u(16), y3 + u(28)
        colw = (L["rw"] - 2 * ip - 2 * u(12)) // 3
        self.ccaps, self.cdd = [], []
        caps = ["cap_format", "cap_quality", "cap_size"]
        for i in range(3):
            x = L["rx"] + ip + i * (colw + u(12))
            self.ccaps.append(cv.create_text(x + u(4), cap_y, anchor="w", text=tr(caps[i]), font=g.font(11), fill=hx(MUTED)))
            self.cdd.append(Dropdown(self, cv, x, dd_y, colw, u(40), ["-"], "-", [self._on_target_changed, None, None][i], size=12))
        self.refresh_dir_c, self.btn_folder_c = self._folder_row(dd_y + u(40) + u(12), self._convert_dir, self.choose_convert_folder)

        # --- R4: persen + aksi ---
        a = self._action_card(with_chart=False)
        self.ac = a
        self.status_c, self.cap_c, self.btn_conv, self.prog_c = a["status"], a["cap"], a["btn"], a["meter"]
        self.prog_c.active_fn = lambda: self.cstate == "converting"
        self.btn_conv.cmd = self._convert_action
        self.btn_conv.configure(enabled=False, text=tr("convert"))
        self.cv.itemconfigure(self.status_c, text=tr("cv_pick_status"))

    def _convert_dir(self):
        return self.settings["convert_dir"] or self.settings["save_dir"]

    def choose_convert_folder(self):
        d = filedialog.askdirectory(initialdir=self._convert_dir())
        if d:
            self.settings["convert_dir"] = d
            save_settings(self.settings)
            self.refresh_dir_c()

    def set_status_c(self, text, color=MUTED, remember=True):
        if remember:
            self.status_c_text, self.status_c_color = text, color
        self.cv.itemconfigure(self.status_c, text=text, fill=hx(color))

    def pick_files(self):
        if self.cstate == "converting":
            return
        if self.page != "convert" and not self.busy:
            self.switch_page("convert")
        paths = filedialog.askopenfilenames(title=tr("pick_dialog"), filetypes=CV.file_filters())
        if not paths:
            return
        paths = [p for p in paths if CV.category_of(p)]
        if not paths:
            return self.set_status_c(tr("cv_unsupported"), ERR)
        cat = CV.category_of(paths[0])
        same = [p for p in paths if CV.category_of(p) == cat]
        self.files, self.ccat = same, cat
        self._update_convert_view(skipped=len(paths) - len(same))

    def clear_files(self):
        if self.cstate == "converting":
            return
        self.files, self.ccat, self.cstate = [], None, "idle"
        self.btn_open_visible = False
        self.prog_c.reset()
        self.cv.itemconfigure(self.cap_c, text="")
        self._update_convert_view()

    def _update_convert_view(self, skipped=0, restore=False):
        g, u = self.g, self.g.u
        n = len(self.files)
        tw, th = self.tile_size
        self.cchips.set(self.ccat)
        if n == 0:
            self.cv.itemconfigure(self.file_text, text=tr("cv_no_file"), fill=hx(DIM))
            self.cv.itemconfigure(self.ctitle, text=tr("cv_no_files_title"), fill=hx(MUTED))
            self.cv.itemconfigure(self.cline2, text=tr("cv_pick_hint"))
            self.cv.itemconfigure(self.cline3, text="")
            self.ctile_fade.to(g.glyph_tile(tw, th, u(14), "video"), 0.3) if not restore else self.ctile_fade.show(g.glyph_tile(tw, th, u(14), "video"))
            self.cstate = "idle"
            self.btn_conv.configure(enabled=False, text=tr("convert"))
            for d in self.cdd:
                d.set_values(["-"])
                d.set_enabled(False)
            if not restore:
                self.set_status_c(tr("cv_pick_status"), MUTED)
            return
        total = sum(os.path.getsize(p) for p in self.files if os.path.isfile(p))
        first = os.path.basename(self.files[0])
        self.cv.itemconfigure(self.file_text, text=ellipsize(g.font(13), first if n == 1 else f"{first}  (+{n - 1})", self.L["fw"] - u(70)), fill="white")
        self.cv.itemconfigure(self.ctitle, text=tr("cv_n_files", n=n) if n > 1 else ellipsize(g.font(15, True), first, self.meta_w if hasattr(self, "meta_w") else u(300)), fill="white")
        self.cv.itemconfigure(self.cline2, text=f"{CV.cat_label(self.ccat)}  ·  {tr('cv_total', size=fmt_size(total))}")
        self.cv.itemconfigure(self.cline3, text=", ".join(os.path.basename(p) for p in self.files[:3]) + (" …" if n > 3 else ""))
        pil = g.glyph_tile(tw, th, u(14), self.ccat)
        (self.ctile_fade.show if restore else (lambda p: self.ctile_fade.to(p, 0.3)))(pil)
        vals = CV.target_values(self.ccat)
        src_ext = os.path.splitext(self.files[0])[1].lstrip(".").upper()
        src_ext = {"JPEG": "JPG", "TIF": "TIFF"}.get(src_ext, src_ext)
        cur = self.cdd[0].get()
        pick = cur if (restore and cur in vals) else next((v for v in vals if CV.target_key(v) != src_ext), vals[0])
        self.cdd[0].set_values(vals, pick)
        self.cdd[0].set_enabled(True)
        self._on_target_changed(pick)
        self.cstate = "ready"
        self.btn_conv.configure(enabled=True)
        if not restore:
            msg = tr("cv_ready") + ("  " + tr("cv_skipped", n=skipped) if skipped else "")
            self.set_status_c(msg, OK)
        elif not self.status_c_text:                        # setelah ganti bahasa
            self.set_status_c(tr("cv_ready"), OK)

    def _on_target_changed(self, val):
        ql, sl, q_on, cap_q, cap_s = CV.option_sets(self.ccat, val)
        self.cv.itemconfigure(self.ccaps[0], text=tr("cap_format"))
        self.cv.itemconfigure(self.ccaps[1], text=cap_q)
        self.cv.itemconfigure(self.ccaps[2], text=cap_s)
        qv, sv = [a for a, _ in ql], [a for a, _ in sl]
        if q_on:
            self.cdd[1].set_values(qv, qv[min(1, len(qv) - 1)] if self.ccat != "audio" and CV.target_key(val) not in CV.AUDIO_TARGETS else qv[0])
        else:
            self.cdd[1].set_values(["Lossless"])
        self.cdd[1].set_enabled(q_on)
        self.cdd[2].set_values(sv, sv[0])
        self.cdd[2].set_enabled(True)
        extract = self.ccat == "video" and CV.target_key(val) in CV.AUDIO_TARGETS
        self.btn_conv.configure(text=tr("extract_audio") if extract else tr("convert"))

    def _convert_action(self):
        if self.cstate == "converting":
            if self.converter:
                self.converter.cancel()
            self.btn_conv.configure(text=tr("cancelling"), enabled=False)
            self.set_status_c(tr("cv_cancelling"), MUTED)
        elif self.cstate == "ready":
            self.start_convert()

    def start_convert(self):
        if not FFMPEG and self.ccat != "image":
            return self.set_status_c(tr("cv_no_ffmpeg"), ERR)
        target = self.cdd[0].get()
        ql, sl, _, _, _ = CV.option_sets(self.ccat, target)
        qlabels, slabels = [a for a, _ in ql], [a for a, _ in sl]
        qi = qlabels.index(self.cdd[1].get()) if self.cdd[1].get() in qlabels else 0
        si = slabels.index(self.cdd[2].get()) if self.cdd[2].get() in slabels else 0
        self.cstate = "converting"
        self.converter = CV.Converter(FFMPEG)
        self._c_overall = 0.0
        self.btn_conv.configure(text=tr("cancel"), style="danger", enabled=True)
        for b in (self.btn_pick_h, self.btn_clear):
            b.configure(enabled=False)
        self.prog_c.reset()
        self.set_status_c(tr("st_start"), MUTED)
        out_dir, files, cat = self._convert_dir(), list(self.files), self.ccat

        def on_prog(frac, text):
            self._c_overall = max(self._c_overall, frac)
            self.post(self._show_progress_c, self._c_overall, text)

        def worker():
            try:
                res, bad = self.converter.run(files, cat, target, qi, si, out_dir, on_prog)
                self.post(self._convert_done, res, bad, out_dir, cat)
            except CV.ConvertCancelled:
                self.post(self._convert_cancelled)
            except Exception as e:
                self.post(self._convert_fail, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _show_progress_c(self, frac, text):
        if self.cstate == "converting":
            self.prog_c.set(frac)
            self.set_status_c(tr("cv_converting", text=text), MUTED)

    def _finish_ui_c(self):
        self.cstate = "ready" if self.files else "idle"
        self.btn_conv.configure(style="primary", enabled=bool(self.files))
        if self.files:
            self._on_target_changed(self.cdd[0].get())
        for b in (self.btn_pick_h, self.btn_clear):
            b.configure(enabled=True)

    def _convert_done(self, res, bad, out_dir, cat):
        self._finish_ui_c()
        self.last_cdir = out_dir
        if res:
            self.prog_c.set(1.0)
            msg = tr("cv_done", n=len(res)) + (f"  ·  {tr('cv_some_failed', n=len(bad), name=bad[0][0])}" if bad else "")
            self.set_status_c(msg, OK if not bad else ERR)
            self.add_activity("conv", os.path.basename(res[0]) + (f" (+{len(res) - 1})" if len(res) > 1 else ""), res[0])
        else:
            self.prog_c.reset()
            self.set_status_c(tr("err_prefix", msg=(bad[0][1][:140] if bad else tr("cv_none"))), ERR)

    def _convert_cancelled(self):
        self._finish_ui_c()
        self.prog_c.reset()
        self.set_status_c(tr("cv_cancelled"), MUTED)

    def _convert_fail(self, err):
        self._finish_ui_c()
        self.prog_c.reset()
        self.set_status_c(tr("err_prefix", msg=err[:140]), ERR)

    # ================================================================ dialog opsi
    def open_settings(self):
        if self.dialog is not None:
            try:
                self.dialog.win.lift()
                return
            except Exception:
                self.dialog = None
        self.dialog = SettingsDialog(self)

    def settings_changed(self):
        save_settings(self.settings)
        self._update_seg_labels()
        self._refresh_quality()

    def run(self):
        self.root.mainloop()


class SettingsDialog:
    def __init__(self, app):
        self.app = app
        g, u = app.g, app.g.u
        self.win = tk.Toplevel(app.root)
        win = self.win
        win.withdraw()
        win.title(tr("opt_title"))
        win.resizable(False, False)
        win.transient(app.root)
        W, H = u(440), u(500)
        self.cv = cv = tk.Canvas(win, width=W, height=H, bg=hx((84, 70, 130)), highlightthickness=0, bd=0)
        cv.pack()
        scene = g.make_bg(W, H)
        g.panel(scene, u(14), u(14), W - u(28), H - u(28), u(30), 0)
        self.scene_img = ImageTk.PhotoImage(scene)
        cv.create_image(0, 0, anchor="nw", image=self.scene_img)

        cv.create_text(u(40), u(54), anchor="w", text=tr("opt_title").upper(), font=g.font(24, True), fill="white")
        cv.create_text(u(40), u(86), anchor="w", text=tr("opt_sub"), font=g.font(12), fill=hx(MUTED))
        s = app.settings
        lang_vals = [tr("lang_auto"), LANG_NAMES["id"], LANG_NAMES["en"]]
        cur_lang = {"auto": lang_vals[0], "id": lang_vals[1], "en": lang_vals[2]}[s["lang"]]
        rows = [("language", lang_vals, cur_lang, "lang"), ("f_video", VIDEO_FORMATS, s["video_fmt"], "video_fmt"),
                ("f_audio", AUDIO_FORMATS, s["audio_fmt"], "audio_fmt"), ("f_thumb", THUMB_FORMATS, s["thumb_fmt"], "thumb_fmt")]
        self.dds = {}
        for i, (label, values, cur, key) in enumerate(rows):
            cy = u(142 + i * 58)
            cv.create_text(u(40), cy, anchor="w", text=tr(label), font=g.font(14), fill="white")
            self.dds[key] = Dropdown(app, cv, u(216), cy - u(20), u(184), u(40), values, cur, lambda v, k=key: self._set(k, v), size=13)
        cv.create_text(u(40), u(372), anchor="nw", width=u(360), text=tr("no_login_note"), font=g.font(11), fill=hx(MUTED))
        cv.create_text(u(40), u(452), anchor="w", text=f"Vidrop v{APP_VERSION}", font=g.font(10), fill=hx(DIM))
        self.btn_done = Button(g, cv, u(280), u(432), u(120), u(40), tr("done"), "primary", self.close, size=13)

        win.protocol("WM_DELETE_WINDOW", self.close)
        win.bind("<Escape>", lambda e: self.close())
        win.bind("<Button-1>", app._outside_click, add="+")
        rx = app.root.winfo_rootx() + (app.W - W) // 2
        ry = app.root.winfo_rooty() + u(60)
        win.geometry(f"{W}x{H}+{max(0, rx)}+{max(0, ry)}")
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            pass
        win.deiconify()
        dark_titlebar(win)
        win.after(120, lambda: set_win_icon(win, resource("assets", "vidrop.ico")))
        Anim(win, 0.25, lambda t: self._alpha(t), ease_out)

    def _alpha(self, t):
        try:
            self.win.attributes("-alpha", t)
        except Exception:
            pass

    def _set(self, key, value):
        app = self.app
        if key == "lang":
            code = {tr("lang_auto"): "auto", LANG_NAMES["id"]: "id", LANG_NAMES["en"]: "en"}.get(value, "auto")
            return app.set_language(code)
        app.settings[key] = value
        app.settings_changed()

    def close(self):
        self.app.close_popup()
        try:
            self.win.destroy()
        except Exception:
            pass
        self.app.dialog = None


def main():
    Vidrop().run()


if __name__ == "__main__":
    main()
