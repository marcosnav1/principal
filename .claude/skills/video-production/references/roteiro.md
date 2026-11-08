# Esquema do storyboard (roteiro JSON)

```jsonc
{
  "title": "Nome do vídeo",               // informativo
  "format": "9:16",                        // 9:16 | 16:9 | 1:1 | 4:5 (CLI --format sobrescreve)
  "fps": 30,
  "subtitles": true,                       // false desliga legendas queimadas (o .srt é sempre gerado)
  "sfx_auto": true,                        // efeitos automáticos em transições/bullets/números/botões
  "sfx_volume": 0.6,
  "end_pad": 0.4,                          // segundos extras no final

  "voice": {
    "engine": "auto",                      // auto | edge | elevenlabs | gtts | piper | espeak
    "voice": "pt-BR-FranciscaNeural",      // edge: nome da voz | elevenlabs: voice_id
    "rate": "+0%",                         // velocidade
    "pitch": "+0Hz"                        // só edge
  },

  "music": {
    "mood": "upbeat",                      // upbeat happy corporate inspiring calm lofi epic dramatic tense suspense none
    "file": null,                          // ou caminho para mp3/wav próprio
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
    "progress_bar": true,
    "handle": "@seucanal",
    "logo": "assets/logo.png"
  },

  "scenes": [ /* ver abaixo */ ]
}
```

## Cena

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
| `image` | path | Imagem (relativa ao JSON). |
| `image_mode` | str | `background` (Ken Burns + escurecimento) ou `card` (cartão flutuante). |
| `image_motion` | str | `zoom_in`, `zoom_out`, `pan`. |
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
- `<saida>_work/` — `voice.wav`, `music.wav`, `sfx.wav`, `mix.wav`, `timeline.json`
- `.tts_cache/` (ao lado da saída) — narrações em cache; reexecuções são rápidas
