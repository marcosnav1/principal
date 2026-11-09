#!/usr/bin/env python3
"""Edição: 'Vade retro' — 6 clipes Veo + narração ElevenLabs + desenho sonoro original + 6 legendas."""
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, "/home/user/principal/.claude/skills/video-production/scripts")
import audio as A  # noqa: E402

W_DIR = os.path.dirname(os.path.abspath(__file__))
CL = lambda n: os.path.join(W_DIR, "clips", f"0{n}.mp4")  # noqa: E731
OUT = os.path.join(W_DIR, "out")
os.makedirs(OUT, exist_ok=True)
W, H, FPS = 1080, 1920, 24
SR = A.SR
FONT = os.path.join(W_DIR, "fonts/package/files/cinzel-latin-800-normal.woff")

# ---------------------------------------------------------------- linha do tempo
# (clipe, src_ini, src_fim, T_ini, T_fim, velocidade)  velocidade < 1 = mais lento
SEGS = [
    (1, 1.00, 9.50, 0.00, 8.50, 1.0),
    (2, 0.30, 8.90, 8.50, 17.10, 1.0),
    (3, 1.60, 9.85, 17.10, 25.35, 1.0),
    (4, 0.40, 6.90, 25.35, 31.85, 1.0),
    (5, 0.00, 10.0, 31.85, 42.40, 0.95),
    (6, 0.00, 0.00, 42.40, 42.90, 0.0),     # Jesus imóvel durante o silêncio
    (6, 0.00, 10.0, 42.90, 52.90, 1.0),
    (6, 9.95, 9.95, 52.90, 56.30, 0.0),     # último quadro + aproximação lenta
]
TOTAL = 56.30
CUT_SILENCE = (42.40, 42.90)
WHISPER_SRC = (55.75, 58.45)   # "Escreve amém e sela a tua casa." na narração original
WHISPER_AT = 52.85

CAPS = [  # (texto, T_ini, T_fim, cor)
    ("VÊM DIAS DIFÍCEIS", 0.12, 8.50, "#ffffff"),
    ("NÃO É FRAQUEZA.\nÉ CERCO.", 14.93, 17.10, "#ffffff"),
    ("NADA QUE É TEU\nSE PERDE", 22.11, 25.35, "#ffffff"),
    ("À VOZ DO ARCANJO", 25.53, 31.85, "#ffffff"),
    ("VADE RETRO,\nSATANA", 34.11, 42.40, "#e8c15a"),
    ("ESCREVE AMÉM", 52.85, 56.30, "#ffffff"),
]


# ---------------------------------------------------------------- áudio
def db(x):
    return 10 ** (x / 20)


def rms(y):
    return float(np.sqrt(np.mean(y ** 2)) + 1e-12)


def place(buf, sig, t, g=1.0):
    i = int(round(t * SR))
    if sig.ndim == 1:
        sig = np.stack([sig, sig], 1)
    n = min(len(sig), len(buf) - i)
    if n > 0:
        buf[i:i + n] += sig[:n] * g


def clip_audio(n, s0, s1, speed):
    y = A.load_audio(CL(n), channels=2)
    seg = y[int(s0 * SR):int(s1 * SR)]
    if speed and abs(speed - 1) > 1e-3:  # acompanha a imagem (sem afetar vozes: só clipe 5, sem fala)
        idx = np.arange(0, len(seg) - 1, speed)
        seg = np.stack([np.interp(idx, np.arange(len(seg)), seg[:, c]) for c in range(2)], 1)
    return seg


def drone(dur, root=54.0, bright=0.0, seed=0):
    """Pad grave tipo cello/órgão afinado em A=432 (A1 = 54 Hz), com respiração lenta."""
    t = np.arange(int(dur * SR)) / SR
    rng = np.random.default_rng(seed)
    out = np.zeros((len(t), 2))
    for ratio, amp in ((1, 1.0), (1.5, 0.55), (2, 0.45), (3, 0.18 + 0.2 * bright), (4, 0.08 + 0.15 * bright)):
        for ch, det in ((0, 0.9985), (1, 1.0015)):
            f = root * ratio * det
            ph = rng.uniform(0, 6.28)
            sig = np.zeros_like(t)
            for k in range(1, 7):  # serrote suavizado (arco de cello)
                sig += np.sin(2 * np.pi * f * k * t + ph * k) / k ** 1.6
            out[:, ch] += sig * amp
    out = np.stack([A.lowpass(out[:, c], 700 + 900 * bright) for c in range(2)], 1)
    breath = 0.82 + 0.18 * np.sin(2 * np.pi * t / 7.3)
    out *= breath[:, None]
    return out / (np.max(np.abs(out)) + 1e-9)


