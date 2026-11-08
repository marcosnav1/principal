"""Áudio: leitura/escrita, trilha sonora procedural, efeitos sonoros, ducking e mixagem.

Tudo é gerado com numpy (sem samples externos, sem direitos autorais), mas também
aceita arquivos do usuário (trilha em mp3/wav e efeitos personalizados).
"""
from __future__ import annotations

import glob
import json
import math
import os
import subprocess
import wave

import numpy as np

SR = 48000
RNG = np.random.default_rng(7)


# ------------------------------------------------------------------ I/O
def load_audio(path: str, channels: int = 1) -> np.ndarray:
    """Decodifica qualquer formato via ffmpeg. channels=2 devolve array (n, 2)."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", str(channels),
                          "-ar", str(SR), "-"], check=True, capture_output=True).stdout
    y = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    return y.reshape(-1, 2) if channels == 2 else y


def write_wav(path: str, y: np.ndarray) -> None:
    """WAV 24 bits (mono ou estéreo) - sem perda de qualidade nos intermediários."""
    y = np.clip(y, -1, 1)
    ch = 1 if y.ndim == 1 else y.shape[1]
    pcm = (y.reshape(-1) * 8388607).astype("<i4")
    data = np.frombuffer(pcm.tobytes(), dtype=np.uint8).reshape(-1, 4)[:, :3].tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(3)
        w.setframerate(SR)
        w.writeframes(data)


def to_stereo(y: np.ndarray, width_ms: float = 0.0) -> np.ndarray:
    """Mono -> estéreo. width_ms > 0 atrasa levemente o canal direito (efeito Haas = abertura)."""
    if y.ndim == 2:
        return y
    if width_ms <= 0:
        return np.stack([y, y], axis=1)
    d = int(width_ms / 1000 * SR)
    r = np.concatenate([np.zeros(d), y[:-d]]) if d else y
    return np.stack([y * 0.97 + r * 0.03, r * 0.97 + y * 0.03], axis=1)


# ------------------------------------------------------------------ tratamento de voz
VOICE_CHAIN = {
    # TTS já sai limpo: só EQ de presença, de-esser, compressão suave e limitador
    "tts": ("highpass=f=70,equalizer=f=180:t=q:w=1.2:g=1.5,equalizer=f=320:t=q:w=1.0:g=-2,"
            "equalizer=f=3200:t=q:w=1.3:g=2,equalizer=f=11000:t=q:w=0.9:g=1.5,deesser=i=0.35,"
            "acompressor=threshold=0.125:ratio=2.5:attack=8:release=140:knee=4:makeup=1.4,"
            "alimiter=limit=0.94:level=disabled"),
    # gravação do usuário: + redução de ruído, corte de graves de ambiente e compressão mais firme
    "gravacao": ("highpass=f=85,afftdn=nr=14:nf=-32:tn=1,anlmdn=s=4,equalizer=f=200:t=q:w=1.2:g=1,"
                 "equalizer=f=350:t=q:w=1.0:g=-3,equalizer=f=3000:t=q:w=1.3:g=2.5,"
                 "equalizer=f=10000:t=q:w=0.9:g=2,deesser=i=0.45,"
                 "acompressor=threshold=0.1:ratio=3.5:attack=6:release=120:knee=4:makeup=1.8,"
                 "alimiter=limit=0.94:level=disabled"),
    "nenhum": "anull",
}


def polish_voice(src: str, dst: str, preset: str = "tts") -> None:
    """Aplica a cadeia de voz (EQ, de-esser, compressor, limitador) com ffmpeg."""
    chain = VOICE_CHAIN.get(preset, preset)  # aceita preset ou cadeia ffmpeg personalizada
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", chain, "-ac", "1",
                    "-ar", str(SR), "-c:a", "pcm_s24le", dst], check=True)


def loudnorm_2pass(src: str, dst: str, I: float = -14.0, TP: float = -1.5, LRA: float = 11.0) -> dict:
    """Normalização EBU R128 em duas passadas (precisa, sem 'bombeamento')."""
    flt = f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json"
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", flt, "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    flt2 = (f"loudnorm=I={I}:TP={TP}:LRA={LRA}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
            "linear=true")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", flt2, "-ar", str(SR),
                    "-c:a", "pcm_s24le", dst], check=True)
    return m


def add_at(buf: np.ndarray, sig: np.ndarray, t: float, gain: float = 1.0) -> None:
    i = int(max(0.0, t) * SR)
    if i >= len(buf):
        return
    n = min(len(sig), len(buf) - i)
    buf[i:i + n] += sig[:n] * gain


def smooth(x: np.ndarray, win_s: float) -> np.ndarray:
    k = max(1, int(win_s * SR))
    c = np.cumsum(np.concatenate([[0.0], x]))
    y = (c[k:] - c[:-k]) / k
    pad_l = k // 2
    return np.concatenate([np.full(pad_l, y[0] if len(y) else 0), y,
                           np.full(len(x) - len(y) - pad_l, y[-1] if len(y) else 0)])


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """Passa-baixas suave via FFT (sem scipy)."""
    if len(x) < 8:
        return x
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / np.sqrt(1 + (f / cutoff) ** 4)
    return np.fft.irfft(X, n=len(x))


def highpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    return x - lowpass(x, cutoff)


def reverb(x: np.ndarray, mix: float = 0.25, size: float = 1.0) -> np.ndarray:
    """Reverb barato: taps de eco esparsos com decaimento + suavização."""
    out = x.copy()
    taps = [(0.029, 0.55), (0.043, 0.5), (0.061, 0.42), (0.089, 0.36), (0.127, 0.3),
            (0.173, 0.24), (0.229, 0.18), (0.311, 0.12), (0.419, 0.08), (0.557, 0.05)]
    wet = np.zeros(len(x) + int(0.6 * size * SR) + 1)
    for d, g in taps:
        i = int(d * size * SR)
        wet[i:i + len(x)] += x * g
    wet = lowpass(wet, 5000)[:len(x)]
    return out + wet * mix


def fade(y: np.ndarray, fin: float = 0.01, fout: float = 0.05) -> np.ndarray:
    y = y.copy()
    a, b = int(fin * SR), int(fout * SR)
    sh = (-1, 1) if y.ndim == 2 else (-1,)
    if a:
        y[:a] *= np.linspace(0, 1, a).reshape(sh)
    if b:
        y[-b:] *= np.linspace(1, 0, b).reshape(sh)
    return y


# ------------------------------------------------------------------ instrumentos
def mfreq(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def pad(f, dur, release=0.8):
    t = _t(dur + release)
    y = np.zeros_like(t)
    for det in (0.996, 1.0, 1.004):
        for k in range(1, 7):
            y += np.sin(2 * np.pi * f * det * k * t + k) / k ** 1.3
    env = np.minimum(1, t / 0.45) * np.where(t > dur, np.exp(-(t - dur) / (release / 3)), 1)
    return y * env / 6


def pluck(f, dur=0.9, bright=1.0):
    t = _t(dur)
    y = np.zeros_like(t)
    for k in range(1, 9):
        y += np.sin(2 * np.pi * f * k * t) * np.exp(-t * (3 + k * 1.8 / bright)) / k
    return fade(y * np.minimum(1, t / 0.004), 0, 0.05) / 2


def bass(f, dur):
    t = _t(dur)
    y = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
    env = np.minimum(1, t / 0.008) * np.exp(-t * 1.2)
    return fade(y * env, 0, 0.03) * 0.8


def kick(gain=1.0):
    t = _t(0.45)
    f = 45 + 95 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) * np.exp(-t * 7) + RNG.normal(0, 1, len(t)) * np.exp(-t * 300) * 0.15
    return y * gain


def snare(gain=1.0):
    t = _t(0.25)
    n = highpass(RNG.normal(0, 1, len(t)), 1200) * np.exp(-t * 18)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return (n * 0.55 + tone * 0.5) * gain


def clap(gain=1.0):
    t = _t(0.22)
    n = highpass(RNG.normal(0, 1, len(t)), 900)
    env = sum(np.exp(-np.maximum(0, t - d) * 60) * (t >= d) for d in (0, 0.01, 0.022))
    return n * env * 0.35 * gain


def hat(gain=1.0, open_=False):
    t = _t(0.25 if open_ else 0.06)
    n = highpass(RNG.normal(0, 1, len(t)), 7000)
    return n * np.exp(-t * (14 if open_ else 70)) * 0.35 * gain


def tom(gain=1.0, base=70):
    t = _t(0.9)
    f = base + 60 * np.exp(-t * 12)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4)
    y += lowpass(RNG.normal(0, 1, len(t)), 900) * np.exp(-t * 12) * 0.4
    return y * gain


def crash(gain=1.0):
    t = _t(2.2)
    return highpass(RNG.normal(0, 1, len(t)), 4000) * np.exp(-t * 2.2) * 0.25 * gain


# ------------------------------------------------------------------ trilha procedural
# acordes como semitons relativos à tônica (C)
MOODS = {
    "upbeat": dict(bpm=114, prog=[[0, 4, 7], [7, 11, 14], [9, 12, 16], [5, 9, 12]], drums="pop",
                   arp=4, pad=0.22, pluck=0.20, bass=0.45, bpc=1),
    "corporate": dict(bpm=100, prog=[[0, 4, 7], [9, 12, 16], [5, 9, 12], [7, 11, 14]], drums="corp",
                      arp=4, pad=0.2, pluck=0.24, bass=0.38, bpc=1),
    "calm": dict(bpm=78, prog=[[5, 9, 12, 16], [4, 7, 11, 14], [2, 5, 9, 12], [0, 4, 7, 11]], drums="soft",
                 arp=2, pad=0.3, pluck=0.18, bass=0.32, bpc=1),
    "epic": dict(bpm=88, prog=[[9, 12, 16], [5, 9, 12], [0, 4, 7], [7, 11, 14]], drums="epic",
                 arp=0, pad=0.42, pluck=0.12, bass=0.5, bpc=1),
    "tense": dict(bpm=96, prog=[[9, 12, 16], [9, 12, 16], [10, 14, 17], [8, 12, 15]], drums="tense",
                  arp=2, pad=0.3, pluck=0.14, bass=0.45, bpc=1),
    "happy": dict(bpm=124, prog=[[0, 4, 7], [5, 9, 12], [7, 11, 14], [5, 9, 12]], drums="pop",
                  arp=4, pad=0.18, pluck=0.24, bass=0.42, bpc=1),
}
MOODS["lofi"] = MOODS["calm"]
MOODS["inspiring"] = MOODS["corporate"]
MOODS["dramatic"] = MOODS["epic"]
MOODS["suspense"] = MOODS["tense"]

DRUMS = {  # passos de 16 avos em um compasso
    "pop": dict(kick=[0, 8, 10], snare=[4, 12], hat=[0, 2, 4, 6, 8, 10, 12, 14], ohat=[14]),
    "corp": dict(kick=[0, 8], clap=[4, 12], hat=[2, 6, 10, 14], shaker=list(range(16))),
    "soft": dict(kick=[0, 10], snare=[8], hat=[0, 4, 8, 12], swing=True),
    "epic": dict(tom=[0, 3, 6, 8, 12], kick=[0, 8], crash_every=4),
    "tense": dict(kick=[0, 3], hat=list(range(0, 16, 2))),
}


def synth_music(duration: float, mood: str = "upbeat", bpm: float | None = None, seed: int = 0) -> np.ndarray:
    cfg = MOODS.get(mood, MOODS["upbeat"])
    rng = np.random.default_rng(seed)
    bpm = bpm or cfg["bpm"]
    beat = 60 / bpm
    bar = beat * 4
    step = beat / 4
    key = 57 + int(rng.integers(0, 6))  # A3..D4 - varia a tonalidade por vídeo
    n_bars = int(math.ceil(duration / bar)) + 1
    buf = np.zeros(int((n_bars * bar + 3) * SR))
    lay_pad, lay_pl, lay_bs, lay_dr = (np.zeros_like(buf) for _ in range(4))
    dr = DRUMS[cfg["drums"]]
    K, S, C, H, OH, T1, T2, CR = kick(), snare(), clap(), hat(), hat(open_=True), tom(base=60), tom(base=75), crash()
    cache = {}

    def cached(fn, *args):
        k = (fn.__name__, *args)
        if k not in cache:
            cache[k] = fn(*args)
        return cache[k]
    for b in range(n_bars):
        chord = cfg["prog"][(b // cfg["bpc"]) % len(cfg["prog"])]
        root_shift = -12 if chord[0] >= 7 else 0
        notes = [key + n + root_shift for n in chord]
        t0 = b * bar
        for m in notes:
            add_at(lay_pad, cached(pad, mfreq(m), bar), t0, cfg["pad"])
        # baixo
        bass_m = key - 12 + chord[0] + root_shift
        pattern = [0, 2.5] if cfg["drums"] in ("epic", "soft") else [0, 1.5, 2, 3, 3.5]
        for p in pattern:
            add_at(lay_bs, cached(bass, mfreq(bass_m), beat * 0.9), t0 + p * beat, cfg["bass"])
        # arpejo
        if cfg["arp"]:
            seq = notes + [notes[0] + 12, notes[1] + 12]
            per_bar = cfg["arp"] * 4
            order = [0, 1, 2, 3, 4, 3, 2, 1] if rng.random() < 0.5 else [0, 2, 1, 3, 2, 4, 3, 1]
            for i in range(per_bar):
                if b == 0 and i < per_bar // 2:
                    continue
                m = seq[order[i % len(order)] % len(seq)] + 12
                vel = 1.0 if i % 4 == 0 else 0.7
                add_at(lay_pl, cached(pluck, mfreq(m), 0.7), t0 + i * bar / per_bar, cfg["pluck"] * vel)
        # bateria (sem bateria nos 2 primeiros compassos = intro)
        if b < 2 and n_bars > 4:
            continue
        for s in range(16):
            tt = t0 + s * step + (step * 0.33 if dr.get("swing") and s % 2 else 0)
            if s in dr.get("kick", []):
                add_at(lay_dr, K, tt, 0.9)
            if s in dr.get("snare", []):
                add_at(lay_dr, S, tt, 0.5 if cfg["drums"] == "soft" else 0.7)
            if s in dr.get("clap", []):
                add_at(lay_dr, C, tt, 0.8)
            if s in dr.get("hat", []):
                add_at(lay_dr, H, tt, 0.5 if s % 4 else 0.7)
            if s in dr.get("ohat", []):
                add_at(lay_dr, OH, tt, 0.35)
            if s in dr.get("shaker", []):
                add_at(lay_dr, H, tt, 0.18)
            if s in dr.get("tom", []):
                add_at(lay_dr, T1 if s == 0 else T2, tt, 0.9 if s in (0, 8) else 0.6)
        if dr.get("crash_every") and b % dr["crash_every"] == 2:
            add_at(lay_dr, CR, t0, 0.7)
    mix = (reverb(lay_pad, 0.35, 1.4) + reverb(lay_pl, 0.3) + lay_bs + reverb(lay_dr, 0.12, 0.6))
    mix = lowpass(mix, 9000)
    mix = mix[:int(duration * SR)]
    mix /= (np.max(np.abs(mix)) + 1e-9)
    return fade(mix * 0.9, 1.0, min(3.0, duration / 4))


def music_from_file(path: str, duration: float, start: float = 0.0) -> np.ndarray:
    """Trilha do usuário em estéreo; repete com crossfade de 2 s se for mais curta que o vídeo."""
    y = load_audio(path, channels=2)[int(start * SR):]
    n = int(duration * SR)
    if len(y) == 0:
        return np.zeros((n, 2))
    xf = min(int(2 * SR), len(y) // 4)
    out = y.copy()
    while len(out) < n:
        ramp = np.linspace(0, 1, xf)[:, None]
        out = np.concatenate([out[:-xf], out[-xf:] * (1 - ramp) + y[:xf] * ramp, y[xf:]])
    out = out[:n]
    out /= (np.max(np.abs(out)) + 1e-9)
    return fade(out * 0.9, 0.3, min(3.0, duration / 4))


AUDIO_EXT = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac")


def find_music(lib_dir: str, mood: str, seed: int = 0) -> str | None:
    """Procura trilha em <lib>/<mood>/*.mp3, depois <lib>/*<mood>*.mp3, depois qualquer uma em <lib>."""
    if not lib_dir or not os.path.isdir(lib_dir):
        return None
    pools = [glob.glob(os.path.join(lib_dir, mood, "*")),
             [p for p in glob.glob(os.path.join(lib_dir, "*")) if mood.lower() in os.path.basename(p).lower()],
             glob.glob(os.path.join(lib_dir, "*"))]
    for pool in pools:
        files = sorted(p for p in pool if p.lower().endswith(AUDIO_EXT))
        if files:
            return files[seed % len(files)]
    return None


# ------------------------------------------------------------------ efeitos sonoros
def sfx(name: str) -> np.ndarray:
    n = name.lower()
    if n in ("whoosh", "swoosh", "transition"):
        dur = 0.55 if n == "whoosh" else 0.35
        t = _t(dur)
        noise = RNG.normal(0, 1, len(t))
        env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2.2
        bright = lowpass(noise, 2500) * env + highpass(noise, 3000) * env ** 3 * 0.25
        return reverb(fade(bright, 0.01, 0.05), 0.2) * 0.9
    if n == "pop":
        t = _t(0.12)
        f = 300 + 700 * np.exp(-t * 45)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35) * 0.8
    if n == "click":
        t = _t(0.04)
        return (np.sin(2 * np.pi * 3200 * t) * 0.5 + RNG.normal(0, 0.4, len(t))) * np.exp(-t * 180) * 0.6
    if n in ("ding", "bell"):
        t = _t(1.6)
        y = sum(a * np.sin(2 * np.pi * 1320 * r * t) * np.exp(-t * d)
                for r, a, d in ((1, 1, 2.5), (2.0, 0.4, 4), (2.76, 0.3, 5), (5.4, 0.15, 8)))
        return reverb(y * 0.35, 0.3)
    if n in ("success", "chime"):
        y = np.zeros(int(1.8 * SR))
        for i, m in enumerate((76, 83, 88)):
            t = _t(1.4)
            add_at(y, np.sin(2 * np.pi * mfreq(m) * t) * np.exp(-t * 3) * 0.35, i * 0.09)
        return reverb(y, 0.35)
    if n in ("coin", "cash"):
        y = np.zeros(int(0.8 * SR))
        for i, f in enumerate((1976, 2637)):
            t = _t(0.6)
            add_at(y, np.sign(np.sin(2 * np.pi * f * t)) * np.exp(-t * 9) * 0.18, i * 0.07)
        return lowpass(y, 7000)
    if n in ("impact", "boom", "hit"):
        t = _t(1.4)
        f = 32 + 80 * np.exp(-t * 14)
        y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.5)
        y += lowpass(RNG.normal(0, 1, len(t)), 1500) * np.exp(-t * 14) * 0.6
        return reverb(y, 0.35, 1.5) * 0.9
    if n == "riser":
        dur = 1.5
        t = _t(dur)
        f = 200 + 1400 * (t / dur) ** 2
        y = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25 + highpass(RNG.normal(0, 1, len(t)), 2000) * 0.25
        return fade(y * (t / dur) ** 2, 0.05, 0.02)
    if n == "glitch":
        y = np.zeros(int(0.35 * SR))
        for i in range(7):
            t = _t(0.03)
            f = float(RNG.uniform(200, 2000))
            add_at(y, np.sign(np.sin(2 * np.pi * f * t)) * 0.25, i * 0.045)
        return y
    if n == "typing":
        y = np.zeros(int(1.2 * SR))
        tt = 0.0
        while tt < 1.1:
            add_at(y, sfx("click"), tt, float(RNG.uniform(0.4, 0.9)))
            tt += float(RNG.uniform(0.06, 0.13))
        return y
    if n == "notification":
        y = np.zeros(int(0.9 * SR))
        for i, m in enumerate((84, 88)):
            t = _t(0.5)
            add_at(y, np.sin(2 * np.pi * mfreq(m) * t) * np.exp(-t * 7) * 0.4, i * 0.12)
        return y
    raise KeyError(name)


SFX_NAMES = ["whoosh", "swoosh", "pop", "click", "ding", "success", "coin", "impact", "riser",
             "glitch", "typing", "notification"]


_SFX_CACHE: dict = {}


def load_sfx(name_or_path: str, lib_dirs=()) -> np.ndarray:
    """Prioridade: arquivo da biblioteca do usuário (sfx/<nome>.wav|mp3) > caminho direto > sintetizado."""
    key = (name_or_path, tuple(lib_dirs))
    if key in _SFX_CACHE:
        return _SFX_CACHE[key]
    y = None
    for d in lib_dirs:
        for ext in AUDIO_EXT:
            p = os.path.join(d, name_or_path + ext)
            if os.path.isfile(p):
                y = load_audio(p)
                break
        if y is not None:
            break
    if y is None and os.path.isfile(name_or_path):
        y = load_audio(name_or_path)
    if y is not None:
        y = y / (np.max(np.abs(y)) + 1e-9) * 0.8
    else:
        y = sfx(name_or_path)
    _SFX_CACHE[key] = y
    return y


# ------------------------------------------------------------------ mixagem
def duck_gain(voice: np.ndarray, base: float, depth: float = 0.65) -> np.ndarray:
    env = smooth(np.abs(voice), 0.05)
    active = (env > 0.015).astype(float)
    mask = np.clip(smooth(active, 0.5) * 1.6, 0, 1)
    return base * (1 - depth * mask)


def master(voice, music, effects, music_volume=0.22, sfx_volume=0.6, duck=0.65):
    """Mixagem estéreo: voz e efeitos no centro, música estéreo com ducking pela voz."""
    n = max(len(voice), len(music), len(effects))

    def fit(a):
        a = to_stereo(a)
        return np.pad(a, ((0, n - len(a)), (0, 0)))

    v, m, e = fit(voice), fit(music), fit(effects)
    g = duck_gain(np.pad(voice, (0, n - len(voice))), music_volume, duck)[:, None]
    mix = v + m * g + e * sfx_volume
    peak = np.max(np.abs(mix)) + 1e-9
    if peak > 0.98:
        mix = np.tanh(mix / peak * 1.2) / np.tanh(1.2) * 0.98
    return mix
