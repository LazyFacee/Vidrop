# -*- coding: utf-8 -*-
"""Vidrop - toolkit grafis 'liquid glass' (tema senja) + animasi halus berbasis waktu."""
import math
import random
import time
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageTk

from core import *   # noqa: F401,F403  (warna, IS_WIN/IS_MAC, hx, ellipsize, tr)

RS = Image.Resampling


# ======================================================================
#  Easing + animasi berbasis waktu (durasi tetap, tidak bergantung kecepatan CPU)
# ======================================================================
def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_out5(t):
    return 1 - (1 - t) ** 5


def ease_in(t):
    return t * t * t


def ease_in_out(t):
    return t * t * t * (t * (6 * t - 15) + 10)          # smootherstep


def ease_out_back(t, s=1.0):
    c3 = s + 1
    return 1 + c3 * (t - 1) ** 3 + s * (t - 1) ** 2


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Anim:
    """Animasi sederhana: memanggil fn(0..1) selama `dur` detik."""

    def __init__(self, w, dur, fn, ease=ease_out, done=None):
        self.w, self.dur, self.fn, self.ease, self.done = w, max(dur, 0.001), fn, ease, done
        self.t0 = time.perf_counter()
        self.job = None
        self.alive = True
        self._tick()

    def _tick(self):
        if not self.alive:
            return
        t = (time.perf_counter() - self.t0) / self.dur
        try:
            if t >= 1:
                self.alive = False
                self.fn(1.0)
                if self.done:
                    self.done()
                return
            self.fn(self.ease(t))
            self.job = self.w.after(6, self._tick)
        except tk.TclError:
            self.alive = False

    def cancel(self):
        self.alive = False
        if self.job is not None:
            try:
                self.w.after_cancel(self.job)
            except Exception:
                pass
            self.job = None


# ======================================================================
#  Util gambar
# ======================================================================
def vg(w, h, a, b):
    """Gradien vertikal 'L': nilai a di atas, b di bawah."""
    g = Image.linear_gradient("L").resize((max(w, 1), max(h, 1)), RS.BILINEAR)
    return g.point(lambda v: int(a + (b - a) * v / 255))


def hg(w, h):
    """Gradien horizontal 'L' 0..255 (kiri ke kanan)."""
    return Image.linear_gradient("L").transpose(Image.Transpose.TRANSPOSE).resize((max(w, 1), max(h, 1)), RS.BILINEAR)


def top_fade(w, h, frac, amax):
    out = Image.new("L", (w, h), 0)
    out.paste(vg(w, max(1, int(h * frac)), amax, 0), (0, 0))
    return out


def tint(color, mask, alpha=1.0):
    a = mask if alpha == 1.0 else mask.point(lambda v: int(v * alpha))
    im = Image.new("RGBA", mask.size, tuple(color[:3]) + (255,))
    im.putalpha(a)
    return im