def metal_hit(dur=6.0):
    """Nota longa de metal (tam-tam/sino) + impacto de sub-bass."""
    t = np.arange(int(dur * SR)) / SR
    f0 = 108.0
    bell = sum(a * np.sin(2 * np.pi * f0 * r * t) * np.exp(-t * d)
               for r, a, d in ((1, 1, 0.5), (2.76, 0.6, 0.7), (5.40, 0.35, 1.1), (8.93, 0.2, 1.8), (13.3, 0.1, 2.5)))
    shimmer = A.highpass(np.random.default_rng(3).normal(0, 1, len(t)), 3000) * np.exp(-t * 2.2) * 0.08
    f = 30 + 55 * np.exp(-t * 6)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.4) * 1.3
    y = bell * 0.5 + shimmer + sub
    y = A.reverb(y, 0.45, 1.8)
    return y / (np.max(np.abs(y)) + 1e-9)


def drum(gain=1.0):
    t = np.arange(int(2.2 * SR)) / SR
    f = 48 + 70 * np.exp(-t * 9)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.6)
    skin = A.lowpass(np.random.default_rng(5).normal(0, 1, len(t)), 700) * np.exp(-t * 18) * 0.5
    y = A.reverb(body + skin, 0.35, 1.6)
    return y / (np.max(np.abs(y)) + 1e-9) * gain


def hum(dur):
    t = np.arange(int(dur * SR)) / SR
    y = np.sin(2 * np.pi * 54 * t) + 0.5 * np.sin(2 * np.pi * 108 * t + 1) + 0.15 * np.sin(2 * np.pi * 162 * t + 2)
    return y / np.max(np.abs(y))


def fade(y, a, b):
    y = y.copy()
    na, nb = int(a * SR), int(b * SR)
    if na:
        y[:na] *= np.linspace(0, 1, na)[:, None] if y.ndim == 2 else np.linspace(0, 1, na)
    if nb:
        y[-nb:] *= np.linspace(1, 0, nb)[:, None] if y.ndim == 2 else np.linspace(1, 0, nb)
    return y


