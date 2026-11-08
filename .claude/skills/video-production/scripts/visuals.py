"""Motor visual: fundos animados, tipografia cinética, cards, números, botões, legendas.

Cada cena vira uma lista de elementos com `draw(canvas, t)`; o renderizador chama
isso quadro a quadro. Tudo com Pillow + numpy.
"""
from __future__ import annotations

import functools
import math
import os
import random
import re
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}


# ------------------------------------------------------------------ utilitários
def hex2rgb(h, a=None):
    if isinstance(h, (tuple, list)):
        rgb = tuple(int(c) for c in h[:3])
    else:
        h = h.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return rgb if a is None else (*rgb, a)


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_cubic(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out_back(x, s=1.70158):
    x = clamp(x) - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2


def luminance(rgb):
    r, g, b = (c / 255 for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


_FALLBACK_FONTS = {
    "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"],
    "black": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/System/Library/Fonts/Supplemental/Arial Black.ttf", "C:/Windows/Fonts/ariblk.ttf"],
    "regular": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf", "C:/Windows/Fonts/arial.ttf"],
    "italic": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
               "/System/Library/Fonts/Supplemental/Arial Italic.ttf", "C:/Windows/Fonts/ariali.ttf"],
}


@functools.lru_cache(maxsize=None)
def find_font(spec: str | None, weight: str = "bold") -> str:
    if spec and os.path.isfile(spec):
        return spec
    style = {"bold": "Bold", "black": "Black", "regular": "Regular", "italic": "Bold Italic"}[weight]
    if shutil.which("fc-match"):
        name = spec or "Inter"
        out = subprocess.run(["fc-match", "-f", "%{file}", f"{name}:style={style}"],
                             capture_output=True, text=True).stdout.strip()
        if out and os.path.isfile(out):
            return out
    for p in _FALLBACK_FONTS[weight]:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("Nenhuma fonte encontrada; defina theme.font com o caminho de um .ttf/.otf")


@functools.lru_cache(maxsize=None)
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(8, int(size)))


def paste(canvas: Image.Image, sprite: Image.Image, x: float, y: float, alpha: float = 1.0,
          scale: float = 1.0) -> None:
    """Compõe `sprite` em (x, y) com opacidade e escala (a partir do centro)."""
    if alpha <= 0.004 or sprite is None:
        return
    w, h = sprite.size
    if abs(scale - 1.0) > 0.002:
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        sprite = sprite.resize((nw, nh), Image.BILINEAR)
        x += (w - nw) / 2
        y += (h - nh) / 2
        w, h = nw, nh
    if alpha < 0.996:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha)))
    x, y = int(round(x)), int(round(y))
    cw, ch = canvas.size
    l, t = max(0, -x), max(0, -y)
    r, b = min(w, cw - x), min(h, ch - y)
    if r <= l or b <= t:
        return
    if (l, t, r, b) != (0, 0, w, h):
        sprite = sprite.crop((l, t, r, b))
    canvas.alpha_composite(sprite, (x + l, y + t))


def anim_state(kind: str, p: float):
    """Devolve (alpha, dx, dy, scale) para a animação de entrada no progresso p∈[0,1]."""
    if p <= 0:
        return 0.0, 0, 0, 1.0
    e = ease_out_cubic(p)
    if kind == "none":
        return 1.0, 0, 0, 1.0
    if kind == "fade":
        return e, 0, 0, 1.0
    if kind in ("up", "slide_up", "rise"):
        return e, 0, (1 - e) * 70, 1.0
    if kind in ("down", "slide_down"):
        return e, 0, -(1 - e) * 70, 1.0
    if kind in ("left", "slide_left"):
        return e, -(1 - e) * 140, 0, 1.0
    if kind in ("right", "slide_right"):
        return e, (1 - e) * 140, 0, 1.0
    if kind == "pop":
        return min(1.0, p * 3), 0, 0, 0.55 + 0.45 * ease_out_back(p)
    if kind == "zoom":
        return e, 0, 0, 1.35 - 0.35 * e
    if kind == "blur":  # aproximação: zoom-out sutil + fade
        return e ** 2, 0, 0, 1.08 - 0.08 * e
    return e, 0, (1 - e) * 70, 1.0


# ------------------------------------------------------------------ texto
_MARK = re.compile(r"\*\*(.+?)\*\*")


