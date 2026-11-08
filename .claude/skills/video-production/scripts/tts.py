"""Narração: TTS com cadeia de fallback + narração gravada pelo usuário.

Motores, na ordem do modo "auto" (o primeiro que funcionar é usado):
  1. elevenlabs  - ELEVENLABS_API_KEY        (melhor qualidade; devolve tempo de cada palavra)
  2. openai      - OPENAI_API_KEY            (gpt-4o-mini-tts; aceita instruções de tom/emoção)
  3. edge        - edge-tts, grátis, internet (neural; devolve tempo de cada palavra)
  4. gtts        - Google Translate TTS       (internet)
  5. piper       - offline neural, PIPER_MODEL=/caminho/voz.onnx
  6. espeak      - offline, robótico (último recurso)

Toda narração passa por `audio.polish_voice` (EQ, de-esser, compressor, limitador).
`synthesize` devolve (wav, duração_s, palavras|None, motor) com palavras = [(texto, ini, fim)].
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request

import numpy as np

from audio import SR, load_audio, polish_voice, write_wav

DEFAULT_VOICE = "pt-BR-FranciscaNeural"
ENGINE_ORDER = ["elevenlabs", "openai", "edge", "gtts", "piper", "espeak"]
OPENAI_VOICES = {"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer",
                 "verse", "marin", "cedar"}


def lang_of(voice: str, fallback: str = "pt-BR") -> str:
    parts = (voice or "").split("-")
    if len(parts) >= 2 and len(parts[0]) == 2 and len(parts[1]) == 2:
        return f"{parts[0]}-{parts[1]}"
    return fallback


def _pct(rate) -> float:
    """'+10%' -> 1.10"""
    if not rate:
        return 1.0
    try:
        return 1.0 + float(str(rate).strip().rstrip("%")) / 100.0
    except ValueError:
        return 1.0


def _to_wav(src: str, dst: str, tempo: float = 1.0) -> None:
    af = ["-af", f"atempo={max(0.5, min(2.0, tempo))}"] if abs(tempo - 1.0) > 0.01 else []
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, *af, "-ac", "1", "-ar", str(SR),
                    "-c:a", "pcm_s24le", dst], check=True)


def _post_json(url, body, headers, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]!r}") from None


def _chars_to_words(chars, starts, ends):
    """Alinhamento por caractere (ElevenLabs) -> palavras."""
    words, cur, s0, e0 = [], "", None, None
    for c, s, e in zip(chars, starts, ends):
        if c.isspace():
            if cur:
                words.append((cur, s0, e0))
            cur, s0 = "", None
            continue
        if s0 is None:
            s0 = s
        cur += c
        e0 = e
    if cur:
        words.append((cur, s0, e0))
    return words


# ---------------------------------------------------------------- motores
def _elevenlabs(text, cfg, out_mp3):
    key = os.environ["ELEVENLABS_API_KEY"]
    voice = cfg.get("voice") or ""
    voice_id = voice if voice and "Neural" not in voice and voice not in OPENAI_VOICES else \
        os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
    body = {
        "text": text,
        "model_id": cfg.get("model") or os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25, "use_speaker_boost": True,
                           "speed": max(0.7, min(1.2, _pct(cfg.get("rate")))), **(cfg.get("settings") or {})},
    }
    if cfg.get("previous_text"):
        body["previous_text"] = cfg["previous_text"]  # mantém entonação contínua entre cenas
    if cfg.get("next_text"):
        body["next_text"] = cfg["next_text"]
    raw = _post_json(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
                     "?output_format=mp3_44100_192", body, {"xi-api-key": key})
    data = json.loads(raw)
    with open(out_mp3, "wb") as fh:
        fh.write(base64.b64decode(data["audio_base64"]))
    al = data.get("alignment") or data.get("normalized_alignment")
    if al:
        return _chars_to_words(al["characters"], al["character_start_times_seconds"],
                               al["character_end_times_seconds"])
    return None


def _openai(text, cfg, out_wav):
    key = os.environ["OPENAI_API_KEY"]
    voice = cfg.get("voice") if cfg.get("voice") in OPENAI_VOICES else os.environ.get("OPENAI_TTS_VOICE", "onyx")
    body = {"model": cfg.get("model") or os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            "voice": voice, "input": text, "response_format": "wav"}
    instr = cfg.get("instructions") or os.environ.get("OPENAI_TTS_INSTRUCTIONS")
    if instr:
        body["instructions"] = instr
    raw = _post_json("https://api.openai.com/v1/audio/speech", body, {"Authorization": f"Bearer {key}"})
    with open(out_wav, "wb") as fh:
        fh.write(raw)


def _edge(text, cfg, out_mp3):
    import edge_tts  # noqa: WPS433

    voice = cfg.get("voice") or DEFAULT_VOICE
    if "Neural" not in voice:
        voice = DEFAULT_VOICE

    async def run():
        words = []
        com = edge_tts.Communicate(text, voice, rate=cfg.get("rate") or "+0%", pitch=cfg.get("pitch") or "+0Hz",
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


def _gtts(text, cfg, out_mp3):
    from gtts import gTTS

    lang = lang_of(cfg.get("voice") or DEFAULT_VOICE)
    code, region = lang.split("-")
    tld = {"BR": "com.br", "PT": "pt", "US": "com", "GB": "co.uk", "ES": "es",
           "MX": "com.mx", "FR": "fr", "AU": "com.au", "IN": "co.in"}.get(region.upper(), "com")
    gTTS(text, lang=code.lower(), tld=tld).save(out_mp3)


def _piper(text, out_wav):
    exe = shutil.which("piper") or "piper"
    subprocess.run([exe, "--model", os.environ["PIPER_MODEL"], "--output_file", out_wav],
                   input=text.encode(), check=True, capture_output=True)


def _espeak(text, cfg, out_wav):
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("espeak-ng não instalado")
    lang = lang_of(cfg.get("voice") or DEFAULT_VOICE).lower()
    v = {"pt-br": "pt-br", "pt-pt": "pt", "en-us": "en-us", "en-gb": "en-gb"}.get(lang, lang.split("-")[0])
    subprocess.run([exe, "-v", v, "-s", str(int(165 * _pct(cfg.get("rate")))), "-w", out_wav, text],
                   check=True, capture_output=True)


# ---------------------------------------------------------------- público
def available_engines() -> list[str]:
    eng = []
    if os.environ.get("ELEVENLABS_API_KEY"):
        eng.append("elevenlabs")
    if os.environ.get("OPENAI_API_KEY"):
        eng.append("openai")
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


def _trim(y, thresh=0.01, keep=0.06):
    idx = np.where(np.abs(y) > thresh)[0]
    if len(idx) == 0:
        return y, 0.0
    a = max(0, idx[0] - int(keep * SR))
    b = min(len(y), idx[-1] + int(keep * 2 * SR))
    return y[a:b], a / SR


def _finish(raw_wav, wav, words, preset, trim=True):
    """Tratamento de voz + corte de silêncio + ajuste dos tempos das palavras."""
    polish_voice(raw_wav, wav, preset)
    y = load_audio(wav)
    shift = 0.0
    if trim:
        y, shift = _trim(y)
        write_wav(wav, y)
    if words:
        words = [(w, max(0.0, s - shift), max(0.0, e - shift)) for w, s, e in words]
    return y, words


def synthesize(text: str, cache_dir: str, cfg: dict, log=print):
    """Gera narração por TTS. cfg: engine, voice, rate, pitch, instructions, model, settings, polish."""
    os.makedirs(cache_dir, exist_ok=True)
    engine = cfg.get("engine", "auto")
    order = available_engines() if engine == "auto" else [engine]
    preset = cfg.get("polish", "tts")
    errors = []
    for eng in order:
        sig = {k: cfg.get(k) for k in ("voice", "rate", "pitch", "instructions", "model", "settings")}
        key = hashlib.sha1(json.dumps([eng, text, sig, preset, 2], sort_keys=True).encode()).hexdigest()[:16]
        wav = os.path.join(cache_dir, f"{key}.wav")
        meta = wav + ".json"
        if os.path.exists(wav) and os.path.exists(meta):
            words = json.load(open(meta))["words"]
            return wav, len(load_audio(wav)) / SR, words, eng
        tmp = os.path.join(cache_dir, f"{key}.tmp")
        words = None
        try:
            if eng == "elevenlabs":
                words = _elevenlabs(text, cfg, tmp + ".mp3")
                _to_wav(tmp + ".mp3", tmp + ".wav")
            elif eng == "openai":
                _openai(text, cfg, tmp + ".src.wav")
                _to_wav(tmp + ".src.wav", tmp + ".wav", tempo=_pct(cfg.get("rate")))
            elif eng == "edge":
                words = _edge(text, cfg, tmp + ".mp3")
                _to_wav(tmp + ".mp3", tmp + ".wav")
            elif eng == "gtts":
                _gtts(text, cfg, tmp + ".mp3")
                _to_wav(tmp + ".mp3", tmp + ".wav", tempo=1.12 * _pct(cfg.get("rate")))  # gTTS fala devagar
            elif eng == "piper":
                _piper(text, tmp + ".src.wav")
                _to_wav(tmp + ".src.wav", tmp + ".wav", tempo=_pct(cfg.get("rate")))
            elif eng == "espeak":
                _espeak(text, cfg, tmp + ".src.wav")
                _to_wav(tmp + ".src.wav", tmp + ".wav")
            else:
                raise ValueError(f"motor desconhecido: {eng}")
            y, words = _finish(tmp + ".wav", wav, words, preset)
        except Exception as exc:  # noqa: BLE001 - tenta o próximo motor
            msg = str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__
            errors.append(f"{eng}: {msg}")
            continue
        finally:
            for ext in (".mp3", ".wav", ".src.wav"):
                if os.path.exists(tmp + ext):
                    os.remove(tmp + ext)
        json.dump({"words": words, "engine": eng}, open(meta, "w"))
        return wav, len(y) / SR, words, eng
    raise RuntimeError("Nenhum motor de voz funcionou:\n  " + "\n  ".join(errors))


def transcribe_words(wav: str, lang: str = "pt"):
    """Tempos de cada palavra de uma gravação via faster-whisper (opcional). None se indisponível."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "small"), device="auto", compute_type="int8")
    segs, _ = model.transcribe(wav, language=lang, word_timestamps=True, vad_filter=True)
    return [(w.word.strip(), float(w.start), float(w.end)) for s in segs for w in (s.words or []) if w.word.strip()]


def recorded(path: str, cache_dir: str, preset: str = "gravacao", lang: str = "pt"):
    """Narração gravada pelo usuário: limpa (ruído, EQ, compressão) e tenta alinhar palavras."""
    os.makedirs(cache_dir, exist_ok=True)
    st = os.stat(path)
    key = hashlib.sha1(json.dumps([os.path.abspath(path), st.st_size, st.st_mtime, preset, 2]).encode()).hexdigest()[:16]
    wav = os.path.join(cache_dir, f"rec_{key}.wav")
    meta = wav + ".json"
    if os.path.exists(wav) and os.path.exists(meta):
        return wav, len(load_audio(wav)) / SR, json.load(open(meta))["words"], "gravação"
    tmp = os.path.join(cache_dir, f"rec_{key}.tmp.wav")
    _to_wav(path, tmp)
    y, _ = _finish(tmp, wav, None, preset)
    os.remove(tmp)
    words = transcribe_words(wav, lang.split("-")[0])
    json.dump({"words": words, "engine": "gravação"}, open(meta, "w"))
    return wav, len(y) / SR, words, "gravação"