def build_audio():
    n = int(TOTAL * SR) + SR
    voice = np.zeros((n, 2))
    amb = np.zeros((n, 2))
    sfx = np.zeros((n, 2))
    # narração (tratada): 0–42,40 no lugar + sussurro final reposicionado
    nar_path = os.path.join(W_DIR, "narr_tratada.wav")
    A.polish_voice(os.path.join(W_DIR, "narracao.mp3"), nar_path,
                   "highpass=f=60,equalizer=f=3000:t=q:w=1.2:g=1.5,deesser=i=0.3,"
                   "acompressor=threshold=0.15:ratio=2:attack=10:release=150:makeup=1.2,alimiter=limit=0.95:level=disabled")
    nar = A.load_audio(nar_path)
    main = fade(nar[:int(42.40 * SR)], 0, 0.04)
    place(voice, main, 0.0)
    wh = fade(nar[int(WHISPER_SRC[0] * SR):int(WHISPER_SRC[1] * SR)], 0.03, 0.25)
    place(voice, wh, WHISPER_AT)
    v_ref = rms(main[np.abs(main) > 0.02])

    # áudio original dos clipes como ambiente (níveis relativos à voz)
    rel = {1: -24, 2: -27, 3: -24, 4: -19, 5: -15}
    for c, s0, s1, t0, t1, sp in SEGS:
        if c == 6 or sp == 0:
            continue
        seg = clip_audio(c, s0, s1, sp)[:int((t1 - t0) * SR)]
        g = db(rel[c]) * v_ref / rms(seg)
        place(amb, fade(seg, 0.02, 0.05), t0, g)
    # Jesus: voz do próprio clipe (sincronia labial), no nível da narração
    j = clip_audio(6, 0.0, 10.0, 1.0)
    jv = j.mean(1)
    jg = v_ref / rms(jv[np.abs(jv) > 0.02])
    place(voice, fade(j, 0.01, 0.4), 42.90, jg)

    # desenho sonoro original
    d1 = drone(25.6, bright=0.0, seed=1)
    d1 *= np.linspace(0.85, 1.15, len(d1))[:, None]  # cresce levemente até o arcanjo
    place(sfx, fade(d1, 1.5, 0.25), 0.0, db(-19.1) * v_ref / rms(d1))
    d2 = drone(42.40 - 25.35, root=54.0, bright=0.8, seed=2)
    place(sfx, fade(d2, 0.05, 0.02), 25.35, db(-23) * v_ref / rms(d2))
    mh = metal_hit(7.0)
    place(sfx, mh, 25.33, db(-6) * v_ref / rms(mh[:SR]))
    for k, (t, g) in enumerate(((34.11, 0.55), (36.67, 0.7), (38.62, 0.85), (40.71, 1.0))):
        dr = drum(g)
        place(sfx, dr, t - 0.02, db(-12) * v_ref / rms(drum(1.0)[:int(0.4 * SR)]))
    hm = hum(52.90 - 42.90)
    place(sfx, fade(hm, 0.6, 0.6), 42.90, db(-34) * v_ref / rms(hm))
    d3 = drone(TOTAL - 52.60, seed=3)
    place(sfx, fade(d3, 1.0, 1.4), 52.60, db(-28) * v_ref / rms(d3))

    mix = voice + amb + sfx
    a, b = int(CUT_SILENCE[0] * SR), int(CUT_SILENCE[1] * SR)
    mix[a:b] = 0.0  # corte seco: 0,5 s de silêncio absoluto
    mix = mix[:int(TOTAL * SR)]
    mix = fade(mix, 0.0, 0.6)
    pk = np.max(np.abs(mix))
    if pk > 0.98:
        mix = np.tanh(mix / pk * 1.15) / np.tanh(1.15) * 0.98
    A.write_wav(os.path.join(OUT, "mix_bruto.wav"), mix)
    for name, arr in (("stem_voz.wav", voice), ("stem_ambiente.wav", amb), ("stem_trilha.wav", sfx)):
        A.write_wav(os.path.join(OUT, name), np.clip(arr[:int(TOTAL * SR)], -1, 1))
    m = A.loudnorm_2pass(os.path.join(OUT, "mix_bruto.wav"), os.path.join(OUT, "mix.wav"), I=-14, TP=-1.5)
    print("loudness bruto:", m["input_i"], "LUFS -> -14")


# ---------------------------------------------------------------- legendas
def caption_sprite(text, color):
    size = 120
    f = ImageFont.truetype(FONT, size)
    lines = text.split("\n")
    pad = 40
    widths = [f.getlength(l) for l in lines]
    asc, desc = f.getmetrics()
    lh = int(size * 1.12)
    w, h = int(max(widths)) + 2 * pad, lh * len(lines) + 2 * pad
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # sombra dura + contorno escuro forte
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sh)
    for i, l in enumerate(lines):
        x = (w - widths[i]) / 2
        ds.text((x + 5, pad + i * lh + 7), l, font=f, fill=(0, 0, 0, 200))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3)))
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        x = (w - widths[i]) / 2
        d.text((x, pad + i * lh), l, font=f, fill=color, stroke_width=7, stroke_fill=(10, 8, 6, 255))
    if color != "#ffffff":  # brilho dourado discreto na virada de tom
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dg = ImageDraw.Draw(glow)
        for i, l in enumerate(lines):
            dg.text(((w - widths[i]) / 2, pad + i * lh), l, font=f, fill=(255, 200, 90, 150))
        img = Image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)), img)
    # condensação horizontal (serifada condensada)
    img = img.resize((int(w * 0.86), h), Image.LANCZOS)
    max_w = int(W * 0.86)
    if img.width > max_w:
        s = max_w / img.width
        img = img.resize((max_w, int(h * s)), Image.LANCZOS)
    return img