def parse_marked(text: str):
    """'Seja **muito** rápido!' -> [('Seja', False), ('muito', True), ('rápido!', False)]"""
    words, in_hl = [], False
    for tok in text.split():
        n = tok.count("**")
        words.append((tok.replace("**", ""), in_hl or n > 0))
        if n % 2:
            in_hl = not in_hl
    return [(w, h) for w, h in words if w]


def strip_marks(text: str) -> str:
    return text.replace("**", "")


def text_sprite(txt, fnt, color, stroke=0, stroke_color=(0, 0, 0), shadow=True):
    asc, desc = fnt.getmetrics()
    pad = int(fnt.size * 0.18) + stroke
    w = int(fnt.getlength(txt)) + 2 * pad
    h = asc + desc + 2 * pad
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((pad, pad + fnt.size * 0.05), txt, font=fnt, fill=(0, 0, 0, 150),
                                stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(fnt.size * 0.07)))
    ImageDraw.Draw(img).text((pad, pad), txt, font=fnt, fill=hex2rgb(color, 255), stroke_width=stroke,
                             stroke_fill=hex2rgb(stroke_color, 255))
    return img, pad


def layout_words(words, fnt, max_w, align="center", line_gap=1.12):
    """Quebra linhas e devolve [(palavra, destaque, x, y)], largura, altura."""
    space = fnt.getlength(" ")
    lines, cur, cur_w = [], [], 0.0
    for w, hl in words:
        ww = fnt.getlength(w)
        add = ww if not cur else cur_w + space + ww
        if cur and add > max_w:
            lines.append((cur, cur_w))
            cur, cur_w = [(w, hl, ww)], ww
        else:
            cur.append((w, hl, ww))
            cur_w = add
    if cur:
        lines.append((cur, cur_w))
    lh = fnt.size * line_gap
    out = []
    for i, (ws, lw) in enumerate(lines):
        x = {"left": 0, "right": max_w - lw}.get(align, (max_w - lw) / 2)
        for w, hl, ww in ws:
            out.append((w, hl, x, i * lh))
            x += ww + space
    return out, max_w, len(lines) * lh, len(lines)


# ------------------------------------------------------------------ elementos
class Element:
    height = 0
    appear = 0.0      # momento (s, relativo à cena) em que o elemento entra
    anim = "up"
    anim_dur = 0.6
    sfx = None        # efeito sonoro disparado na entrada

    def draw(self, canvas, x0, y0, t):  # pragma: no cover - interface
        raise NotImplementedError


class TextEl(Element):
    def __init__(self, text, font_path, size, color, accent, max_w, anim="up", align="center",
                 stroke=0, shadow=True, max_lines=6, word_stagger=None):
        self.anim = anim
        words = parse_marked(text)
        size = int(size)
        while True:
            fnt = font(font_path, size)
            self.layout, self.w, self.h, n = layout_words(words, fnt, max_w, align)
            if n <= max_lines or size < 28:
                break
            size = int(size * 0.9)
        self.fnt, self.size = fnt, size
        self.sprites = []
        for w, hl, x, y in self.layout:
            spr, pad = text_sprite(w, fnt, accent if hl else color, stroke=stroke, shadow=shadow)
            self.sprites.append((spr, x - pad, y - pad))
        self.height = int(self.h + size * 0.15)
        self.block = Image.new("RGBA", (int(self.w) + 2 * size, self.height + 2 * size), (0, 0, 0, 0))
        for spr, x, y in self.sprites:
            self.block.alpha_composite(spr, (int(x + size), int(y + size)))
        self.word_stagger = word_stagger
        if anim in ("words", "typewriter"):
            self.anim_dur = 0.35 + len(self.sprites) * self._stagger()

    def _stagger(self):
        if self.word_stagger:
            return self.word_stagger
        return min(0.12, 1.4 / max(1, len(self.sprites)))

    def draw(self, canvas, x0, y0, t):
        lt = t - self.appear
        if lt <= 0:
            return
        if self.anim in ("words", "typewriter"):
            st = self._stagger()
            for i, (spr, x, y) in enumerate(self.sprites):
                p = (lt - i * st) / (0.05 if self.anim == "typewriter" else 0.35)
                a, dx, dy, sc = anim_state("none" if self.anim == "typewriter" else "up", p)
                if self.anim == "typewriter" and p <= 0:
                    continue
                paste(canvas, spr, x0 + x + dx, y0 + y + dy * 0.6, a, sc)
            return
        a, dx, dy, sc = anim_state(self.anim, lt / self.anim_dur)
        paste(canvas, self.block, x0 - self.size + dx, y0 - self.size + dy, a, sc)


