#!/usr/bin/env python3
"""Produção de vídeo completa a partir de um roteiro JSON.

    python produce.py roteiro.json -o saida/video.mp4
    python produce.py roteiro.json --preview            # meia resolução, render rápido
    python produce.py roteiro.json --still 4.2          # salva só um quadro PNG em t=4.2s
    python produce.py roteiro.json --format 9:16,16:9   # várias proporções de uma vez

Pipeline: narração (TTS) -> linha do tempo -> legendas sincronizadas -> trilha sonora
-> efeitos sonoros -> mixagem com ducking -> animação quadro a quadro -> MP4 (H.264/AAC,
loudness -14 LUFS) + .srt + thumbnail.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audio as A  # noqa: E402
import tts as T  # noqa: E402
import visuals as V  # noqa: E402

DEFAULT_THEME = {
    "palette": ["#0f172a", "#312e81", "#facc15"],  # fundo 1, fundo 2, destaque
    "text_color": None,                              # auto (branco/preto pelo contraste)
    "font": "Inter",
    "background": "particles",
    "transition": "fade",
    "subtitle_style": "karaoke",                     # karaoke | stroke | box | none
    "progress_bar": True,
    "handle": None,
    "logo": None,
}
BG_CYCLE = ["particles", "waves", "bokeh", "grid"]


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ legendas
def estimate_words(text, dur):
    toks = text.split()
    if not toks:
        return []
    wts = [len(re.sub(r"\W", "", w)) + 2 for w in toks]
    pauses = [0.32 if w[-1] in ",;:" else 0.45 if w[-1] in ".!?" else 0.0 for w in toks]
    pauses[-1] = 0
    total_p = sum(pauses)
    if total_p > dur * 0.3:
        pauses = [p * dur * 0.3 / total_p for p in pauses]
        total_p = dur * 0.3
    speech = max(0.2, dur - total_p - 0.1)
    out, t = [], 0.05
    for w, wt, p in zip(toks, wts, pauses):
        d = speech * wt / sum(wts)
        out.append((w, t, t + d))
        t += d + p
    return out


def clean_word(w):
    w = w.strip()
    return re.sub(r"[,.;:]+$", "", w) or w


def chunk_words(words, max_words, max_chars):
    chunks, cur = [], []
    for i, (w, s, e) in enumerate(words):
        cur.append((clean_word(w), s, e))
        nxt = words[i + 1] if i + 1 < len(words) else None
        chars = sum(len(x[0]) + 1 for x in cur)
        brk = (nxt is None or len(cur) >= max_words or chars + len(nxt[0]) > max_chars
               or nxt[1] - e > 0.22 or w.rstrip()[-1:] in ".!?,;:")
        if brk:
            chunks.append(cur)
            cur = []
    return chunks


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


# ------------------------------------------------------------------ cenas
class Scene:
    pass


def build_scene(sc, idx, theme, W, H, subs_on, base_dir):
    """Monta os elementos da cena e calcula o layout vertical."""
    pal = sc.get("colors") or theme["palette"][:2]
    accent = sc.get("accent") or theme.get("accent") or theme["palette"][-1]
    bg_lum = np.mean([V.luminance(V.hex2rgb(c)) for c in pal])
    text_color = sc.get("text_color") or theme.get("text_color") or ("#111111" if bg_lum > 0.6 else "#ffffff")
    fb = V.find_font(theme["font"], "black")
    fbold = V.find_font(theme["font"], "bold")
    freg = V.find_font(theme.get("body_font") or theme["font"], "regular")
    fit = V.find_font(theme["font"], "italic")
    vertical = H > W
    u = min(W, H)
    cw = W * (0.84 if vertical else 0.78)
    left = (W - cw) / 2
    top = H * (0.10 if vertical else 0.08)
    bottom = H * ((0.70 if vertical else 0.78) if subs_on else (0.90 if vertical else 0.92))
    area = bottom - top

    image = sc.get("image")
    if image and not os.path.isabs(image):
        image = os.path.join(base_dir, image)
    img_mode = sc.get("image_mode", "background")
    bg_kind = sc.get("background") or theme["background"]
    if bg_kind == "auto":
        bg_kind = BG_CYCLE[idx % len(BG_CYCLE)]
    if image and img_mode == "background":
        bg_kind = "image"

    v0, vdur = sc["_voice_start"], sc["_voice_dur"]
    first_anim = 0.25 if idx == 0 else 0.35

    def build(f):
        els = []
        t = first_anim
        title_anim = sc.get("title_anim") or ("pop" if idx == 0 or sc.get("type") in ("title", "cta") else "up")
        if sc.get("kicker"):
            e = V.PillEl(sc["kicker"].upper(), fbold, u * 0.032 * f, "#111111" if V.luminance(V.hex2rgb(accent)) > 0.55
                         else "#ffffff", accent, anim="pop")
            e.appear = t; t += 0.2
            els.append(e)
        if image and img_mode == "card":
            e = V.ImageCardEl(image, cw, area * 0.45 * f, radius=int(u * 0.035))
            e.appear = t; t += 0.3
            els.append(e)
        if sc.get("stat") is not None:
            st = sc["stat"] if isinstance(sc["stat"], dict) else {"value": sc["stat"]}
            e = V.StatEl(st["value"], fb, u * 0.2 * f, text_color, accent, st.get("prefix", ""),
                         st.get("suffix", ""), st.get("decimals"))
            e.appear = t; e.sfx = st.get("sfx", "impact"); t += 0.45
            els.append(e)
        if sc.get("title"):
            size = u * (0.105 if sc.get("type") == "title" or idx == 0 else 0.088) * f
            e = V.TextEl(sc["title"], fb, size, text_color, accent, cw, anim=title_anim, max_lines=4)
            e.appear = t; t += 0.35
            els.append(e)
        if sc.get("text"):
            e = V.TextEl(sc["text"], freg if sc.get("text_weight") == "regular" else fbold, u * 0.062 * f,
                         text_color, accent, cw, anim=sc.get("text_anim", "words"), max_lines=7)
            e.appear = t; t += min(1.2, e.anim_dur * 0.6)
            els.append(e)
        if sc.get("quote"):
            q = V.TextEl("“" + sc["quote"] + "”", fit, u * 0.07 * f, text_color, accent, cw,
                         anim=sc.get("text_anim", "words"), max_lines=7)
            q.appear = t; t += q.anim_dur * 0.7
            els.append(q)
            if sc.get("author"):
                a = V.TextEl("— " + sc["author"], fbold, u * 0.04 * f, accent, accent, cw, anim="up")
                a.appear = t; t += 0.3
                els.append(a)
        if sc.get("bullets"):
            items = sc["bullets"]
            n = len(items)
            start = max(t, v0 + 0.3)
            span = (vdur * 0.8 if vdur else 0.6 * n)
            times = sc.get("bullet_times") or [start + i * span / max(1, n) for i in range(n)]
            e = V.BulletsEl(items, fbold, u * 0.058 * f, text_color, accent, cw, times,
                            style=sc.get("bullet_style", "check"))
            e.appear = times[0]
            e.sfx_times = times
            t = times[-1] + 0.3
            els.append(e)
        if sc.get("button"):
            ink = "#111111" if V.luminance(V.hex2rgb(accent)) > 0.55 else "#ffffff"
            e = V.PillEl(sc["button"], fb, u * 0.048 * f, ink, accent, pulse=True, anim="pop")
            e.appear = max(t, 0.6); e.sfx = "ding"
            els.append(e)
        return els

    f = 1.0
    for _ in range(7):
        els = build(f)
        gap = u * 0.035 * f
        total = sum(e.height for e in els) + gap * max(0, len(els) - 1)
        if total <= area:
            break
        f *= 0.88
    y = top + (area - total) / 2
    if bg_kind == "image" and not any(isinstance(e, V.ImageCardEl) for e in els):
        y = top + (area - total) * 0.85  # texto mais embaixo sobre fotos
    pos = []
    for e in els:
        e.cw = cw
        pos.append((left, y))
        y += e.height + gap
    s = Scene()
    s.bg = V.Background(bg_kind, W, H, pal + ([sc["colors"][2]] if sc.get("colors") and len(sc["colors"]) > 2 else []),
                        accent, image=image, seed=idx * 7 + 3, motion=sc.get("image_motion", "zoom_in"))
    s.items = list(zip(els, pos))
    s.accent = accent
    return s


def render_scene(s, t, gt):
    frame = s.bg.render(t, gt)
    for e, (x, y) in s.items:
        e.draw(frame, x, y, t)
    return frame


def transition(prev, cur, kind, p, W, H):
    e = V.ease_in_out(p)
    if kind == "slide":
        out = Image.new("RGBA", (W, H))
        out.paste(prev, (int(-e * W), 0))
        out.paste(cur, (int(W - e * W), 0))
        return out
    if kind == "slide_up":
        out = Image.new("RGBA", (W, H))
        out.paste(prev, (0, int(-e * H)))
        out.paste(cur, (0, int(H - e * H)))
        return out
    if kind == "zoom":
        z = 1 + 0.35 * e
        pz = prev.resize((int(W * z), int(H * z)), Image.BILINEAR)
        pz = pz.crop(((pz.width - W) // 2, (pz.height - H) // 2, (pz.width - W) // 2 + W, (pz.height - H) // 2 + H))
        return Image.blend(pz, cur, e)
    if kind == "wipe":
        out = prev.copy()
        x = int(e * W)
        if x > 0:
            out.paste(cur.crop((0, 0, x, H)), (0, 0))
        return out
    if kind == "flash":
        white = Image.new("RGBA", (W, H), (255, 255, 255, 255))
        return Image.blend(prev, white, p * 2) if p < 0.5 else Image.blend(white, cur, (p - 0.5) * 2)
    if kind == "none":
        return cur
    return Image.blend(prev, cur, e)


# ------------------------------------------------------------------ principal
def produce(sb, base_dir, out_path, fmt, preview=False, still=None, engine=None, no_subs=False, log=log):
    t_start = time.time()
    W, H = V.FORMATS[fmt]
    if preview:
        W, H = W // 2, H // 2
    fps = int(sb.get("fps", 30 if not preview else 24))
    theme = {**DEFAULT_THEME, **sb.get("theme", {})}
    vcfg = {"engine": "auto", "voice": T.DEFAULT_VOICE, "rate": "+0%", "pitch": "+0Hz", **sb.get("voice", {})}
    if engine:
        vcfg["engine"] = engine
    scenes = sb["scenes"]
    work = os.path.splitext(out_path)[0] + "_work"
    os.makedirs(work, exist_ok=True)
    cache = os.path.join(os.path.dirname(os.path.abspath(out_path)), ".tts_cache")
    subs_style = "none" if no_subs or sb.get("subtitles") is False else theme["subtitle_style"]
    subs_on = subs_style != "none"

    # 1) narração
    log(f"▶ Narração ({vcfg['engine']}, {vcfg['voice']})")
    used = set()
    for i, sc in enumerate(scenes):
        nar = V.strip_marks(sc.get("narration", "")).strip()
        sc["_wav"], sc["_voice_dur"], sc["_words"] = None, 0.0, None
        if not nar:
            continue
        vc = {**vcfg, **(sc.get("voice") or {})}
        wav, d, words, eng = T.synthesize(nar, cache, vc["engine"], vc["voice"], vc.get("rate"), vc.get("pitch"))
        used.add(eng)
        sc["_wav"], sc["_voice_dur"] = wav, d
        sc["_words"] = words if words else estimate_words(nar, d)
        log(f"  cena {i + 1}: {d:.1f}s [{eng}]")
    if "espeak" in used:
        log("  ⚠ usando espeak (voz robótica). Instale/conecte edge-tts para vozes neurais.")

    # 2) linha do tempo
    t0 = 0.0
    for i, sc in enumerate(scenes):
        lead = sc.get("voice_delay", 0.45 if i == 0 else 0.3)
        tail = sc.get("pause", 0.55)
        need = lead + sc["_voice_dur"] + tail if sc["_wav"] else 0
        if sc.get("bullets") and not sc["_wav"]:
            need = 1.0 + 0.7 * len(sc["bullets"])
        sc["_start"], sc["_voice_start"] = t0, lead if sc["_wav"] else 0.0
        sc["_dur"] = max(float(sc.get("duration", 0) or 0), need, 1.5 if sc["_wav"] else 3.0)
        t0 += sc["_dur"]
    total = t0 + float(sb.get("end_pad", 0.4))
    log(f"▶ Duração total: {total:.1f}s em {len(scenes)} cenas")

    # 3) cenas visuais
    scene_objs = [build_scene(sc, i, theme, W, H, subs_on, base_dir) for i, sc in enumerate(scenes)]

    # 4) legendas
    subs = None
    srt = []
    if subs_on:
        subs = V.Subtitles(W, H, V.find_font(theme["font"], "black"), theme.get("subtitle_color") or
                           theme.get("accent") or theme["palette"][-1], style=subs_style,
                           position=theme.get("subtitle_position"))
    vertical = H > W
    for sc in scenes:
        if not sc["_words"]:
            continue
        off = sc["_start"] + sc["_voice_start"]
        chunks = chunk_words(sc["_words"], 4 if vertical else 7, 26 if vertical else 44)
        glob = []
        for ch in chunks:
            glob.append([(w, s + off, e + off) for w, s, e in ch])
        for k, ch in enumerate(glob):
            s = ch[0][1]
            e = ch[-1][2] + 0.25
            if k + 1 < len(glob):
                e = min(e, glob[k + 1][0][1])
            e = max(e, s + 0.4)
            srt.append((s, e, " ".join(w for w, _, _ in ch)))
            if subs:
                subs.add_chunks([(s, e, ch)])

    def overlays(frame, T_):
        if theme.get("progress_bar"):
            hgt = max(4, H // 220)
            bar = Image.new("RGBA", (W, hgt), (255, 255, 255, 45))
            ImageDraw.Draw(bar).rectangle((0, 0, int(W * T_ / total), hgt), fill=V.hex2rgb(theme["palette"][-1], 255))
            frame.alpha_composite(bar)
        if theme.get("handle"):
            hf = V.font(V.find_font(theme["font"], "bold"), int(min(W, H) * 0.03))
            if "_handle" not in theme:
                theme["_handle"] = V.text_sprite(theme["handle"], hf, "#ffffff", shadow=True)[0]
            V.paste(frame, theme["_handle"], W * 0.04, H * 0.03, 0.8)
        if theme.get("_logo") is not None:
            lg = theme["_logo"]
            V.paste(frame, lg, W - lg.width - W * 0.04, H * 0.03, 0.92)
        if subs:
            subs.draw(frame, T_)
        return frame

    if theme.get("logo"):
        lp = theme["logo"] if os.path.isabs(theme["logo"]) else os.path.join(base_dir, theme["logo"])
        lg = Image.open(lp).convert("RGBA")
        s_ = (min(W, H) * 0.11) / lg.height
        theme["_logo"] = lg.resize((int(lg.width * s_), int(lg.height * s_)), Image.LANCZOS)

    def frame_at(T_, prev_cache={}):
        i = max(k for k, sc in enumerate(scenes) if sc["_start"] <= T_ + 1e-9) if T_ < t0 else len(scenes) - 1
        sc = scenes[i]
        t = T_ - sc["_start"]
        cur = render_scene(scene_objs[i], t, T_)
        td = float(sc.get("transition_duration", 0.45))
        kind = sc.get("transition") or theme["transition"]
        if i > 0 and t < td and kind != "none":
            if i not in prev_cache:
                p = scenes[i - 1]
                prev_cache.clear()
                prev_cache[i] = render_scene(scene_objs[i - 1], p["_dur"] - 1 / fps, sc["_start"] - 1 / fps)
            cur = transition(prev_cache[i], cur, kind, t / td, W, H)
        return overlays(cur, T_)

    if still is not None:
        out_png = os.path.splitext(out_path)[0] + f"_t{still:.1f}.png"
        frame_at(float(still)).convert("RGB").save(out_png)
        log(f"✔ Quadro salvo: {out_png}")
        return out_png

    # 5) áudio
    log("▶ Áudio: voz + trilha + efeitos")
    n = int(total * A.SR) + A.SR
    voice = np.zeros(n)
    for sc in scenes:
        if sc["_wav"]:
            A.add_at(voice, A.load_audio(sc["_wav"]), sc["_start"] + sc["_voice_start"])
    mcfg = {"mood": "upbeat", "volume": 0.22, **(sb.get("music") or {})}
    if mcfg.get("file"):
        mp = mcfg["file"] if os.path.isabs(mcfg["file"]) else os.path.join(base_dir, mcfg["file"])
        music = A.music_from_file(mp, total)
    elif mcfg["mood"] in (None, "none", False):
        music = np.zeros(n)
    else:
        music = A.synth_music(total, mcfg["mood"], mcfg.get("bpm"), seed=int(mcfg.get("seed", len(scenes))))
    fx = np.zeros(n)
    auto = sb.get("sfx_auto", True)
    for i, (sc, so) in enumerate(zip(scenes, scene_objs)):
        st = sc["_start"]
        if auto:
            kind = sc.get("transition") or theme["transition"]
            if i > 0 and kind != "none":
                A.add_at(fx, A.sfx("swoosh" if kind == "fade" else "whoosh"), st - 0.12, 0.55)
            for e, _ in so.items:
                if getattr(e, "sfx_times", None):
                    for tt in e.sfx_times:
                        A.add_at(fx, A.sfx("pop"), st + tt, 0.55)
                elif e.sfx:
                    A.add_at(fx, A.sfx(e.sfx), st + e.appear, 0.7)
            if i == 0 and sc.get("type") == "title":
                A.add_at(fx, A.sfx("impact"), st + 0.2, 0.6)
        for item in sc.get("sfx", []):
            name, at, g = (item, 0.0, 0.8) if isinstance(item, str) else (item["name"], item.get("at", 0.0),
                                                                           item.get("volume", 0.8))
            src = name if name in A.SFX_NAMES or os.path.isabs(name) else os.path.join(base_dir, name)
            A.add_at(fx, A.load_sfx(src), st + float(at), g)
    mix = A.master(voice, music, fx, music_volume=float(mcfg["volume"]), sfx_volume=float(sb.get("sfx_volume", 0.6)),
                   duck=float(mcfg.get("duck", 0.65)))[:int(total * A.SR)]
    mix = A.fade(mix, 0.02, 0.4)
    A.write_wav(os.path.join(work, "voice.wav"), voice[:len(mix)])
    A.write_wav(os.path.join(work, "music.wav"), music[:len(mix)] * float(mcfg["volume"]))
    A.write_wav(os.path.join(work, "sfx.wav"), fx[:len(mix)] * 0.6)
    mix_path = os.path.join(work, "mix.wav")
    A.write_wav(mix_path, mix)

    # 6) legendas .srt + linha do tempo
    srt_path = os.path.splitext(out_path)[0] + ".srt"
    with open(srt_path, "w", encoding="utf-8") as fh:
        for k, (s, e, txt) in enumerate(srt, 1):
            fh.write(f"{k}\n{srt_time(s)} --> {srt_time(e)}\n{txt}\n\n")
    json.dump([{"scene": i + 1, "start": round(sc["_start"], 2), "duration": round(sc["_dur"], 2),
                "voice": round(sc["_voice_dur"], 2)} for i, sc in enumerate(scenes)],
              open(os.path.join(work, "timeline.json"), "w"), indent=1)

    # 7) vídeo
    log(f"▶ Renderizando {W}x{H} @ {fps}fps")
    n_frames = int(math.ceil(total * fps))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-i", mix_path, "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "veryfast" if preview else "medium", "-crf", "23" if preview else "19",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-shortest", "-movflags", "+faststart",
           out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    last = time.time()
    thumb_t = min(scenes[0]["_dur"] - 0.1, 1.6)
    thumb = None
    try:
        for fi in range(n_frames):
            T_ = fi / fps
            fr = frame_at(T_).convert("RGB")
            if thumb is None and T_ >= thumb_t:
                thumb = fr
            proc.stdin.write(fr.tobytes())
            if time.time() - last > 5:
                last = time.time()
                log(f"  {100 * fi / n_frames:5.1f}%  ({fi}/{n_frames} quadros)")
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError("ffmpeg falhou ao codificar o vídeo")
    if thumb is not None:
        thumb.save(os.path.splitext(out_path)[0] + "_thumb.jpg", quality=92)
    log(f"✔ {out_path}  ({total:.1f}s, {os.path.getsize(out_path) / 1e6:.1f} MB, "
        f"render em {time.time() - t_start:.0f}s)")
    log(f"  legendas: {srt_path}\n  stems/mix: {work}/")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Gera um vídeo completo a partir de um roteiro JSON")
    ap.add_argument("storyboard")
    ap.add_argument("-o", "--out", help="arquivo .mp4 de saída (padrão: out/<nome>.mp4)")
    ap.add_argument("--format", help="9:16, 16:9, 1:1, 4:5 (vírgula para vários)")
    ap.add_argument("--preview", action="store_true", help="meia resolução, 24fps, encode rápido")
    ap.add_argument("--still", type=float, help="renderiza apenas o quadro no tempo indicado (s)")
    ap.add_argument("--engine", help="força motor de voz: edge|gtts|elevenlabs|piper|espeak")
    ap.add_argument("--no-subs", action="store_true")
    ap.add_argument("--list-engines", action="store_true")
    a = ap.parse_args()
    if a.list_engines:
        print("Motores de voz disponíveis:", ", ".join(T.available_engines()) or "nenhum")
        return
    sb = json.load(open(a.storyboard, encoding="utf-8"))
    base = os.path.dirname(os.path.abspath(a.storyboard))
    fmts = (a.format or sb.get("format", "9:16")).split(",")
    name = os.path.splitext(os.path.basename(a.storyboard))[0]
    for fmt in fmts:
        fmt = fmt.strip()
        if fmt not in V.FORMATS:
            sys.exit(f"formato inválido: {fmt} (use {', '.join(V.FORMATS)})")
        out = a.out or os.path.join("out", f"{name}.mp4")
        if len(fmts) > 1:
            out = os.path.splitext(out)[0] + f"_{fmt.replace(':', 'x')}.mp4"
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        produce(json.loads(json.dumps(sb)), base, out, fmt, a.preview, a.still, a.engine, a.no_subs)


if __name__ == "__main__":
    main()