SPR = [caption_sprite(t, c) for t, _, _, c in CAPS]


def draw_caption(frame, T):
    for (text, t0, t1, col), spr in zip(CAPS, SPR):
        if t0 <= T < t1:
            p = min(1.0, (T - t0) / 0.28)
            e = 1 - (1 - p) ** 3
            sc = 1.07 - 0.07 * e if col == "#ffffff" else 1.16 - 0.16 * e
            alpha = e
            s = spr.resize((max(1, int(spr.width * sc)), max(1, int(spr.height * sc))), Image.BILINEAR) if sc != 1 else spr
            if alpha < 1:
                s = s.copy()
                s.putalpha(s.getchannel("A").point(lambda v: int(v * alpha)))
            cy = H * 0.695
            frame.alpha_composite(s, (int((W - s.width) / 2), int(cy - s.height / 2)))


# ---------------------------------------------------------------- vídeo
class Reader:
    def __init__(self, n):
        self.p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", CL(n), "-f", "rawvideo", "-pix_fmt", "rgb24",
                                   "-s", f"{W}x{H}", "-"], stdout=subprocess.PIPE)
        self.idx = -1
        self.cur = None

    def get(self, k):
        while self.idx < k:
            raw = self.p.stdout.read(W * H * 3)
            if len(raw) < W * H * 3:
                break
            self.cur = raw
            self.idx += 1
        return Image.frombytes("RGB", (W, H), self.cur)

    def close(self):
        self.p.stdout.close()
        self.p.kill()


def render(preview_png=None):
    if preview_png is None:
        build_audio()
    out_mp4 = os.path.join(OUT, "vade-retro-final.mp4")
    if preview_png is None:
        enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", str(FPS), "-i", "-", "-i", os.path.join(OUT, "mix.wav"), "-map", "0:v", "-map", "1:a",
                                "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                                "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
                                out_mp4], stdin=subprocess.PIPE)
    nframes = int(round(TOTAL * FPS))
    times = [preview_png] if preview_png is not None else [i / FPS for i in range(nframes)]
    readers = {}
    for T in times:
        seg = next(s for s in SEGS if s[3] <= T + 1e-6 < s[4]) if T < SEGS[-1][4] else SEGS[-1]
        c, s0, s1, t0, t1, sp = seg
        key = (c, s0, t0)
        if key not in readers:
            for r in readers.values():
                r.close()
            readers = {key: Reader(c)}
        src = s0 if sp == 0 else min(s1 - 1e-3, s0 + (T - t0) * sp)
        fr = readers[key].get(int(src * FPS)).convert("RGBA")
        if seg == SEGS[-1]:  # aproximação lenta no quadro final + escurecimento
            p = (T - t0) / (t1 - t0)
            z = 1 + 0.045 * (p * p * (3 - 2 * p))
            cw, ch = W / z, H / z
            fr = fr.resize((W, H), Image.BICUBIC, box=((W - cw) / 2, (H - ch) * 0.42, (W + cw) / 2, (H - ch) * 0.42 + ch))
        if 25.35 <= T < 25.60:  # clarão curto na entrada do arcanjo
            a = 0.55 * (1 - (T - 25.35) / 0.25)
            fr = Image.blend(fr, Image.new("RGBA", (W, H), (255, 250, 235, 255)), a)
        draw_caption(fr, T)
        if T > TOTAL - 0.6:
            fr = Image.blend(fr, Image.new("RGBA", (W, H), (0, 0, 0, 255)), (T - (TOTAL - 0.6)) / 0.6)
        if preview_png is not None:
            fr.convert("RGB").save(os.path.join(OUT, f"quadro_{T:.2f}.png"))
        else:
            enc.stdin.write(fr.convert("RGB").tobytes())
    for r in readers.values():
        r.close()
    if preview_png is None:
        enc.stdin.close()
        enc.wait()
        print("ok", out_mp4)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for t in sys.argv[1:]:
            render(float(t))
    else:
        render()