class PillEl(Element):
    """Rótulo pequeno (kicker) ou botão de CTA."""

    def __init__(self, text, font_path, size, fg, bg, pulse=False, anim="pop", outline=False):
        self.anim, self.pulse = anim, pulse
        fnt = font(font_path, int(size))
        tw = fnt.getlength(text)
        asc, desc = fnt.getmetrics()
        px, py = size * 0.9, size * 0.5
        w, h = int(tw + 2 * px), int(asc + desc + 2 * py)
        m = int(size * 0.6)
        img = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((m, m + size * 0.15, m + w, m + h + size * 0.15), radius=h // 2,
                                                 fill=(0, 0, 0, 110))
        img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(size * 0.3)))
        d = ImageDraw.Draw(img)
        if outline:
            d.rounded_rectangle((m, m, m + w, m + h), radius=h // 2, outline=hex2rgb(bg, 255),
                                width=max(2, int(size * 0.12)))
        else:
            d.rounded_rectangle((m, m, m + w, m + h), radius=h // 2, fill=hex2rgb(bg, 255))
        d.text((m + px, m + py), text, font=fnt, fill=hex2rgb(fg, 255))
        self.img, self.m, self.w = img, m, w
        self.height = h

    def draw(self, canvas, x0, y0, t):
        lt = t - self.appear
        if lt <= 0:
            return
        a, dx, dy, sc = anim_state(self.anim, lt / self.anim_dur)
        if self.pulse and lt > self.anim_dur:
            sc *= 1 + 0.045 * math.sin((lt - self.anim_dur) * 2 * math.pi * 1.3)
        cx = x0 + self.cw / 2 - self.img.width / 2
        paste(canvas, self.img, cx + dx, y0 - self.m + dy, a, sc)


class BulletsEl(Element):
    def __init__(self, items, font_path, size, color, accent, max_w, times, style="check"):
        self.anim = "left"
        self.times = times
        fnt = font(font_path, int(size))
        self.rows = []
        y = 0
        icon = int(size * 1.05)
        gap = size * 0.55
        for i, it in enumerate(items):
            tel = TextEl(it, font_path, size, color, accent, max_w - icon - size * 0.6, anim="none",
                         align="left", max_lines=3)
            badge = Image.new("RGBA", (icon * 2, icon * 2), (0, 0, 0, 0))
            d = ImageDraw.Draw(badge)
            d.ellipse((icon // 2, icon // 2, icon * 3 // 2, icon * 3 // 2), fill=hex2rgb(accent, 255))
            ink = (20, 20, 20, 255) if luminance(hex2rgb(accent)) > 0.55 else (255, 255, 255, 255)
            c = icon
            if style == "number":
                bf = font(font_path, int(icon * 0.6))
                d.text((c, c), str(i + 1), font=bf, fill=ink, anchor="mm")
            else:
                lw = max(3, icon // 9)
                d.line([(c - icon * 0.22, c + icon * 0.0), (c - icon * 0.05, c + icon * 0.18),
                        (c + icon * 0.25, c - icon * 0.17)], fill=ink, width=lw, joint="curve")
            row_h = max(icon, tel.height)
            self.rows.append((badge, tel, y, row_h))
            y += row_h + gap
        self.height = int(y - gap)
        self.icon = icon
        self.max_w = max_w
        # largura real usada (para centralizar o bloco)
        self.block_w = icon + size * 0.6 + max(max((w[2] + tel.fnt.getlength(w[0])) for w in tel.layout)
                                               for _, tel, _, _ in self.rows)

    def draw(self, canvas, x0, y0, t):
        bx = x0 + (self.max_w - self.block_w) / 2
        for i, (badge, tel, y, row_h) in enumerate(self.rows):
            lt = t - self.times[i]
            if lt <= 0:
                continue
            ba, _, _, bs = anim_state("pop", lt / 0.45)
            paste(canvas, badge, bx - self.icon / 2, y0 + y + (row_h - self.icon) / 2 - self.icon / 2 + 2, ba, bs)
            tel.anim, tel.anim_dur, tel.appear = "right", 0.5, self.times[i] + 0.05
            tel.draw(canvas, bx + self.icon * 1.6, y0 + y + (row_h - tel.height) / 2, t)


class StatEl(Element):
    """Número grande contando de 0 até o valor."""

    def __init__(self, value, font_path, size, color, accent, prefix="", suffix="", decimals=None,
                 count_dur=1.4):
        self.value = float(value)
        self.prefix, self.suffix = prefix, suffix
        self.decimals = decimals if decimals is not None else (0 if float(value).is_integer() else 1)
        self.fnt = font(font_path, int(size))
        self.color, self.accent = color, accent
        self.count_dur = count_dur
        self.anim = "pop"
        asc, desc = self.fnt.getmetrics()
        self.height = asc + desc
        self._cache = {}

    def fmt(self, v):
        s = f"{v:,.{self.decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{self.prefix}{s}{self.suffix}"

    def draw(self, canvas, x0, y0, t):
        lt = t - self.appear
        if lt <= 0:
            return
        p = ease_out_cubic(lt / self.count_dur)
        txt = self.fmt(self.value * p)
        if txt not in self._cache:
            self._cache[txt] = text_sprite(txt, self.fnt, self.accent, shadow=True)
        spr, pad = self._cache[txt]
        a, dx, dy, sc = anim_state("pop", lt / 0.5)
        if lt > self.count_dur:  # leve "respiração" depois de terminar
            sc *= 1 + 0.02 * math.sin((lt - self.count_dur) * 3)
        paste(canvas, spr, x0 + (self.cw - spr.width) / 2 + dx, y0 - pad + dy, a, sc)


class ImageCardEl(Element):
    def __init__(self, path, max_w, max_h, radius=36, anim="pop"):
        self.anim = anim
        im = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
        scale = min(max_w / im.width, max_h / im.height)
        w, h = int(im.width * scale), int(im.height * scale)
        im = im.resize((w, h), Image.LANCZOS)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
        im.putalpha(mask)
        m = 50
        card = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
        sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((m, m + 18, m + w, m + h + 18), radius=radius, fill=(0, 0, 0, 140))
        card.alpha_composite(sh.filter(ImageFilter.GaussianBlur(22)))
        card.alpha_composite(im, (m, m))
        self.card, self.m, self.w = card, m, w
        self.height = h

    def draw(self, canvas, x0, y0, t):
        lt = t - self.appear
        if lt <= 0:
            return
        a, dx, dy, sc = anim_state(self.anim, lt / self.anim_dur)
        dy += math.sin(lt * 1.6) * 6  # flutuação
        paste(canvas, self.card, x0 + (self.cw - self.card.width) / 2 + dx, y0 - self.m + dy, a, sc)


# ------------------------------------------------------------------ fundos
def gradient(w, h, colors, angle=135.0, noise=True):
    cols = np.array([hex2rgb(c) for c in colors], dtype=np.float32)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    a = math.radians(angle)
    d = xs * math.cos(a) + ys * math.sin(a)
    d = (d - d.min()) / (d.max() - d.min() + 1e-6)
    pos = d * (len(cols) - 1)
    i0 = np.clip(pos.astype(int), 0, len(cols) - 2) if len(cols) > 1 else np.zeros_like(pos, dtype=int)
    f = (pos - i0)[..., None]
    if len(cols) == 1:
        img = np.broadcast_to(cols[0], (h, w, 3)).copy()
    else:
        img = cols[i0] * (1 - f) + cols[i0 + 1] * f
    if noise:
        img += np.random.default_rng(1).normal(0, 1.6, img.shape).astype(np.float32)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def radial(w, h, inner, outer, cx=0.5, cy=0.4, r=0.9):
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xs / w - cx) * (w / max(w, h))) ** 2 + ((ys / h - cy) * (h / max(w, h))) ** 2) / r
    d = np.clip(d, 0, 1)[..., None]
    img = np.array(hex2rgb(inner), np.float32) * (1 - d) + np.array(hex2rgb(outer), np.float32) * d
    img += np.random.default_rng(2).normal(0, 1.6, img.shape).astype(np.float32)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


@functools.lru_cache(maxsize=4)
def vignette(w, h, strength=0.55):
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xs / w - 0.5) * 2) ** 2 + ((ys / h - 0.5) * 2) ** 2) / math.sqrt(2)
    a = np.clip((d - 0.45) / 0.55, 0, 1) ** 1.6 * 255 * strength
    v = np.zeros((h, w, 4), np.uint8)
    v[..., 3] = a.astype(np.uint8)
    return Image.fromarray(v, "RGBA")


