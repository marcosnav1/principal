---
name: video-production
description: Produz vídeos completos (MP4) a partir de um tema ou roteiro — narração com voz neural (TTS), animações de texto e fundo, trilha sonora gerada, efeitos sonoros, legendas sincronizadas estilo karaokê, transições, thumbnail e .srt. Use quando o usuário pedir "faça um vídeo", "crie um reels/short/tiktok", "vídeo explicativo", "vídeo com narração", "anúncio em vídeo", "vídeo animado", "video production", ou quiser transformar um texto, roteiro, post ou lista em vídeo. Formatos 9:16, 16:9, 1:1 e 4:5.
---

# Produção de Vídeo (animação + voz + som + legendas)

Pipeline 100% local e programático: **roteiro JSON → narração TTS → linha do tempo
→ animação quadro a quadro (Pillow) → trilha procedural + efeitos (numpy) → ducking
e mixagem → MP4 H.264/AAC normalizado a -14 LUFS**, com `.srt` e thumbnail.

Scripts em `.claude/skills/video-production/scripts/` (abaixo: `$SKILL`).

## Fluxo de trabalho

1. **Entender o pedido** – objetivo, público, plataforma (define o formato), duração
   alvo, tom/voz, idioma, CTA, marca (cores, @handle, logo). Se faltar algo, use padrões
   sensatos e diga quais usou; não trave a produção com perguntas.
2. **Escrever o roteiro** (ver "Boas práticas de roteiro"). Narração ≈ 2,5 palavras/s
   → 30 s ≈ 75 palavras, 60 s ≈ 150 palavras.
3. **Montar o storyboard JSON** – esquema completo em `references/roteiro.md`;
   modelos prontos em `examples/`. Salve-o ao lado dos assets (caminhos relativos ao JSON).
4. **Preparar ambiente** (1ª vez): `bash $SKILL/scripts/setup.sh`
   e confira as vozes: `python3 $SKILL/scripts/produce.py x --list-engines`.
5. **Conferir visual antes do render** – gere quadros-chave e OLHE para eles
   (Read no PNG): `python3 $SKILL/scripts/produce.py roteiro.json -o out/v.mp4 --still 2.5`
   Verifique texto cortado, contraste, sobreposição com a legenda.
6. **Preview rápido** (meia resolução): `... --preview`; **final**: sem `--preview`.
   Vários formatos de uma vez: `--format 9:16,16:9,1:1`.
7. **Validar a saída** – extraia 4–8 quadros com ffmpeg e monte uma folha de contato
   para revisar; cheque loudness (`ffmpeg -i v.mp4 -af ebur128 -f null -`).
8. **Entregar** – MP4, `_thumb.jpg`, `.srt` e a pasta `_work/` (stems voice/music/sfx/mix
   e `timeline.json`). Informe duração, motor de voz usado e como ajustar.

## Voz (TTS)

Ordem automática (`"engine": "auto"`): **ElevenLabs** (se `ELEVENLABS_API_KEY`) →
**edge-tts** (neural, grátis, precisa de internet; fornece tempo de cada palavra →
legenda karaokê exata) → **gTTS** → **Piper** (offline, `PIPER_MODEL=.onnx`) →
**espeak-ng** (offline, robótico — último recurso; avise o usuário se for usado).

Vozes edge recomendadas: `pt-BR-FranciscaNeural`, `pt-BR-AntonioNeural`,
`pt-BR-ThalitaMultilingualNeural`, `pt-PT-RaquelNeural`, `en-US-AndrewMultilingualNeural`,
`en-US-AvaMultilingualNeural`, `es-MX-DaliaNeural`. Lista completa: `edge-tts --list-voices`.
Ajustes: `"rate": "+8%"`, `"pitch": "-2Hz"`. Cada cena pode ter sua própria `voice`
(diálogos, entrevistador/especialista).

Em sandbox sem acesso a `speech.platform.bing.com`, o pipeline cai para espeak
automaticamente; o vídeo sai completo, mas recomende rodar localmente para voz neural.

## Visual

- **Formatos**: `9:16` (1080×1920 Reels/TikTok/Shorts), `16:9` (1920×1080 YouTube),
  `1:1`, `4:5` (feed).
- **Elementos por cena** (combine à vontade, empilhados e centralizados com auto-ajuste
  de tamanho): `kicker` (selo), `image` (fundo Ken Burns ou `image_mode: "card"`),
  `stat` (número contando), `title`, `text`, `quote`+`author`, `bullets` (entram
  sincronizados com a fala), `button` (CTA pulsante).
- **Destaque**: envolva palavras com `**assim**` → cor de destaque.
- **Animações de texto**: `pop`, `up`, `down`, `left`, `right`, `fade`, `zoom`,
  `words` (palavra por palavra), `typewriter`, `none`.
- **Fundos**: `particles`, `bokeh`, `waves`, `grid`, `gradient`, `radial`, `auto`
  (alterna por cena) ou imagem.
- **Transições**: `fade`, `slide`, `slide_up`, `zoom`, `wipe`, `flash`, `none`.
- **Legendas**: `karaoke` (palavra falada destacada), `stroke`, `box`, `none`.
- **Marca**: `palette` [fundo1, fundo2, destaque], `font` (nome fc ou caminho .ttf),
  `handle`, `logo`, `progress_bar`.

## Som

- **Trilha procedural** (sem direitos autorais, muda de tom a cada vídeo):
  `upbeat`, `happy`, `corporate`/`inspiring`, `calm`/`lofi`, `epic`/`dramatic`,
  `tense`/`suspense`, `none`. Ou `"file": "minha-trilha.mp3"` (loop/corte automáticos).
- **Ducking**: a música abaixa sozinha quando há voz (`duck` 0–1, padrão 0.65).
- **Efeitos**: automáticos (whoosh nas transições, pop nos bullets, impacto no número,
  ding no botão) + manuais por cena: `whoosh swoosh pop click ding success coin impact
  riser glitch typing notification` ou caminho para um arquivo.
  Ex.: `"sfx": ["riser", {"name": "coin", "at": 1.2, "volume": 0.9}]`.
- **Master**: limitador suave + loudnorm -14 LUFS / -1.5 dBTP (padrão das redes).

## Boas práticas de roteiro

- **Gancho em ≤ 2 s**: promessa, número ou pergunta ("O 3º quase ninguém faz").
- Uma ideia por cena; cenas de 3–8 s. Texto na tela = resumo, não a narração inteira.
- Frases curtas, voz ativa, números escritos por extenso na narração ("vinte e três")
  e com algarismos na tela (`stat`).
- Ritmo: alterne tipos de cena (título → bullets → número → imagem → citação → CTA).
- Termine com CTA claro (`type: "cta"` + `button`).
- Respeite direitos: use apenas imagens/músicas do usuário, geradas ou livres;
  não imite marcas ou pessoas reais sem autorização.

## Solução de problemas

| Sintoma | Ação |
|---|---|
| Voz robótica | edge-tts sem rede → rode localmente, ou defina `ELEVENLABS_API_KEY` / `PIPER_MODEL` |
| Texto muito pequeno | menos texto por cena (o layout reduz a fonte para caber) |
| Legenda sobre o conteúdo | `theme.subtitle_position` (0–1) ou `"subtitles": false` |
| Música alta | `music.volume` 0.12–0.18 ou `music.duck` 0.8 |
| Render lento | `--preview`, `"fps": 24`, menos partículas (`background: gradient`) |
| Cena curta demais | `"duration": 6` ou `"pause": 1.0` na cena |
