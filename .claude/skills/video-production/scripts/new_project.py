#!/usr/bin/env python3
"""Cria a estrutura de um projeto de vídeo ou gera o roteiro a partir das imagens.

    python new_project.py meu-video                  # cria pastas + roteiro modelo + .env.example
    python new_project.py meu-video --from-images    # roteiro com 1 cena ilustrada por imagem
                                                     # (abertura e encerramento animados)

Estrutura:
    meu-video/
      roteiro.json      storyboard (cenas de animação + cenas ilustradas)
      imagens/          SUAS fotos/ilustrações (jpg, png, webp) - ordem pelo nome: 01.jpg, 02.jpg...
      narracao/         (opcional) narração gravada por cena: cena01.mp3, cena02.mp3...
      musica/           (opcional) trilhas licenciadas; subpastas por clima: musica/calm/, musica/upbeat/
      sfx/              (opcional) efeitos próprios com o nome do efeito: whoosh.wav, pop.wav, ding.wav...
      .env              chaves de API (ELEVENLABS_API_KEY, OPENAI_API_KEY) - nunca versionar
      out/              vídeos gerados
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")

ENV_EXAMPLE = """# Copie para .env e preencha UMA das opções de voz (a primeira disponível é usada).
# ElevenLabs (melhor qualidade, tempo exato de cada palavra p/ legenda):
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
# ELEVENLABS_MODEL=eleven_multilingual_v2
#
# OpenAI TTS (bom e barato; aceita instruções de tom):
OPENAI_API_KEY=
# OPENAI_TTS_VOICE=onyx
# OPENAI_TTS_INSTRUCTIONS=Narrador brasileiro, tom acolhedor e nostálgico, ritmo calmo.
#
# Opcional: alinhamento de narração gravada (pip install faster-whisper)
# WHISPER_MODEL=small
"""

README = """# {name}

1. Coloque suas imagens em `imagens/` (01.jpg, 02.jpg, ...).
2. (Opcional) trilhas licenciadas em `musica/<clima>/`, efeitos em `sfx/`, narração gravada em `narracao/`.
3. Copie `.env.example` para `.env` e coloque a chave de voz (ElevenLabs ou OpenAI).
4. Edite `roteiro.json` (ou peça ao Claude para escrever o roteiro).
5. Gere:
   - quadro de conferência: `python3 {produce} roteiro.json --still 3`
   - prévia rápida:         `python3 {produce} roteiro.json --preview`
   - final:                 `python3 {produce} roteiro.json -o out/video.mp4`
"""


def caption_from(fname):
    base = os.path.splitext(os.path.basename(fname))[0]
    base = re.sub(r"^\d+[\s._-]*", "", base).replace("_", " ").replace("-", " ").strip()
    return base[:1].upper() + base[1:] if base else ""


def template(images):
    scenes = [{
        "kind": "animacao",
        "type": "title",
        "kicker": "Tema",
        "title": "Título do vídeo com **destaque**",
        "narration": "TODO: gancho de abertura em uma ou duas frases.",
    }]
    looks = ["cinematic", "warm", "cinematic", "vintage"]
    for i, img in enumerate(images):
        cap = caption_from(img)
        scenes.append({
            "kind": "imagem",
            "images": [os.path.relpath(img, start=os.path.dirname(os.path.dirname(img)))],
            "look": looks[i % len(looks)],
            "title": cap or None,
            "narration": f"TODO: narração da imagem {i + 1}" + (f" ({cap})." if cap else "."),
        })
        if i % 3 == 2 and i + 1 < len(images):  # intercala uma cena animada a cada 3 imagens
            scenes.append({"kind": "animacao", "title": "TODO: ideia-chave", "text": "TODO: frase de apoio",
                           "narration": "TODO: narração da cena animada."})
    if not images:
        scenes.append({"kind": "imagem", "images": ["imagens/01.jpg"], "look": "cinematic",
                       "lower_third": {"title": "Nome / lugar", "subtitle": "Legenda curta"},
                       "narration": "TODO: narração sobre a imagem."})
    scenes.append({"kind": "animacao", "type": "cta", "title": "Chamada **final**?", "button": "Siga para mais",
                   "narration": "TODO: chamada para ação."})
    for s in scenes:
        if s.get("title") is None:
            s.pop("title", None)
    return {
        "title": "Meu vídeo",
        "format": "9:16",
        "voice": {"engine": "auto", "voice": "pt-BR-AntonioNeural", "rate": "+0%",
                  "instructions": "Narrador brasileiro, tom acolhedor, ritmo natural."},
        "music": {"mood": "calm", "volume": 0.18, "library": "musica"},
        "loudness": -14,
        "theme": {"palette": ["#101418", "#2b3440", "#f5c518"], "font": "Inter", "background": "bokeh",
                  "transition": "fade", "subtitle_style": "karaoke", "look": "cinematic", "progress_bar": True},
        "scenes": scenes,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--from-images", action="store_true", help="gera roteiro a partir de imagens/")
    ap.add_argument("--force", action="store_true", help="sobrescreve roteiro.json existente")
    a = ap.parse_args()
    for sub in ("imagens", "narracao", "musica", "sfx", "out"):
        os.makedirs(os.path.join(a.dir, sub), exist_ok=True)
    env = os.path.join(a.dir, ".env.example")
    if not os.path.exists(env):
        open(env, "w").write(ENV_EXAMPLE)
    gi = os.path.join(a.dir, ".gitignore")
    if not os.path.exists(gi):
        open(gi, "w").write(".env\nout/\n.tts_cache/\n*_work/\n")
    produce = os.path.relpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "produce.py"), a.dir)
    rd = os.path.join(a.dir, "README.md")
    if not os.path.exists(rd):
        open(rd, "w").write(README.format(name=os.path.basename(os.path.abspath(a.dir)), produce=produce))
    images = sorted(p for p in glob.glob(os.path.join(a.dir, "imagens", "*")) if p.lower().endswith(IMG_EXT))
    rj = os.path.join(a.dir, "roteiro.json")
    if os.path.exists(rj) and not a.force:
        print(f"roteiro.json já existe (use --force para sobrescrever). Imagens encontradas: {len(images)}")
        return
    sb = template(images if a.from_images else [])
    json.dump(sb, open(rj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✔ Projeto em {a.dir}  ({len(images)} imagens, {len(sb['scenes'])} cenas)")
    print("  Próximo: preencha os TODO do roteiro.json e configure o .env")


if __name__ == "__main__":
    main()