@functools.lru_cache(maxsize=64)
def soft_dot(r, color):
    s = int(r * 4)
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r), fill=color)
    return im.filter(ImageFilter.GaussianBlur(r * 0.45))


class Background:
    def __init__(self, kind, W, H, colors, accent, image=None, seed=0, motion="zoom_in", shade_top=False):
        self.kind, self.W, self.H = kind, W, H
        self.colors, self.accent = colors, accent
        self.rng = random.Random(seed)
        self.pan = int(max(W, H) * 0.12)
        if kind == "image" and image:
            src = ImageOps.exif_transpose(Image.open(image)).convert("RGB")
            src = ImageOps.fit(src, (int(W * 1.12), int(H * 1.12)), Image.LANCZOS)
            self.img = src.convert("RGBA")
            self.motion = motion
            ov = np.zeros((H, W, 4), np.uint8)
            ramp = np.linspace(0, 1, H)[:, None]
            shade = 0.25 + 0.55 * ramp ** 1.5
            if shade_top:  # escurece o topo quando o texto fica em cima
                shade = np.maximum(shade, 0.62 * np.clip(1 - ramp / 0.42, 0, 1) ** 1.3)
            ov[..., 3] = (np.clip(shade, 0, 1) * 255).astype(np.uint8)
            self.overlay = Image.fromarray(ov, "RGBA")
        elif kind == "radial" or kind == "spotlight":
            self.base = radial(W + self.pan, H + self.pan, colors[-1], colors[0])
        else:
            self.base = gradient(W + self.pan, H + self.pan, colors, angle=self.rng.choice([115, 135, 155, 60]))
        if kind in ("particles", "bokeh"):
            n = 26 if kind == "particles" else 14
            pal = [hex2rgb(c) for c in [accent] + list(colors[1:])]
            self.parts = []
            for _ in range(n):
                r = self.rng.uniform(4, 14) if kind == "particles" else self.rng.uniform(40, 120)
                col = (*self.rng.choice(pal), int(self.rng.uniform(70, 170) if kind == "particles" else 55))
                self.parts.append(dict(x=self.rng.random(), y=self.rng.random(), r=int(r), col=col,
                                       sp=self.rng.uniform(0.015, 0.05), ph=self.rng.uniform(0, 6.28),
                                       amp=self.rng.uniform(10, 40)))

    def render(self, t, gt):
        W, H = self.W, self.H
        if self.kind == "image":
            z = 1.0 + 0.1 * clamp(t / 12) if self.motion != "zoom_out" else 1.1 - 0.1 * clamp(t / 12)
            iw, ih = self.img.size
            cw, ch = iw / z, ih / z
            px = (iw - cw) / 2 + (math.sin(t * 0.15) * 0.25 * (iw - cw) if self.motion == "pan" else 0)
            frame = self.img.crop((int(px), int((ih - ch) / 2), int(px + cw), int((ih + ch) / 2))).resize(
                (W, H), Image.BILINEAR)
            frame.alpha_composite(self.overlay)
            return frame
        ox = self.pan / 2 + math.sin(gt * 0.25) * self.pan / 2.2
        oy = self.pan / 2 + math.cos(gt * 0.2) * self.pan / 2.2
        frame = self.base.crop((int(ox), int(oy), int(ox) + W, int(oy) + H))
        if self.kind in ("particles", "bokeh"):
            for p in self.parts:
                y = ((p["y"] - gt * p["sp"]) % 1.2 - 0.1) * H
                x = p["x"] * W + math.sin(gt * 0.8 + p["ph"]) * p["amp"]
                dot = soft_dot(p["r"], p["col"])
                paste(frame, dot, x - dot.width / 2, y - dot.height / 2)
        elif self.kind == "waves":
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ac = hex2rgb(self.accent)
            for i in range(3):
                amp = H * (0.025 + 0.012 * i)
                base_y = H * (0.78 + 0.06 * i)
                k = 2 * math.pi / (W * (0.9 + 0.3 * i))
                pts = [(x, base_y + amp * math.sin(k * x + gt * (0.9 + 0.35 * i) + i)) for x in range(0, W + 41, 40)]
                wl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(wl).polygon(pts + [(W, H), (0, H)], fill=(*ac, 34 + 10 * i))
                layer.alpha_composite(wl)
            frame.alpha_composite(layer)
        elif self.kind == "grid":
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            step = int(min(W, H) / 9)
            off = (gt * 30) % step
            col = (255, 255, 255, 22)
            for x in range(-step, W + step, step):
                d.line([(x + off, 0), (x + off, H)], fill=col, width=2)
            for y in range(-step, H + step, step):
                d.line([(0, y + off), (W, y + off)], fill=col, width=2)
            frame.alpha_composite(layer)
        frame.alpha_composite(vignette(W, H))
        return frame


