---
name: video-production
description: Produz vídeos completos (MP4) a partir de um tema ou roteiro — narração com voz neural (TTS), animações de texto e fundo, trilha sonora gerada, efeitos sonoros, legendas sincronizadas estilo karaokê, transições, thumbnail e .srt. Use quando o usuário pedir "faça um vídeo", "crie um reels/short/tiktok", "vídeo explicativo", "vídeo com narração", "anúncio em vídeo", "vídeo animado", "video production", ou quiser transformar um texto, roteiro, post ou lista em vídeo. Formatos 9:16, 16:9, 1:1 e 4:5.
---

# Produção de Vídeo (animação + voz + som + legendas)

Pipeline 100% local e programático: **roteiro JSON → narração TTS → linha do tempo
→ animação quadro a quadro (Pillow) → trilha procedural + efeitos (numpy) → ducking
e mixagem → MP4 H.264/AAC normalizado a -14 LUFS**, com `.srt` e thumbnail.

Scripts em `.claude/skills/video-production/scripts/` (abaixo: `$SKILL`).

## Estrutura de projeto (recomendada)

```
python3 $SKILL/scripts/new_project.py meu-video                # pastas + roteiro modelo + .env.example
python3 $SKILL/scripts/new_project.py meu-video --from-images  # 1 cena ilustrada por imagem de imagens/
```
`imagens/` fotos do usuário · `narracao/` voz gravada por cena · `musica/<clima>/` trilhas
licenciadas · `sfx/` efeitos próprios · `.env` chaves de API · `out/` resultados.
Configuração de chaves e bibliotecas: `references/configuracao.md`.

## Dois tipos de cena

- **Animação** (`"kind": "animacao"`): tipografia cinética, números, listas, citações, CTA.
- **Ilustrada** (`"kind": "imagem"`): imagens do usuário com Ken Burns, `focus` no assunto,
  `look` (cinematic, warm, vintage, bw...), várias imagens por cena com crossfade, tarja
  (`lower_third`) e fundo desfocado automático quando a proporção não bate.
Intercale: abertura animada → 2–3 cenas ilustradas → cena animada com a ideia-chave → ... → CTA animado.
Antes de escrever a narração de uma cena ilustrada, OLHE a imagem (Read) e descreva o que ela mostra;
defina `focus` no rosto/assunto principal.

## Projetos com várias vozes / falas prontas

Para personagens (uma voz por fala), gere cada fala separadamente — p.ex. pelo conector ElevenLabs
(`creative_generate_speech`, baixando o mp3 de `elevenlabsusercontent.com`) — salve em
`narracao/NN.mp3` e use `"audio": "narracao/NN"` em cada cena. Com `"target_duration"` o render
mede as falas e fecha a duração exata sem acelerar voz; se não couber, ele avisa quanto sobra para
enxugar o texto. Nunca entregue voz espeak como final.

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

Ordem automática (`"engine": "auto"`): **ElevenLabs** (se `ELEVENLABS_API_KEY`; tempos por
palavra e entonação contínua entre cenas) → **OpenAI** (se `OPENAI_API_KEY`; `instructions` dirige o
tom) → **edge-tts** (neural, grátis, precisa de internet; fornece tempo de cada palavra →
legenda karaokê exata) → **gTTS** → **Piper** (offline, `PIPER_MODEL=.onnx`) →
**espeak-ng** (offline, robótico — último recurso; avise o usuário se for usado).

Vozes edge recomendadas: `pt-BR-FranciscaNeural`, `pt-BR-AntonioNeural`,
`pt-BR-ThalitaMultilingualNeural`, `pt-PT-RaquelNeural`, `en-US-AndrewMultilingualNeural`,
`en-US-AvaMultilingualNeural`, `es-MX-DaliaNeural`. Lista completa: `edge-tts --list-voices`.
Ajustes: `"rate": "+8%"`, `"pitch": "-2Hz"`. Cada cena pode ter sua própria `voice`
(diálogos, entrevistador/especialista).

**Narração gravada**: `"audio": "narracao/cena01.mp3"` na cena — recebe redução de ruído, EQ,
de-esser e compressão; legenda sincronizada se `faster-whisper` estiver instalado.
Toda voz passa por cadeia de tratamento (EQ de presença, de-esser, compressor, limitador).
As chaves podem ficar em `.env` na pasta do roteiro (carregado automaticamente).

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

- **Trilha licenciada (recomendado)**: arquivos em `musica/<mood>/` são escolhidos pelo `mood`;
  ou `"file"`. Estéreo, loop com crossfade. Sem arquivo, cai na trilha sintetizada (qualidade de rascunho).
- **Trilha procedural** (fallback, sem direitos autorais):
  `upbeat`, `happy`, `corporate`/`inspiring`, `calm`/`lofi`, `epic`/`dramatic`,
  `tense`/`suspense`, `none`. Ou `"file": "minha-trilha.mp3"` (loop/corte automáticos).
- **Ducking**: a música abaixa sozinha quando há voz (`duck` 0–1, padrão 0.65).
- **Efeitos**: automáticos (whoosh nas transições, pop nos bullets, impacto no número,
  ding no botão) + manuais por cena: `whoosh swoosh pop click ding success coin impact
  riser glitch typing notification` ou caminho para um arquivo.
  Ex.: `"sfx": ["riser", {"name": "coin", "at": 1.2, "volume": 0.9}]`.
- **Efeitos próprios**: `sfx/whoosh.wav` substitui o whoosh sintetizado (vale para qualquer nome).
- **Master**: estéreo 48 kHz, limitador suave, loudnorm em 2 passadas (-14 LUFS / -1.5 dBTP), AAC 256 kbps.

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
