"""Narração (text-to-speech) com cadeia de fallback.

Motores, na ordem do modo "auto":
  1. elevenlabs  - se ELEVENLABS_API_KEY estiver definida (qualidade de estúdio)
  2. edge        - vozes neurais da Microsoft via edge-tts (grátis, precisa de internet)
  3. gtts        - Google Translate TTS (grátis, precisa de internet)
  4. piper       - neural offline, se PIPER_MODEL apontar para um .onnx
  5. espeak      - offline, robótico, sempre disponível como último recurso

Cada síntese devolve (caminho_wav, duracao_s, palavras) em que `palavras` é uma
lista de (texto, inicio_s, fim_s) quando o motor informa os tempos (edge-tts),
ou None (o chamador estima).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request

from audio import SR, load_audio, write_wav

DEFAULT_VOICE = "pt-BR-FranciscaNeural"


def lang_of(voice: str, fallback: str = "pt-BR") -> str:
    parts = (voice or "").split("-")
    if len(parts) >= 2 and len(parts[0]) == 2 and len(parts[1]) == 2:
        return f"{parts[0]}-{parts[1]}"
    return fallback


def _pct(rate: str | None) -> float:
    """'+10%' -> 1.10"""
    if not rate:
        return 1.0
    try:
        return 1.0 + float(str(rate).strip().rstrip("%")) / 100.0
    except ValueError:
        return 1.0


def _to_wav(src: str, dst: str, tempo: float = 1.0) -> None:
    af = ["-af", f"atempo={max(0.5, min(2.0, tempo))}"] if abs(tempo - 1.0) > 0.01 else []
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, *af,
                    "-ac", "1", "-ar", str(SR), dst], check=True)


# ---------------------------------------------------------------- engines
def _edge(text, voice, rate, pitch, out_mp3):
    import edge_tts  # noqa: WPS433

    async def run():
        words = []
        com = edge_tts.Communicate(text, voice, rate=rate or "+0%", pitch=pitch or "+0Hz",
                                   boundary="WordBoundary")
        with open(out_mp3, "wb") as fh:
            async for chunk in com.stream():
                if chunk["type"] == "audio":
                    fh.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    st = chunk["offset"] / 1e7
                    words.append((chunk["text"], st, st + chunk["duration"] / 1e7))
        return words

    words = asyncio.run(run())
    if os.path.getsize(out_mp3) == 0:
        raise RuntimeError("edge-tts não retornou áudio")
    return words or None


def _gtts(text, voice, out_mp3):
    from gtts import gTTS

    lang = lang_of(voice)
    code, region = lang.split("-")
    tld = {"BR": "com.br", "PT": "pt", "US": "com", "GB": "co.uk", "ES": "es",
           "MX": "com.mx", "FR": "fr", "AU": "com.au", "IN": "co.in"}.get(region.upper(), "com")
    gTTS(text, lang=code.lower(), tld=tld).save(out_mp3)


def _elevenlabs(text, voice, out_mp3):
    key = os.environ["ELEVENLABS_API_KEY"]
    voice_id = voice if voice and "Neural" not in voice else os.environ.get(
        "ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
    body = json.dumps({"text": text, "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")})
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}", data=body.encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=120) as r, open(out_mp3, "wb") as fh:
        fh.write(r.read())


def _piper(text, out_wav):
    model = os.environ["PIPER_MODEL"]
    exe = shutil.which("piper") or "piper"
    subprocess.run([exe, "--model", model, "--output_file", out_wav],
                   input=text.encode(), check=True, capture_output=True)


def _espeak(text, voice, rate, out_wav):
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("espeak-ng não instalado")
    lang = lang_of(voice).lower()
    v = {"pt-br": "pt-br", "pt-pt": "pt", "en-us": "en-us", "en-gb": "en-gb"}.get(lang, lang.split("-")[0])
    speed = int(165 * _pct(rate))
    subprocess.run([exe, "-v", v, "-s", str(speed), "-w", out_wav, text], check=True, capture_output=True)


# ---------------------------------------------------------------- public
def available_engines() -> list[str]:
    eng = []
    if os.environ.get("ELEVENLABS_API_KEY"):
        eng.append("elevenlabs")
    for mod, name in (("edge_tts", "edge"), ("gtts", "gtts")):
        try:
            __import__(mod)
            eng.append(name)
        except ImportError:
            pass
    if os.environ.get("PIPER_MODEL") and shutil.which("piper"):
        eng.append("piper")
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        eng.append("espeak")
    return eng


def synthesize(text: str, cache_dir: str, engine: str = "auto", voice: str | None = None,
               rate: str | None = None, pitch: str | None = None, log=print):
    """Gera narração e devolve (wav_path, duração, palavras|None, motor_usado)."""
    voice = voice or DEFAULT_VOICE
    os.makedirs(cache_dir, exist_ok=True)
    order = available_engines() if engine == "auto" else [engine]
    errors = []
    for eng in order:
        key = hashlib.sha1(json.dumps([eng, text, voice, rate, pitch]).encode()).hexdigest()[:16]
        wav = os.path.join(cache_dir, f"{key}.wav")
        meta = wav + ".json"
        if os.path.exists(wav) and os.path.exists(meta):
            words = json.load(open(meta))["words"]
            y = load_audio(wav)
            return wav, len(y) / SR, words, eng
        tmp = os.path.join(cache_dir, f"{key}.tmp")
        words = None
        try:
            if eng == "edge":
                words = _edge(text, voice, rate, pitch, tmp + ".mp3")
                _to_wav(tmp + ".mp3", wav)
            elif eng == "gtts":
                _gtts(text, voice, tmp + ".mp3")
                _to_wav(tmp + ".mp3", wav, tempo=1.12 * _pct(rate))  # gTTS fala devagar
            elif eng == "elevenlabs":
                _elevenlabs(text, voice, tmp + ".mp3")
                _to_wav(tmp + ".mp3", wav, tempo=_pct(rate))
            elif eng == "piper":
                _piper(text, tmp + ".wav")
                _to_wav(tmp + ".wav", wav, tempo=_pct(rate))
            elif eng == "espeak":
                _espeak(text, voice, rate, tmp + ".wav")
                _to_wav(tmp + ".wav", wav)
            else:
                raise ValueError(f"motor desconhecido: {eng}")
        except Exception as exc:  # noqa: BLE001 - tenta o próximo motor
            errors.append(f"{eng}: {str(exc).splitlines()[0][:160] if str(exc) else type(exc).__name__}")
            for ext in (".mp3", ".wav"):
                if os.path.exists(tmp + ext):
                    os.remove(tmp + ext)
            continue
        for ext in (".mp3", ".wav"):
            if os.path.exists(tmp + ext):
                os.remove(tmp + ext)
        # remove silêncio inicial/final excessivo e desloca os tempos das palavras
        y = load_audio(wav)
        y, shift = _trim(y)
        write_wav(wav, y)
        if words:
            words = [(w, max(0.0, s - shift), max(0.0, e - shift)) for w, s, e in words]
        json.dump({"words": words, "engine": eng}, open(meta, "w"))
        return wav, len(y) / SR, words, eng
    raise RuntimeError("Nenhum motor de voz funcionou:\n  " + "\n  ".join(errors))


def _trim(y, thresh=0.01, keep=0.06):
    import numpy as np

    idx = np.where(np.abs(y) > thresh)[0]
    if len(idx) == 0:
        return y, 0.0
    a = max(0, idx[0] - int(keep * SR))
    b = min(len(y), idx[-1] + int(keep * 2 * SR))
    return y[a:b], a / SR