# ------------------------------------------------------------------ cenas ilustradas (imagens do usuário)
def grade(img: Image.Image, kind: str | None, seed: int = 0) -> Image.Image:
    """Correção de cor / look: none warm cool vintage bw cinematic vivid matte."""
    if not kind or kind == "none":
        return img
    if kind == "vivid":
        from PIL import ImageEnhance
        return ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(1.28)).enhance(1.06)
    a = np.asarray(img.convert("RGB")).astype(np.float32) / 255
    L = (0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2])[..., None]
    if kind == "warm":
        a = a * [1.05, 1.0, 0.88] + [0.02, 0.01, 0]
    elif kind == "cool":
        a = a * [0.92, 1.0, 1.08]
    elif kind == "bw":
        c = np.clip((L - 0.5) * 1.15 + 0.5, 0, 1)
        a = np.repeat(c, 3, axis=2)
    elif kind == "cinematic":
        a = a + (1 - L) * np.array([-0.05, 0.015, 0.05]) + L * np.array([0.06, 0.015, -0.05])
        a = np.clip(a, 0, 1)
        a = a + (a - 0.5) * 0.12  # contraste em S leve
    elif kind == "matte":
        a = a * 0.9 + 0.06
    elif kind == "vintage":
        a = a * 0.86 + 0.07
        a[..., 0] = a[..., 0] ** 0.92
        a[..., 2] = a[..., 2] ** 1.12 * 0.95
        a = a * 0.8 + L * 0.2
        a = a + np.random.default_rng(seed).normal(0, 0.022, a.shape[:2])[..., None]
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "RGB")


