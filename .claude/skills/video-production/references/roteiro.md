# Esquema do storyboard (roteiro JSON)

```jsonc
{
  "title": "Nome do vídeo",               // informativo
  "format": "9:16",                        // 9:16 | 16:9 | 1:1 | 4:5 (CLI --format sobrescreve)
  "fps": 30,
  "subtitles": true,                       // false desliga legendas queimadas (o .srt é sempre gerado)
  "sfx_auto": true,                        // efeitos automáticos em transições/bullets/números/botões
  "sfx_volume": 0.6,
  "sfx_library": "sfx",                    // sfx/<nome>.wav substitui o efeito sintetizado de mesmo nome
  "end_pad": 0.4,                          // segundos extras no final

  "loudness": -14,
  "target_duration": 120.0,                // fecha a duração exata: mede as falas e distribui a folga nas pausas
  "thumbnail": "imagens/01.png",           // thumbnail a partir de uma imagem (senão, quadro da 1ª cena)                         // LUFS final (-14 redes sociais, -16 podcast, -23 TV)

  "voice": {
    "engine": "auto",                      // auto | elevenlabs | openai | edge | gtts | piper | espeak
    "voice": "pt-BR-FranciscaNeural",      // edge: nome | elevenlabs: voice_id | openai: onyx, nova, coral...
    "rate": "+0%",                         // velocidade
    "pitch": "+0Hz",                       // só edge
    "instructions": "Tom acolhedor...",    // só openai: direção de atuação da voz
    "model": null,                         // elevenlabs: eleven_multilingual_v2 | openai: gpt-4o-mini-tts
    "settings": { "stability": 0.45 },     // só elevenlabs: voice_settings
    "polish": "tts",                       // cadeia de tratamento: tts | gravacao | nenhum | filtro ffmpeg
    "recording_polish": "gravacao"         // tratamento das narrações gravadas (campo "audio" da cena)
  },

  "music": {
    "mood": "upbeat",                      // upbeat happy corporate inspiring calm lofi epic dramatic tense suspense violao none
    "file": null,                          // trilha específica (mp3/wav/m4a)
    "library": "musica",                   // pasta de trilhas: musica/<mood>/*.mp3 é escolhida pelo mood
    "start": 0,                            // começar a trilha em N segundos
    "delay_scene": 2,                      // a trilha entra só nesta cena (opcional)
    "volume": 0.22,                        // 0..1 (sob a voz)
    "duck": 0.65,                          // quanto abaixa durante a fala
    "bpm": null,                           // opcional
    "seed": 3                              // muda tonalidade/arpejo
  },

  "theme": {
    "palette": ["#0f172a", "#312e81", "#facc15"],  // fundo1, fundo2, destaque
    "accent": null,                        // sobrescreve o destaque
    "text_color": null,                    // auto pelo contraste
    "font": "Inter",                       // nome (fc-match) ou caminho .ttf/.otf
    "body_font": null,
    "background": "particles",             // particles bokeh waves grid gradient radial auto
    "transition": "fade",                  // fade slide slide_up zoom wipe flash none
    "subtitle_style": "karaoke",           // karaoke stroke box none
    "subtitle_color": null,                // cor da palavra ativa (padrão: destaque)
    "subtitle_position": null,             // 0..1 da altura (padrão 0.80 vertical / 0.87 horizontal)
    "subtitle_size": null,                 // fração da largura (ex. 0.054)
    "subtitle_max_words": null,            // por bloco (até 2 linhas); padrão 4 vertical / 7 horizontal
    "subtitle_max_chars": null,            // por bloco; padrão 26 / 44
    "progress_bar": true,
    "handle": "@seucanal",
    "logo": "assets/logo.png"
  },

  "scenes": [ /* ver abaixo */ ]
}
```

## Dois tipos de cena

- **`"kind": "animacao"`** – tipografia cinética, números, listas, citações e botões sobre fundos animados.
- **`"kind": "imagem"`** – cena ilustrada por SUAS imagens (`images`), com movimento de câmera
  (Ken Burns), correção de cor (`look`), enquadramento inteligente e texto/tarja por cima.

### Campos exclusivos de cenas `imagem`