def mul(a, b):
    return ImageChops.multiply(a, b)


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Gfx:
    def __init__(self, root, scale):
        self.root, self.S = root, scale
        self._fonts, self._cache = {}, {}
        self.field_color = (66, 54, 104)
        fams = set(tkfont.families(root))
        self.family = None
        for n in ("Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI", "SF Pro Display", "SF Pro Text",
                  "Helvetica Neue", "Inter", "Noto Sans", "DejaVu Sans", "Arial"):
            if n in fams:
                self.family = n
                break
        if not self.family:
            self.family = tkfont.nametofont("TkDefaultFont").actual("family")

    def u(self, v):
        return int(round(v * self.S))

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(root=self.root, family=self.family, size=-self.u(size),
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    # ---------------------------------------------------------- bentuk dasar
    def rr_mask(self, w, h, r, ss=4):
        r = max(1, min(r, h // 2, w // 2))
        m = Image.new("L", (w * ss, h * ss), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=r * ss, fill=255)
        return m.resize((w, h), RS.LANCZOS)

    def ring_mask(self, w, h, r, bw=None, ss=4):
        bw = bw or max(1, self.u(1))
        r = max(1, min(r, h // 2, w // 2))
        outer = self.rr_mask(w, h, r, ss)
        big = Image.new("L", (w * ss, h * ss), 0)
        ImageDraw.Draw(big).rounded_rectangle((bw * ss, bw * ss, (w - bw) * ss - 1, (h - bw) * ss - 1),
                                              radius=max(r - bw, 1) * ss, fill=255)
        return ImageChops.subtract(outer, big.resize((w, h), RS.LANCZOS))

    # ---------------------------------------------------------- latar: senja kota yang buram
    def make_bg(self, W, H, variant="main"):
        u = self.u
        w, h = max(2, W // 2), max(2, H // 2)
        im = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(im)
        stops = [(0.0, (86, 80, 176)), (0.30, (146, 108, 188)), (0.50, (226, 142, 172)),
                 (0.64, (255, 184, 142)), (0.78, (240, 160, 132)), (1.0, (84, 70, 116))]
        for y in range(h):
            t = y / (h - 1)
            col = stops[-1][1]
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t0 <= t <= t1:
                    col = mix(c0, c1, (t - t0) / (t1 - t0))
                    break
            d.line([(0, y), (w, y)], fill=col)
        R = lambda fx, fy: (int(w * fx), int(h * fy))
        # gedung (siluet kebiruan)
        for (x0, y0, x1, y1, col) in ((0.00, 0.00, 0.17, 0.80, (92, 114, 176)), (0.17, 0.18, 0.28, 0.80, (122, 126, 188)),
                                      (0.80, 0.04, 0.93, 0.80, (72, 106, 166)), (0.93, 0.20, 1.00, 0.80, (94, 124, 176)),
                                      (0.60, 0.34, 0.78, 0.80, (156, 134, 190)), (0.30, 0.46, 0.50, 0.80, (176, 140, 192))):
            d.rectangle(R(x0, y0) + R(x1, y1), fill=col)
        d.rectangle(R(0, 0.78) + R(1, 1), fill=(92, 76, 122))                       # jalan
        d.rectangle(R(0.30, 0.82) + R(0.66, 1), fill=(48, 42, 70))                  # blok gelap
        rnd = random.Random(21)
        for _ in range(60):                                                          # jendela hangat
            x = rnd.choice([rnd.uniform(0.01, 0.16), rnd.uniform(0.81, 0.92), rnd.uniform(0.61, 0.77)])
            y = rnd.uniform(0.06, 0.70)
            px, py = R(x, y)
            d.rectangle((px, py, px + max(2, u(3)), py + max(2, u(4))), fill=(255, 214, 150))
        for cx, cy, r, col in ((0.06, 0.88, 0.16, (80, 154, 100)), (0.17, 0.95, 0.14, (156, 200, 100)),
                               (0.02, 0.70, 0.12, (92, 162, 104)), (0.13, 0.80, 0.06, (238, 104, 156))):
            cxp, cyp = R(cx, cy)
            rr = int(w * r)
            d.ellipse((cxp - rr, cyp - rr, cxp + rr, cyp + rr), fill=col)             # dedaunan kiri
        im = im.convert("RGBA")
        bok = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bok)
        for _ in range(30):                                                          # bokeh lampu
            x, y = rnd.randint(0, w), rnd.randint(int(h * 0.50), int(h * 0.96))
            r = rnd.randint(max(3, u(6)), max(6, u(24)))
            col = rnd.choice([(255, 206, 110), (255, 150, 120), (255, 124, 164), (255, 236, 176), (255, 190, 90)])
            bd.ellipse((x - r, y - r, x + r, y + r), fill=col + (rnd.randint(70, 150),))
        im.alpha_composite(bok)
        im = im.filter(ImageFilter.GaussianBlur(max(2, u(10))))
        im = im.resize((W, H), RS.BICUBIC).convert("RGB")
        return ImageEnhance.Color(im).enhance(1.12)

    # ---------------------------------------------------------- panel & kartu (dibakar ke latar)
    def panel(self, scene, x, y, w, h, r, rail_w):
        u = self.u
        pad = u(44)
        sh = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
        sh.paste(self.rr_mask(w, h, r).point(lambda v: int(v * 0.42)), (pad, pad + u(18)))
        scene.paste((20, 10, 46), (x - pad, y - pad), sh.filter(ImageFilter.GaussianBlur(u(26))))

        region = scene.crop((x, y, x + w, y + h)).filter(ImageFilter.GaussianBlur(u(30)))
        region = ImageEnhance.Brightness(ImageEnhance.Color(region).enhance(1.5)).enhance(1.08)
        glass = Image.blend(region, Image.new("RGB", (w, h), (58, 42, 100)), 0.17)
        glass = Image.blend(glass, Image.new("RGB", (w, h), (255, 255, 255)), 0.10)
        glass.paste((255, 255, 255), (0, 0), top_fade(w, h, 0.42, 40))
        pm = self.rr_mask(w, h, r)
        scene.paste(glass, (x, y), pm)
        if rail_w:
            rect = Image.new("L", (w, h), 0)
            rect.paste(255, (0, 0, rail_w, h))
            scene.paste((20, 12, 44), (x, y), mul(pm, rect).point(lambda v: int(v * 0.26)))
            line = Image.new("L", (w, h), 0)
            line.paste(255, (rail_w, u(26), rail_w + max(1, u(1)), h - u(26)))
            scene.paste((255, 255, 255), (x, y), line.point(lambda v: int(v * 0.14)))
        rm = self.ring_mask(w, h, r, bw=max(1, u(1.5)))
        scene.paste((255, 255, 255), (x, y), mul(rm, vg(w, h, 235, 60)))

    def card(self, scene, x, y, w, h, r):
        m = self.rr_mask(w, h, r)
        scene.paste((255, 255, 255), (x, y), m.point(lambda v: int(v * 0.085)))
        scene.paste((255, 255, 255), (x, y), mul(top_fade(w, h, 0.45, 255), m).point(lambda v: int(v * 0.055)))
        scene.paste((255, 255, 255), (x, y), mul(self.ring_mask(w, h, r), vg(w, h, 110, 34)))

    def inset(self, scene, x, y, w, h, r):
        """Kolom isian: warna rata (Entry Tk tidak bisa transparan), diambil dari kaca di sekitarnya."""
        avg = scene.crop((x, y, x + w, y + h)).resize((1, 1), RS.BOX).getpixel((0, 0))
        fc = mix(avg, (30, 22, 58), 0.46)
        self.field_color = fc
        scene.paste(fc, (x, y), self.rr_mask(w, h, r))
        scene.paste((255, 255, 255), (x, y), mul(self.ring_mask(w, h, r), vg(w, h, 70, 26)))
        return fc

    def track_img(self, w, h):
        key = ("track", w, h)
        if key not in self._cache:
            r = h // 2
            m = self.rr_mask(w, h, r)
            out = tint((255, 255, 255), m, 0.11)
            out.alpha_composite(tint((255, 255, 255), mul(self.ring_mask(w, h, r), vg(w, h, 90, 30))))
            self._cache[key] = out
        return self._cache[key]

    # ---------------------------------------------------------- tombol
    def button_img(self, w, h, style, state):
        key = ("btn", w, h, style, state)
        if key in self._cache:
            return self._cache[key]
        u = self.u
        p = u(16)
        W, H = w + 2 * p, h + 2 * p
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        r = h // 2
        mask = self.rr_mask(w, h, r)
        if style == "primary" and state != "disabled":
            sh = Image.new("L", (W, H), 0)
            sh.paste(mask.point(lambda v: int(v * {"normal": 0.24, "hover": 0.28, "down": 0.12}[state])), (p, p + u(4)))
            out.alpha_composite(tint((24, 10, 56), sh.filter(ImageFilter.GaussianBlur(u(8)))))
            if state == "hover":
                gl = Image.new("L", (W, H), 0)
                gl.paste(mask.point(lambda v: int(v * 0.34)), (p, p))
                out.alpha_composite(tint((255, 255, 255), gl.filter(ImageFilter.GaussianBlur(u(9)))))
        if style == "primary":
            if state == "disabled":
                body = tint((255, 255, 255), mask, 0.20)
            else:
                top, bot = {"normal": ((255, 255, 255), (238, 234, 252)), "hover": ((255, 255, 255), (248, 245, 255)),
                            "down": ((228, 224, 246), (214, 208, 236))}[state]
                body = Image.composite(Image.new("RGBA", (w, h), bot + (250,)),
                                       Image.new("RGBA", (w, h), top + (250,)), vg(w, h, 0, 255))
                body.putalpha(mul(mask, Image.new("L", (w, h), 250)))
        elif style == "danger":
            body = tint((255, 112, 134), mask, {"normal": 0.34, "hover": 0.46, "down": 0.24, "disabled": 0.12}[state])
        else:
            body = tint((255, 255, 255), mask, {"normal": 0.14, "hover": 0.23, "down": 0.09, "disabled": 0.07}[state])
        out.alpha_composite(body, (p, p))
        if state != "disabled" and style != "primary":
            out.alpha_composite(tint((255, 255, 255), mul(top_fade(w, h, 0.55, 255), mask).point(lambda v: int(v * 0.12))), (p, p))
        if style != "primary":
            rm = self.ring_mask(w, h, r)
            ra = mul(rm, vg(w, h, 190, 70) if style == "glass" else vg(w, h, 230, 120))
            if state == "disabled":
                ra = ra.point(lambda v: int(v * 0.45))
            out.alpha_composite(tint((255, 255, 255) if style == "glass" else (255, 190, 200), ra), (p, p))
        self._cache[key] = out
        return out

    def field_img(self, w, h, state):
        key = ("fld", w, h, state)
        if key in self._cache:
            return self._cache[key]
        r = min(self.u(14), h // 2)
        mask = self.rr_mask(w, h, r)
        out = tint((255, 255, 255), mask, {"normal": 0.12, "hover": 0.20, "disabled": 0.06}[state])
        out.alpha_composite(tint((255, 255, 255), mul(top_fade(w, h, 0.5, 255), mask).point(lambda v: int(v * 0.07))))
        ra = mul(self.ring_mask(w, h, r), vg(w, h, 140, 46))
        if state == "disabled":
            ra = ra.point(lambda v: int(v * 0.5))
        out.alpha_composite(tint((255, 255, 255), ra))
        self._cache[key] = out
        return out

    def chevron(self, size, angle, enabled=True):
        ss = 4
        S = size * ss
        big = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        c, k = S // 2, int(S * 0.27)
        col = (255, 255, 255, 235 if enabled else 95)
        wd = max(2, int(S * 0.095))
        pts = [(c - k, c - k // 2), (c, c + k // 2), (c + k, c - k // 2)]
        d.line(pts, fill=col, width=wd, joint="curve")
        for (px, py) in (pts[0], pts[2]):
            d.ellipse((px - wd // 2, py - wd // 2, px + wd // 2, py + wd // 2), fill=col)
        return big.rotate(angle, resample=RS.BICUBIC).resize((size, size), RS.LANCZOS)

    def chip_img(self, w, h, on):
        key = ("chip", w, h, on)
        if key in self._cache:
            return self._cache[key]
        p = self.u(10)
        W, H = w + 2 * p, h + 2 * p
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        mask = self.rr_mask(w, h, h // 2)
        if on:
            gm = Image.new("L", (W, H), 0)
            gm.paste(mask.point(lambda v: int(v * 0.38)), (p, p + self.u(1)))
            out.alpha_composite(tint((255, 255, 255), gm.filter(ImageFilter.GaussianBlur(self.u(6)))))
            body = Image.composite(Image.new("RGBA", (w, h), (238, 234, 252, 250)),
                                   Image.new("RGBA", (w, h), (255, 255, 255, 250)), vg(w, h, 0, 255))
            body.putalpha(mul(mask, Image.new("L", (w, h), 250)))
            out.alpha_composite(body, (p, p))
        else:
            out.alpha_composite(tint((255, 255, 255), mask, 0.09), (p, p))
            out.alpha_composite(tint((255, 255, 255), mul(self.ring_mask(w, h, h // 2), vg(w, h, 100, 34))), (p, p))
        self._cache[key] = out
        return out

    # ---------------------------------------------------------- popup dropdown
    def popup_bg(self, w, h):
        r = self.u(16)
        mask = self.rr_mask(w, h, r)
        body = Image.composite(Image.new("RGBA", (w, h), (36, 28, 66, 255)),
                               Image.new("RGBA", (w, h), (64, 50, 104, 255)), vg(w, h, 0, 255))
        body.alpha_composite(tint((255, 255, 255), mul(top_fade(w, h, 0.45, 255), mask).point(lambda v: int(v * 0.08))))
        body.alpha_composite(tint((255, 255, 255), mul(self.ring_mask(w, h, r), vg(w, h, 200, 64))))
        out = Image.new("RGBA", (w, h), (1, 1, 1, 255) if IS_WIN else (36, 28, 66, 255))
        out.paste(body, (0, 0), mask)
        return out.convert("RGB")

    def popup_hover(self, w, h):
        r = self.u(10)
        m = self.rr_mask(w, h, r)
        out = tint((255, 255, 255), m, 0.17)
        out.alpha_composite(tint((255, 255, 255), mul(self.ring_mask(w, h, r), vg(w, h, 120, 50))))
        return out

    def row_hover(self, w, h):
        key = ("rowh", w, h)
        if key not in self._cache:
            m = self.rr_mask(w, h, self.u(14))
            out = tint((255, 255, 255), m, 0.10)
            out.alpha_composite(tint((255, 255, 255), mul(self.ring_mask(w, h, self.u(14)), vg(w, h, 70, 30))))
            self._cache[key] = out
        return self._cache[key]

    # ---------------------------------------------------------- ikon garis & glyph
    def icon(self, name, size, color=(255, 255, 255), alpha=255):
        key = ("icon", name, size, tuple(color), alpha)
        if key in self._cache:
            return self._cache[key]
        ss = 4
        S = size * ss
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        lw = max(2, int(S * 0.085))
        col = tuple(color[:3]) + (alpha,)

        def L(pts, closed=False):
            pp = [(x * S, y * S) for x, y in pts]
            if closed:
                pp = pp + [pp[0]]
            d.line(pp, fill=col, width=lw, joint="curve")
            for (x, y) in ([pp[0], pp[-1]] if not closed else []):
                d.ellipse((x - lw / 2, y - lw / 2, x + lw / 2, y + lw / 2), fill=col)

        if name == "download":
            L([(0.5, 0.16), (0.5, 0.62)]); L([(0.30, 0.44), (0.5, 0.64), (0.70, 0.44)]); L([(0.20, 0.84), (0.80, 0.84)])
        elif name == "convert":
            L([(0.16, 0.34), (0.82, 0.34)]); L([(0.66, 0.18), (0.82, 0.34), (0.66, 0.50)])
            L([(0.84, 0.68), (0.18, 0.68)]); L([(0.34, 0.52), (0.18, 0.68), (0.34, 0.84)])
        elif name == "folder":
            L([(0.14, 0.28), (0.40, 0.28), (0.49, 0.38), (0.86, 0.38), (0.86, 0.78), (0.14, 0.78)], closed=True)
        elif name == "gear":
            c = S / 2
            r1 = S * 0.17
            d.ellipse((c - r1, c - r1, c + r1, c + r1), outline=col, width=lw)
            for i in range(8):
                a = i * math.pi / 4
                x0, y0, x1, y1 = c + math.cos(a) * S * 0.27, c + math.sin(a) * S * 0.27, c + math.cos(a) * S * 0.39, c + math.sin(a) * S * 0.39
                d.line([(x0, y0), (x1, y1)], fill=col, width=lw)
                for (x, y) in ((x0, y0), (x1, y1)):
                    d.ellipse((x - lw / 2, y - lw / 2, x + lw / 2, y + lw / 2), fill=col)
            r2 = S * 0.285
            d.ellipse((c - r2, c - r2, c + r2, c + r2), outline=col, width=max(2, lw // 2))
        elif name == "send":
            L([(0.18, 0.5), (0.82, 0.5)]); L([(0.58, 0.26), (0.82, 0.5), (0.58, 0.74)])
        elif name == "dots":
            for x in (0.24, 0.5, 0.76):
                r = S * 0.065
                d.ellipse((x * S - r, S * 0.5 - r, x * S + r, S * 0.5 + r), fill=col)
        elif name == "close":
            L([(0.28, 0.28), (0.72, 0.72)]); L([(0.72, 0.28), (0.28, 0.72)])
        elif name == "check":
            L([(0.22, 0.52), (0.43, 0.72), (0.80, 0.30)])
        elif name == "clipboard":
            d.rounded_rectangle((S * 0.24, S * 0.22, S * 0.76, S * 0.84), radius=int(S * 0.08), outline=col, width=lw)
            L([(0.38, 0.14), (0.62, 0.14)])
            L([(0.36, 0.50), (0.64, 0.50)]); L([(0.36, 0.66), (0.58, 0.66)])
        elif name == "link":
            lay = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            ld = ImageDraw.Draw(lay)
            ld.rounded_rectangle((S * 0.06, S * 0.40, S * 0.56, S * 0.62), radius=int(S * 0.11), outline=col, width=lw)
            ld.rounded_rectangle((S * 0.44, S * 0.38, S * 0.94, S * 0.60), radius=int(S * 0.11), outline=col, width=lw)
            im.alpha_composite(lay.rotate(35, resample=RS.BICUBIC))
        elif name == "video":
            d.rounded_rectangle((S * 0.16, S * 0.26, S * 0.84, S * 0.74), radius=int(S * 0.10), outline=col, width=lw)
            d.polygon([(S * 0.43, S * 0.38), (S * 0.43, S * 0.62), (S * 0.63, S * 0.5)], fill=col)
        elif name == "music":
            d.ellipse((S * 0.18, S * 0.58, S * 0.46, S * 0.84), fill=col)
            d.line([(S * 0.44, S * 0.70), (S * 0.44, S * 0.22)], fill=col, width=lw)
            d.line([(S * 0.44, S * 0.22), (S * 0.78, S * 0.32)], fill=col, width=lw)
            d.ellipse((S * 0.60, S * 0.54, S * 0.86, S * 0.78), fill=col)
            d.line([(S * 0.84, S * 0.66), (S * 0.84, S * 0.32)], fill=col, width=lw)
        elif name == "image":
            d.rounded_rectangle((S * 0.16, S * 0.22, S * 0.84, S * 0.78), radius=int(S * 0.09), outline=col, width=lw)
            d.polygon([(S * 0.22, S * 0.70), (S * 0.42, S * 0.46), (S * 0.56, S * 0.62), (S * 0.66, S * 0.52), (S * 0.80, S * 0.70)], fill=col)
            d.ellipse((S * 0.60, S * 0.30, S * 0.72, S * 0.42), fill=col)
        im = im.resize((size, size), RS.LANCZOS)
        self._cache[key] = im
        return im

    def avatar(self, size, kind):
        """Lingkaran gradien dengan ikon putih; untuk daftar aktivitas."""
        key = ("avatar", size, kind)
        if key not in self._cache:
            ss = 4
            S = size * ss
            m = Image.new("L", (S, S), 0)
            ImageDraw.Draw(m).ellipse((0, 0, S - 1, S - 1), fill=255)
            pal = {"dl_audio": ((255, 160, 120), (255, 120, 170)), "conv": ((104, 170, 255), (170, 140, 255))}.get(
                kind, ((150, 130, 255), (255, 150, 196)))
            grad = Image.composite(Image.new("RGBA", (S, S), pal[0] + (255,)), Image.new("RGBA", (S, S), pal[1] + (255,)),
                                   vg(S, S, 0, 255))
            grad.putalpha(m)
            ic = self.icon({"dl_video": "video", "dl_audio": "music", "dl_thumb": "image", "conv": "convert"}.get(kind, "video"),
                           int(size * 0.56))
            out = grad.resize((size, size), RS.LANCZOS)
            out.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2))
            self._cache[key] = out
        return self._cache[key]

    def ring_avatar(self, size):
        """Cincin gradien (pink-oranye-biru) dengan isi gelap; tombol bahasa di sidebar."""
        key = ("ringav", size)
        if key not in self._cache:
            ss = 4
            S = size * ss
            outer = Image.new("L", (S, S), 0)
            ImageDraw.Draw(outer).ellipse((0, 0, S - 1, S - 1), fill=255)
            inner = Image.new("L", (S, S), 0)
            b = int(S * 0.085)
            ImageDraw.Draw(inner).ellipse((b, b, S - 1 - b, S - 1 - b), fill=255)
            ring = ImageChops.subtract(outer, inner)
            grad = Image.new("RGBA", (S, S))
            gd = ImageDraw.Draw(grad)
            stops = [(0.0, (255, 150, 196)), (0.5, (255, 190, 124)), (1.0, (108, 178, 255))]
            for x in range(S):
                t = x / (S - 1)
                col = stops[-1][1]
                for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                    if t0 <= t <= t1:
                        col = mix(c0, c1, (t - t0) / (t1 - t0))
                        break
                gd.line([(x, 0), (x, S)], fill=col + (255,))
            grad.putalpha(ring)
            base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            base.alpha_composite(tint((40, 28, 76), inner, 0.82))
            base.alpha_composite(grad)
            self._cache[key] = base.resize((size, size), RS.LANCZOS)
        return self._cache[key]

    def glyph_tile(self, w, h, r, kind):
        """Ubin dengan glyph besar (video/audio/gambar) untuk pratinjau."""
        base = Image.composite(Image.new("RGB", (w, h), (96, 78, 168)), Image.new("RGB", (w, h), (150, 118, 206)),
                               vg(w, h, 0, 255)).convert("RGBA")
        name = {"audio": "music", "image": "image"}.get(kind, "video")
        ic = self.icon(name, int(min(w, h) * 0.52), (255, 255, 255), 235)
        base.alpha_composite(ic, ((w - ic.width) // 2, (h - ic.height) // 2))
        base.putalpha(self.rr_mask(w, h, r))
        base.alpha_composite(tint((255, 255, 255), mul(self.ring_mask(w, h, r), vg(w, h, 110, 40))))
        return base

    def round_thumb(self, img, w, h, r):
        if img is None:
            return self.glyph_tile(w, h, r, "video")
        out = ImageOps.fit(img.convert("RGB"), (w, h), RS.LANCZOS).convert("RGBA")
        out.putalpha(self.rr_mask(w, h, r))
        out.alpha_composite(tint((255, 255, 255), mul(self.ring_mask(w, h, r), vg(w, h, 110, 40))))
        return out

    # ---------------------------------------------------------- progress & grafik
    def _bar_gradient(self, w, h):
        stops = [(0.0, PINK), (0.55, VIOLET), (1.0, BLUE)]
        strip = Image.new("RGBA", (w, h))
        d = ImageDraw.Draw(strip)
        for x in range(w):
            t = x / max(1, w - 1)
            col = stops[-1][1]
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t0 <= t <= t1:
                    col = mix(c0, c1, (t - t0) / (t1 - t0))
                    break
            d.line([(x, 0), (x, h)], fill=col + (255,))
        return strip

    def bar_img(self, w, h, frac, shimmer=None):
        ss = 3
        if frac is None:
            big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
            ImageDraw.Draw(big).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=h * ss // 2, fill=(255, 255, 255, 40))
            return big.resize((w, h), RS.LANCZOS)
        fw = max(h, int(w * frac))
        grad = self._bar_gradient(w * ss, h * ss).crop((0, 0, fw * ss, h * ss))
        m = Image.new("L", (fw * ss, h * ss), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, fw * ss - 1, h * ss - 1), radius=h * ss // 2, fill=255)
        grad.putalpha(m)
        if shimmer is not None:
            bw = max(h * 5, int(fw * 0.25)) * ss
            tri = hg(bw, h * ss).point(lambda v: int(min(v, 255 - v) * 2))
            band = Image.new("L", (fw * ss, h * ss), 0)
            band.paste(tri, (int((fw * ss + bw) * shimmer - bw), 0))
            grad.alpha_composite(tint((255, 255, 255), mul(band, m).point(lambda v: int(v * 0.55))))
        return grad.resize((fw, h), RS.LANCZOS)

    def chart_img(self, w, h, samples):
        """Grafik kecepatan: garis putih mulus + area gradien (gaya 'Performance' pada referensi)."""
        ss = 3
        W, H = w * ss, h * ss
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for i in range(4):
            y = int((i + 0.5) * H / 4)
            d.line([(0, y), (W, y)], fill=(255, 255, 255, 30), width=ss)
        lw = max(2, int(self.S * 2.6 * ss))
        if len(samples) < 2:                                      # kosong: gelombang putus-putus
            pts = [(x, H * 0.60 - math.sin(x / W * math.pi * 2.4) * H * 0.12) for x in range(0, W, 5)]
            for i in range(0, len(pts) - 1, 3):
                d.line([pts[i], pts[i + 1]], fill=(255, 255, 255, 80), width=max(2, lw // 2))
            return im.resize((w, h), RS.LANCZOS)
        vmax = max(max(samples) * 1.2, 1e-6)
        n = len(samples)
        pts = [(i * (W - 1) / (n - 1), H - 6 * ss - (v / vmax) * (H - 14 * ss)) for i, v in enumerate(samples)]
        for _ in range(3):                                         # Chaikin: kurva mulus
            new = [pts[0]]
            for a, b in zip(pts, pts[1:]):
                new += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
            new.append(pts[-1])
            pts = new
        area = Image.new("L", (W, H), 0)
        ImageDraw.Draw(area).polygon(pts + [(W, H), (0, H)], fill=255)
        im.alpha_composite(tint((255, 255, 255), mul(area, vg(W, H, 105, 0))))
        d = ImageDraw.Draw(im)
        d.line(pts, fill=(255, 255, 255, 245), width=lw, joint="curve")
        ex, ey = pts[-1]
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        r = lw * 2.4
        ImageDraw.Draw(halo).ellipse((ex - r, ey - r, ex + r, ey + r), fill=(255, 255, 255, 120))
        im.alpha_composite(halo.filter(ImageFilter.GaussianBlur(lw)))
        ImageDraw.Draw(im).ellipse((ex - lw * 1.2, ey - lw * 1.2, ex + lw * 1.2, ey + lw * 1.2), fill=(255, 255, 255, 255))
        return im.resize((w, h), RS.LANCZOS)


# ======================================================================
#  Widget kanvas
# ======================================================================
class Crossfade:
    """Cross-fade halus (berbasis waktu) antar gambar RGBA pada satu item kanvas."""

    def __init__(self, cv, item):
        self.cv, self.item = cv, item
        self.cur, self.anim, self.photo = None, None, None

    def _set(self, pil):
        self.photo = ImageTk.PhotoImage(pil)
        self.cv.itemconfigure(self.item, image=self.photo)

    def _cancel(self):
        if self.anim:
            self.anim.cancel()
            self.anim = None

    def show(self, pil):
        self._cancel()
        self.cur = pil
        self._set(pil)

    def to(self, pil, dur=0.16):
        if self.cur is None or self.cur.size != pil.size or dur <= 0:
            return self.show(pil)
        self._cancel()
        try:
            a, b = self.cur.convert("RGBa"), pil.convert("RGBa")
            premul = True
        except Exception:
            a, b, premul = self.cur, pil, False

        def fn(t):
            if t >= 1:
                frame = pil
            else:
                frame = Image.blend(a, b, t)
                if premul:
                    frame = frame.convert("RGBA")
            self.cur = frame
            self._set(frame)

        self.anim = Anim(self.cv, dur, fn, ease_in_out)


class Button:
    COLORS = {"primary": (INK, (178, 172, 204)), "glass": (TXT, (196, 190, 220)), "danger": (TXT, (214, 170, 180))}

    def __init__(self, g, cv, x, y, w, h, text, style="glass", command=None, size=14, bold=True, icon=None):
        self.g, self.cv, self.w, self.h = g, cv, w, h
        self.style, self.cmd, self.icon_name = style, command, icon
        self.enabled, self.state, self.visible = True, "normal", True
        self.p = g.u(16)
        self.item = cv.create_image(x - self.p, y - self.p, anchor="nw")
        self.fade = Crossfade(cv, self.item)
        self.fade.show(self._pil())
        self.label = cv.create_text(x + w // 2, y + h // 2, text="" if icon else text, font=g.font(size, bold),
                                    fill=hx(self.COLORS[style][0]), state="disabled")
        self.icon_item, self.icon_photo = None, None
        if icon:
            self.icon_size = int(min(w, h) * 0.46)
            self.icon_item = cv.create_image(x + w // 2, y + h // 2, anchor="center", state="disabled")
            self._icon()
        self._tcol, self._tanim = self.COLORS[style][0], None
        cv.tag_bind(self.item, "<Enter>", lambda e: self._hover(True))
        cv.tag_bind(self.item, "<Leave>", lambda e: self._hover(False))
        cv.tag_bind(self.item, "<ButtonPress-1>", self._press)
        cv.tag_bind(self.item, "<ButtonRelease-1>", self._release)

    def _icon(self):
        if self.icon_item is None:
            return
        col = self.COLORS[self.style][0 if self.enabled else 1]
        self.icon_photo = ImageTk.PhotoImage(self.g.icon(self.icon_name, self.icon_size, col))
        self.cv.itemconfigure(self.icon_item, image=self.icon_photo)

    def _pil(self):
        st = "disabled" if not self.enabled else self.state
        return self.g.button_img(self.w, self.h, self.style, st)

    def _text_to(self, col, dur):
        if self._tanim:
            self._tanim.cancel()
        c0 = self._tcol
        if dur <= 0 or c0 == col:
            self._tcol = col
            self.cv.itemconfigure(self.label, fill=hx(col))
            return

        def fn(t):
            self._tcol = lerp_color(c0, col, t) if t < 1 else col
            self.cv.itemconfigure(self.label, fill=hx(self._tcol))

        self._tanim = Anim(self.cv, dur, fn, ease_out)

    def _refresh(self, dur=0.16):
        self.fade.to(self._pil(), dur)
        self._text_to(self.COLORS[self.style][0 if self.enabled else 1], dur)
        self._icon()

    def _hover(self, on):
        if not self.enabled:
            return
        self.state = "hover" if on else "normal"
        self.cv.configure(cursor="hand2" if on else "")
        self._refresh(0.18)

    def _press(self, e):
        if self.enabled:
            self.state = "down"
            self._refresh(0.07)

    def _release(self, e):
        if not self.enabled:
            return
        was_down = self.state == "down"
        self.state = "hover"
        self._refresh(0.18)
        if was_down and self.cmd:
            self.cmd()

    def configure(self, text=None, style=None, enabled=None, visible=None):
        dur = 0.18
        if text is not None and not self.icon_name:
            self.cv.itemconfigure(self.label, text=text)
        if style is not None and style != self.style:
            self.style, dur = style, 0.26
        if enabled is not None and enabled != self.enabled:
            self.enabled, dur = enabled, 0.24
            if not enabled:
                self.state = "normal"
                self.cv.configure(cursor="")
        if visible is not None:
            appearing = visible and not self.visible
            self.visible = visible
            self.cv.itemconfigure(self.item, state="normal" if visible else "hidden")
            self.cv.itemconfigure(self.label, state="disabled" if visible else "hidden")
            if self.icon_item:
                self.cv.itemconfigure(self.icon_item, state="disabled" if visible else "hidden")
            if appearing:
                self.fade.show(Image.new("RGBA", self.fade.cur.size, (0, 0, 0, 0)))
                self._tcol = (120, 100, 170)
                self.cv.itemconfigure(self.label, fill=hx(self._tcol))
                dur = 0.30
        self._refresh(dur)


class Dropdown:
    def __init__(self, app, cv, x, y, w, h, values, value, command, size=13):
        self.app, self.g, self.cv = app, app.g, cv
        self.x, self.y, self.w, self.h = x, y, w, h
        self.values, self.value, self.cmd = list(values), value, command
        self.enabled, self.hover, self.is_open = True, False, False
        self.size = size
        g = self.g
        self.item = cv.create_image(x, y, anchor="nw")
        self.fade = Crossfade(cv, self.item)
        self.fade.show(g.field_img(w, h, "normal"))
        self.label = cv.create_text(x + g.u(16), y + h // 2, anchor="w", text="", font=g.font(size),
                                    fill=hx(TXT), state="disabled")
        self.chev_size = g.u(22)
        self.chev_item = cv.create_image(x + w - g.u(24), y + h // 2, anchor="center", state="disabled")
        self._chev_cache, self._chev_angle, self._chev_anim = {}, 0.0, None
        self._set_chev()
        self._set_text()
        cv.tag_bind(self.item, "<Enter>", lambda e: self._hover(True))
        cv.tag_bind(self.item, "<Leave>", lambda e: self._hover(False))
        cv.tag_bind(self.item, "<ButtonRelease-1>", lambda e: self.open())

    def _update_look(self, dur=0.16):
        st = "disabled" if not self.enabled else ("hover" if (self.hover or self.is_open) else "normal")
        self.fade.to(self.g.field_img(self.w, self.h, st), dur)

    def _set_text(self):
        t = ellipsize(self.g.font(self.size), str(self.value), self.w - self.g.u(56))
        self.cv.itemconfigure(self.label, text=t, fill=hx(TXT if self.enabled else DIM))

    def _set_chev(self):
        a = int(round(self._chev_angle / 6) * 6)
        key = (a, self.enabled)
        if key not in self._chev_cache:
            self._chev_cache[key] = ImageTk.PhotoImage(self.g.chevron(self.chev_size, a, self.enabled))
        self.cv.itemconfigure(self.chev_item, image=self._chev_cache[key])

    def _chev_to(self, target):
        if self._chev_anim:
            self._chev_anim.cancel()
        a0 = self._chev_angle

        def fn(t):
            self._chev_angle = a0 + (target - a0) * (ease_out_back(t, 1.0) if t < 1 else 1.0)
            self._set_chev()

        self._chev_anim = Anim(self.cv, 0.30, fn, lambda t: t)

    def _hover(self, on):
        if not self.enabled:
            return
        self.hover = on
        self.cv.configure(cursor="hand2" if on else "")
        self._update_look(0.16)

    def set(self, value):
        self.value = value
        self._set_text()

    def get(self):
        return self.value

    def set_values(self, values, value=None):
        self.values = list(values)
        self.value = value if value is not None else (self.values[0] if self.values else "")
        self._set_text()

    def set_enabled(self, en):
        self.enabled, self.hover = en, False
        if self._chev_anim:
            self._chev_anim.cancel()
        self._chev_angle = 0.0
        self._set_chev()
        self._update_look(0.22)
        self._set_text()

    def on_popup_closed(self):
        self.is_open = False
        self._chev_to(0)
        self._update_look(0.2)

    def open(self):
        if not self.enabled:
            return
        app = self.app
        if app.popup is not None and app.popup_owner is self:       # klik kedua = tutup
            app.close_popup()
            return
        owner, t = app.last_closed
        if owner is self and time.time() - t < 0.3:
            return
        app.close_popup()

        g = self.g
        u = g.u
        root = self.cv.winfo_toplevel()
        f = g.font(self.size)
        pad, item_h = u(6), u(36)
        n = len(self.values)
        pw = max(self.w, max(f.measure(str(v)) for v in self.values) + u(64))
        ph = 2 * pad + n * item_h

        pop = tk.Toplevel(root)
        pop.withdraw()
        pop.overrideredirect(True)
        key_bg = "#010101" if IS_WIN else hx((36, 28, 66))
        pop.configure(bg=key_bg)
        try:
            if IS_WIN:
                pop.attributes("-transparentcolor", "#010101")      # sudut membulat
        except Exception:
            pass
        c = tk.Canvas(pop, width=pw, height=ph, bg=key_bg, highlightthickness=0, bd=0, cursor="hand2")
        c.pack()
        bg = ImageTk.PhotoImage(g.popup_bg(pw, ph))
        hov = ImageTk.PhotoImage(g.popup_hover(pw - 2 * pad, item_h - u(4)))
        c._refs = (bg, hov)
        c.create_image(0, 0, anchor="nw", image=bg)
        hover_item = c.create_image(pad, pad, anchor="nw", image=hov, state="hidden")
        for i, v in enumerate(self.values):
            cy = pad + i * item_h + item_h // 2
            sel = (v == self.value)
            if sel:
                r = u(3)
                cx = pad + u(18)
                c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="white", outline="")
            c.create_text(pad + u(32), cy, anchor="w", text=str(v), font=g.font(self.size, sel),
                          fill="white" if sel else hx(MUTED), state="disabled")

        st = {"y": float(pad), "target": float(pad), "job": None, "shown": False, "t": time.perf_counter()}

        def slide():
            st["job"] = None
            now = time.perf_counter()
            dt = min(0.05, now - st["t"])
            st["t"] = now
            d = st["target"] - st["y"]
            st["y"] = st["target"] if abs(d) < 0.4 else st["y"] + d * (1 - 2.718 ** (-dt * 26))
            try:
                c.coords(hover_item, pad, st["y"])
                if st["y"] != st["target"]:
                    st["job"] = c.after(6, slide)
            except tk.TclError:
                pass

        def idx_at(y):
            i = (y - pad) // item_h
            return i if 0 <= i < n else None

        def on_move(e):
            i = idx_at(e.y)
            if i is None:
                c.itemconfigure(hover_item, state="hidden")
                st["shown"] = False
                return
            st["target"] = float(pad + i * item_h + u(2))
            if not st["shown"]:
                st["y"], st["shown"] = st["target"], True
                c.itemconfigure(hover_item, state="normal")
            if st["job"] is None:
                st["t"] = time.perf_counter()
                slide()

        def on_leave(e):
            c.itemconfigure(hover_item, state="hidden")
            st["shown"] = False

        def on_release(e):
            i = idx_at(e.y)
            if i is not None:
                self._choose(self.values[i])

        c.bind("<Motion>", on_move)
        c.bind("<Leave>", on_leave)
        c.bind("<ButtonRelease-1>", on_release)
        pop.bind("<Escape>", lambda e: app.close_popup())

        rx = self.cv.winfo_rootx() + self.x + self.w - pw
        ry = self.cv.winfo_rooty() + self.y + self.h + u(6)
        off = -u(10)
        if ry + ph > root.winfo_screenheight() - u(40):
            ry = self.cv.winfo_rooty() + self.y - ph - u(6)
            off = u(10)
        rx, ry = max(0, rx), max(0, ry)
        pop._anim = (rx, ry, off)
        try:
            pop.attributes("-alpha", 0.0)
        except Exception:
            pass
        pop.geometry(f"{pw}x{ph}+{rx}+{ry + off}")
        pop.deiconify()
        try:
            pop.attributes("-topmost", True)
        except Exception:
            pass
        app.popup, app.popup_owner = pop, self
        self.is_open = True
        self._chev_to(180)
        self._update_look(0.16)
        app.popup_in(pop)

    def _choose(self, val):
        self.app.close_popup()
        self.value = val
        self._set_text()
        if self.cmd:
            self.cmd(val)
