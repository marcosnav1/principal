#!/usr/bin/env python3
"""Geração de imagens (com referências de personagem) e clipes Veo pela API do Gemini.

Autenticação (nesta ordem):
  1. variável GEMINI_API_KEY (ou GOOGLE_API_KEY), enviada no cabeçalho x-goog-api-key;
  2. sem variável: a requisição sai sem chave e o proxy do ambiente injeta a chave salva
     como "network secret" para generativelanguage.googleapis.com (Claude Code na nuvem).

    python gemini_media.py models
    python gemini_media.py image -p "prompt" --ref lulinha.png --ref sala.png --aspect 9:16 -o cena.png
    python gemini_media.py video -p "prompt" --image cena.png --aspect 9:16 --seconds 8 -o clipe.mp4
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://generativelanguage.googleapis.com/v1beta"


def _headers():
    h = {"Content-Type": "application/json"}
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        h["x-goog-api-key"] = key
    return h


def _req(method, url, body=None, timeout=300, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:600]
        raise RuntimeError(f"HTTP {e.code} em {url.split('?')[0]}: {msg}") from None
    return payload if raw else json.loads(payload)


def list_models():
    out, token = [], None
    while True:
        url = f"{BASE}/models?pageSize=200" + (f"&pageToken={token}" if token else "")
        d = _req("GET", url)
        out += d.get("models", [])
        token = d.get("nextPageToken")
        if not token:
            return out


def pick_model(kind, preferred=None):
    """Escolhe o modelo disponível na conta: kind='image' ou 'video'."""
    if preferred:
        return preferred if preferred.startswith("models/") else f"models/{preferred}"
    names = [m["name"] for m in list_models()]
    if kind == "image":
        cands = [n for n in names if "image" in n and ("gemini" in n) and "imagen" not in n]
    else:
        cands = [n for n in names if "veo" in n]
    if not cands:
        raise RuntimeError(f"Nenhum modelo de {kind} disponível para esta chave. Modelos: {len(names)}")

    def score(n):  # prefere versões mais novas e não 'lite'/'fast'
        s = 0
        s -= 5 if "lite" in n else 0
        s -= 2 if "fast" in n else 0
        s -= 1 if "preview" in n else 0
        digits = "".join(ch if ch.isdigit() or ch == "." else " " for ch in n).split()
        ver = max((float(x) for x in digits if x.replace(".", "", 1).isdigit() and x.count(".") <= 1), default=0)
        return (ver, s)

    return sorted(cands, key=score)[-1]


def _inline(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(open(path, "rb").read()).decode()}}


def generate_image(prompt, out, refs=(), aspect="9:16", model=None, log=print):
    model = pick_model("image", model)
    parts = [{"text": prompt}] + [_inline(r) for r in refs]
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
    log(f"  imagem via {model.split('/')[-1]} ({len(refs)} referência(s))")
    d = _req("POST", f"{BASE}/{model}:generateContent", body)
    for cand in d.get("candidates", []):
        for p in cand.get("content", {}).get("parts", []):
            blob = p.get("inlineData") or p.get("inline_data")
            if blob:
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                with open(out, "wb") as fh:
                    fh.write(base64.b64decode(blob["data"]))
                return out
    reason = json.dumps(d.get("promptFeedback") or d.get("candidates", [{}])[0].get("finishReason"))
    raise RuntimeError(f"O modelo não devolveu imagem (motivo: {reason})")


def generate_video(prompt, out, image=None, aspect="9:16", seconds=8, model=None, negative=None, log=print,
                   poll=10, timeout=900):
    model = pick_model("video", model)
    inst = {"prompt": prompt}
    if image:
        mime = mimetypes.guess_type(image)[0] or "image/png"
        inst["image"] = {"bytesBase64Encoded": base64.b64encode(open(image, "rb").read()).decode(), "mimeType": mime}
    params = {"aspectRatio": aspect, "durationSeconds": int(seconds)}
    if negative:
        params["negativePrompt"] = negative
    log(f"  vídeo via {model.split('/')[-1]} ({seconds}s, {aspect})")
    op = _req("POST", f"{BASE}/{model}:predictLongRunning", {"instances": [inst], "parameters": params})
    name = op["name"]
    t0 = time.time()
    while not op.get("done"):
        if time.time() - t0 > timeout:
            raise RuntimeError(f"Tempo esgotado aguardando {name}")
        time.sleep(poll)
        op = _req("GET", f"{BASE}/{name}")
    if "error" in op:
        raise RuntimeError(f"Veo falhou: {op['error']}")
    resp = op.get("response", {})
    samples = (resp.get("generateVideoResponse") or resp).get("generatedSamples") or resp.get("videos") or []
    if not samples:
        raise RuntimeError(f"Veo não devolveu vídeo (talvez bloqueado por política): {json.dumps(resp)[:400]}")
    uri = samples[0].get("video", {}).get("uri") or samples[0].get("uri")
    data = _req("GET", uri + ("&" if "?" in uri else "?") + "alt=media", raw=True, timeout=600)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(data)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models")
    pi = sub.add_parser("image")
    pi.add_argument("-p", "--prompt", required=True)
    pi.add_argument("--ref", action="append", default=[])
    pi.add_argument("--aspect", default="9:16")
    pi.add_argument("--model")
    pi.add_argument("-o", "--out", required=True)
    pv = sub.add_parser("video")
    pv.add_argument("-p", "--prompt", required=True)
    pv.add_argument("--image")
    pv.add_argument("--aspect", default="9:16")
    pv.add_argument("--seconds", type=int, default=8)
    pv.add_argument("--negative")
    pv.add_argument("--model")
    pv.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    try:
        if a.cmd == "models":
            for m in list_models():
                meths = ",".join(m.get("supportedGenerationMethods", []))
                if any(k in m["name"] for k in ("image", "veo", "imagen")):
                    print(m["name"], "|", meths)
        elif a.cmd == "image":
            print(generate_image(a.prompt, a.out, a.ref, a.aspect, a.model))
        else:
            print(generate_video(a.prompt, a.out, a.image, a.aspect, a.seconds, a.model, a.negative))
    except RuntimeError as e:
        sys.exit(f"erro: {e}")


if __name__ == "__main__":
    main()