| Campo | Tipo | Descrição |
|---|---|---|
| `images` | [str \| obj] | Uma ou mais imagens; várias = sequência com crossfade dentro da cena. Objeto: `{ "path", "motion", "focus", "fit", "look", "duration", "zoom" }` |
| `motion` | str | `auto` (alterna), `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `static` |
| `focus` | [x, y] | Ponto de interesse 0–1 (ex. rosto em `[0.5, 0.35]`): o zoom vai até ele e o corte o preserva |
| `fit` | str | `cover` (preenche), `contain` (foto inteira + fundo desfocado), `auto` (decide pela proporção) |
| `look` | str | `none`, `warm`, `cool`, `vintage`, `bw`, `cinematic`, `vivid`, `matte` (padrão: `theme.look`) |
| `zoom` | float | Intensidade do movimento (1.0 padrão; 0.5 sutil; 1.5 forte) |
| `shade` | str | Escurecimento p/ leitura: `bottom`, `top`, `both`, `full`, `none` |
| `lower_third` | str \| obj | Tarja: `{ "title": "Nome", "subtitle": "Lugar, ano", "at": 0.6 }` |
| `audio` | path | Narração GRAVADA ou gerada fora (ex. ElevenLabs) para a cena; extensão opcional (`narracao/01` acha 01.mp3/.wav). Legenda sincronizada pelas pausas reais do áudio |
| `subtitle_position` | float | Altura da legenda só nesta cena (desviar de objetos importantes) |
| `lock_duration` | bool | Com `target_duration`, esta cena não recebe folga (ex. reação final de 0,5 s) |
| `lower_third.y` | float | Altura da tarja (ex. 0.055 = canto superior) |

Texto comum (`title`, `text`, `kicker`, `quote`...) também funciona sobre as imagens;
use `text_position: "top"` quando o assunto da foto estiver no centro/baixo.

## Cena (campos gerais)

Todos os campos são opcionais; combine os que quiser. Ordem de empilhamento na tela:
kicker → image(card) → stat → title → text → quote/author → bullets → button.

| Campo | Tipo | Descrição |
|---|---|---|
| `narration` | str | Texto falado. Define a duração da cena. `**` é removido antes do TTS. |
| `type` | str | `title` (título maior + impacto) ou `cta`; demais são livres. |
| `kicker` | str | Selo pequeno em caixa alta acima do título. |
| `title` | str | Título. `**palavra**` = cor de destaque. |
| `title_anim` | str | pop up down left right fade zoom words typewriter none |
| `text` | str | Texto de apoio. |
| `text_anim` | str | padrão `words` (palavra por palavra). |
| `text_weight` | str | `regular` para texto mais leve. |
| `bullets` | [str] | Itens que entram sincronizados com a narração. |
| `bullet_style` | str | `check` ou `number`. |
| `bullet_times` | [float] | Tempos manuais (s, relativos à cena). |
| `stat` | num / obj | `{ "value": 87, "prefix": "R$ ", "suffix": "%", "decimals": 0, "sfx": "impact" }` |
| `quote`, `author` | str | Citação em itálico com aspas. |
| `button` | str | Botão CTA pulsante (toca "ding"). |
| `image` | path | Imagem única (legado; prefira `kind: "imagem"` + `images`). |
| `image_mode` | str | `background` (vira cena ilustrada) ou `card` (cartão flutuante numa cena animada). |
| `image_motion` | str | `zoom_in`, `zoom_out`, `pan`. |
| `text_position` | str | `top`, `center`, `low`, `bottom` (sobre fotos, `top` escurece o céu/topo). |
| `card_height` | float | Altura máx. do cartão de imagem (fração da área, padrão 0.45). |
| `background` | str | Fundo desta cena. |
| `colors` | [hex] | Gradiente desta cena (2–3 cores). |
| `accent`, `text_color` | hex | Cores desta cena. |
| `transition` | str | Transição de ENTRADA desta cena. |
| `transition_duration` | float | padrão 0.45 s. |
| `voice` | obj | Sobrescreve `voice` global (diálogos). |
| `voice_delay` | float | Silêncio antes da fala (padrão 0.45 na 1ª cena, 0.3 nas demais). |
| `pause` | float | Silêncio após a fala (padrão 0.55). |
| `duration` | float | Duração mínima (cenas sem narração: padrão 3 s). |
| `sfx` | list | `"riser"` ou `{ "name": "coin", "at": 1.2, "volume": 0.8 }`; nome ou caminho de arquivo. |

## Saídas

- `<saida>.mp4` — H.264 yuv420p + AAC 48 kHz, -14 LUFS, faststart
- `<saida>.srt` — legendas
- `<saida>_thumb.jpg` — thumbnail (1ª cena)
- `<saida>_work/` — `voice.wav`, `music.wav`, `sfx.wav`, `mix_bruto.wav`, `mix.wav` (normalizado), `timeline.json`
- Áudio: AAC 256 kbps, 48 kHz estéreo, loudness em 2 passadas (±0,3 LU do alvo)
- `.tts_cache/` (ao lado da saída) — narrações em cache; reexecuções são rápidas