def _shade_overlay(W, H, shade, strength=1.0):
    ramp = np.linspace(0, 1, H)[:, None]
    a = np.zeros((H, 1))
    if shade in ("bottom", "both"):
        a = np.maximum(a, 0.78 * np.clip((ramp - 0.45) / 0.55, 0, 1) ** 1.4)
    if shade in ("top", "both"):
        a = np.maximum(a, 0.65 * np.clip(1 - ramp / 0.42, 0, 1) ** 1.3)
    if shade == "full":
        a = a + 0.35
    ov = np.zeros((H, W, 4), np.uint8)
    ov[..., 3] = (np.clip(a * strength, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(ov, "RGBA")


MOTIONS = ["zoom_in", "pan_right", "zoom_out", "pan_left", "pan_up", "zoom_in", "pan_down"]


class PhotoShot:
    """Uma imagem preparada (grade + enquadramento) com movimento de câmera."""
    HEAD = 1.22  # folga de resolução para o zoom não perder nitidez

    def __init__(self, W, H, path, motion="auto", focus=(0.5, 0.45), fit="auto", look=None, idx=0,
                 strength=1.0):
        self.W, self.H = W, H
        SW, SH = int(W * self.HEAD), int(H * self.HEAD)
        img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        ar_img, ar_out = img.width / img.height, W / H
        if fit == "auto":  # proporção muito diferente -> fundo desfocado + foto inteira
            fit = "contain" if max(ar_img / ar_out, ar_out / ar_img) > 1.55 else "cover"
        img = grade(img, look, idx)
        fx, fy = focus
        if fit == "contain":
            bg = ImageOps.fit(img, (SW, SH), Image.LANCZOS, centering=(fx, fy))
            bg = bg.filter(ImageFilter.GaussianBlur(SW * 0.035))
            bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.45)
            fg = ImageOps.contain(img, (int(SW * 0.9), int(SH * 0.9)), Image.LANCZOS)
            src = bg.convert("RGBA")
            sh = Image.new("RGBA", src.size, (0, 0, 0, 0))
            ox, oy = (SW - fg.width) // 2, (SH - fg.height) // 2
            ImageDraw.Draw(sh).rectangle((ox, oy + 20, ox + fg.width, oy + fg.height + 20), fill=(0, 0, 0, 150))
            src.alpha_composite(sh.filter(ImageFilter.GaussianBlur(30)))
            src.alpha_composite(fg.convert("RGBA"), (ox, oy))
            self.focus = (0.5 + (fx - 0.5) * fg.width / SW, 0.5 + (fy - 0.5) * fg.height / SH)
        else:
            src = ImageOps.fit(img, (SW, SH), Image.LANCZOS, centering=(fx, fy)).convert("RGBA")
            self.focus = (fx, fy)
        self.src = src
        self.motion = MOTIONS[idx % len(MOTIONS)] if motion in (None, "auto") else motion
        self.strength = strength

    def frame(self, p):
        p = clamp(p)
        p = 0.4 * p + 0.6 * ease_in_out(p)
        zmax = 1 + 0.18 * self.strength
        fx, fy = self.focus
        m = self.motion
        if m == "zoom_in":
            f = 1 / (1 + (zmax - 1) * p)
            cx, cy = 0.5 + (fx - 0.5) * p, 0.5 + (fy - 0.5) * p
        elif m == "zoom_out":
            f = 1 / (zmax - (zmax - 1) * p)
            cx, cy = fx + (0.5 - fx) * p, fy + (0.5 - fy) * p
        elif m in ("pan_left", "pan_right"):
            f = 1 / zmax
            span = (1 - f) / 2 * 0.9
            d = -1 if m == "pan_left" else 1
            cx, cy = 0.5 - d * span + 2 * d * span * p, fy
        elif m in ("pan_up", "pan_down"):
            f = 1 / zmax
            span = (1 - f) / 2 * 0.9
            d = -1 if m == "pan_up" else 1
            cx, cy = fx, 0.5 - d * span + 2 * d * span * p
        else:  # static / respiração mínima
            f = 1 / (1 + 0.04 * p + 0.02)
            cx, cy = fx, fy
        cx = clamp(cx, f / 2, 1 - f / 2)
        cy = clamp(cy, f / 2, 1 - f / 2)
        SW, SH = self.src.size
        w, h = f * SW, f * SH
        box = (cx * SW - w / 2, cy * SH - h / 2, cx * SW + w / 2, cy * SH + h / 2)
        return self.src.resize((self.W, self.H), Image.BILINEAR, box=box)


class PhotoBackground:
    """Fundo de cena ilustrada: 1+ imagens com Ken Burns, crossfade entre elas, look e sombreamento."""

    def __init__(self, W, H, shots, scene_dur, shade="bottom", look=None, fit="auto", xfade=0.7,
                 strength=1.0, seed=0):
        self.W, self.H, self.dur, self.xf = W, H, scene_dur, xfade
        norm = []
        for i, s in enumerate(shots):
            s = {"path": s} if isinstance(s, str) else dict(s)
            norm.append(s)
        fixed = sum(s.get("duration", 0) for s in norm)
        free = [s for s in norm if not s.get("duration")]
        rest = max(0.5, scene_dur - fixed) / max(1, len(free))
        t = 0.0
        self.shots = []
        for i, s in enumerate(norm):
            d = s.get("duration") or rest
            shot = PhotoShot(W, H, s["path"], s.get("motion", "auto"), tuple(s.get("focus", (0.5, 0.45))),
                             s.get("fit", fit), s.get("look", look), idx=i + seed, strength=s.get("zoom", strength))
            self.shots.append((t, d, shot))
            t += d
        ov = _shade_overlay(W, H, shade) if shade and shade != "none" else Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.overlay = Image.alpha_composite(ov, vignette(W, H, 0.35))  # 1 composição por quadro

    def _shot_frame(self, i, t):
        st, d, shot = self.shots[i]
        return shot.frame((t - st + self.xf / 2) / (d + self.xf))

    def render(self, t, gt=0.0):
        i = 0
        for k, (st, d, _) in enumerate(self.shots):
            if t >= st:
                i = k
        frame = self._shot_frame(i, t)
        st, d, _ = self.shots[i]
        if i + 1 < len(self.shots) and t > st + d - self.xf / 2:
            p = (t - (st + d - self.xf / 2)) / self.xf
            frame = Image.blend(frame, self._shot_frame(i + 1, t), ease_in_out(p))
        frame.alpha_composite(self.overlay)
        return frame


class LowerThirdEl(Element):
    """Tarja de identificação (título + subtítulo) com barra de destaque, entra e sai animada."""

    def __init__(self, title, subtitle, font_bold, font_reg, u, accent, text_color="#ffffff", max_w=900):
        self.anim, self.end = "left", None
        ft, fs = font(font_bold, int(u * 0.05)), font(font_reg, int(u * 0.034))
        pad = int(u * 0.028)
        tw = min(max_w, max(ft.getlength(title or ""), fs.getlength(subtitle or "")))
        a1, d1 = ft.getmetrics()
        a2, d2 = fs.getmetrics()
        h = pad * 2 + a1 + d1 + ((a2 + d2 + pad // 3) if subtitle else 0)
        bar = max(6, int(u * 0.011))
        w = int(tw + pad * 2 + bar)
        img = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle((20, 26, 20 + w, 26 + h), fill=(0, 0, 0, 120))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
        d = ImageDraw.Draw(img)
        d.rectangle((20, 20, 20 + w, 20 + h), fill=(10, 10, 14, 200))
        d.rectangle((20, 20, 20 + bar, 20 + h), fill=hex2rgb(accent, 255))
        d.text((20 + bar + pad, 20 + pad), title or "", font=ft, fill=hex2rgb(text_color, 255))
        if subtitle:
            d.text((20 + bar + pad, 20 + pad + a1 + d1 + pad // 3), subtitle, font=fs, fill=hex2rgb(accent, 255))
        self.img = img
        self.height = h

    def draw(self, canvas, x0, y0, t):
        lt = t - self.appear
        if lt <= 0:
            return
        a, dx, dy, sc = anim_state("left", lt / 0.55)
        if self.end is not None and t > self.end:
            a *= clamp(1 - (t - self.end) / 0.35)
        paste(canvas, self.img, x0 - 20 + dx, y0 - 20, a)


# ------------------------------------------------------------------ legendas
class Subtitles:
    def __init__(self, W, H, font_path, accent, style="karaoke", position=None, size=None, color="#ffffff"):
        self.W, self.H = W, H
        vertical = H > W
        self.size = int(size or (W * 0.066 if vertical else H * 0.058))
        self.fnt = font(font_path, self.size)
        self.accent, self.color, self.style = accent, color, style
        self.y_center = H * (position if position is not None else (0.80 if vertical else 0.87))
        self.max_w = W * (0.84 if vertical else 0.75)
        self.chunks = []  # (start, end, [(word, s, e)])
        self._cache = {}

    def add_chunks(self, chunks):
        self.chunks.extend(chunks)

    def _render(self, ci, active):
        key = (ci, active)
        if key in self._cache:
            return self._cache[key]
        _, _, words = self.chunks[ci]
        lay, w, h, _ = layout_words([(wd, i == active) for i, (wd, _, _) in enumerate(words)], self.fnt, self.max_w)
        img = Image.new("RGBA", (int(self.max_w) + 2 * self.size, int(h) + 2 * self.size), (0, 0, 0, 0))
        stroke = max(4, self.size // 9)
        if self.style == "box":
            ImageDraw.Draw(img).rounded_rectangle(
                (self.size * 0.6, self.size * 0.6, img.width - self.size * 0.6, img.height - self.size * 0.6),
                radius=self.size // 2, fill=(0, 0, 0, 150))
            stroke = 0
        for wd, hl, x, y in lay:
            col = self.accent if (hl and self.style == "karaoke") else self.color
            spr, pad = text_sprite(wd, self.fnt, col, stroke=stroke, shadow=True)
            img.alpha_composite(spr, (int(x + self.size - pad), int(y + self.size - pad)))
        if len(self._cache) > 400:
            self._cache.clear()
        self._cache[key] = img
        return img

    def draw(self, canvas, T):
        for ci, (s, e, words) in enumerate(self.chunks):
            if s <= T < e:
                active = -1
                for i, (_, ws, we) in enumerate(words):
                    if ws <= T:
                        active = i
                img = self._render(ci, active)
                p = (T - s) / 0.12
                a, _, dy, sc = anim_state("pop", p)
                paste(canvas, img, (self.W - img.width) / 2, self.y_center - img.height / 2 + dy, a, 0.92 + 0.08 * sc)
                return
