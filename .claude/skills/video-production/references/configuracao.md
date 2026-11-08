# Configuração: o que conectar para qualidade profissional

## 1. Voz (maior impacto na qualidade)

| Opção | Qualidade | Custo | Como ativar |
|---|---|---|---|
| **ElevenLabs** | ★★★★★ voz humana, emoção, tempos por palavra | pago por caractere | `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` no `.env` |
| **OpenAI TTS** (`gpt-4o-mini-tts`) | ★★★★ dirigível por instruções | baixo | `OPENAI_API_KEY` no `.env`; `voice.instructions` |
| **edge-tts** | ★★★½ neural, grátis | grátis | só internet (já instalado pelo `setup.sh`) |
| **Sua própria voz** | ★★★★★ autêntica | grátis | grave por cena em `narracao/` e use `"audio"` |
| Piper | ★★★ offline | grátis | `pip install piper-tts` + `PIPER_MODEL=voz.onnx` |
| espeak | ★ robótica | grátis | último recurso automático |

ElevenLabs: crie a chave em elevenlabs.io → Profile → API Keys. Escolha/clone uma voz na
Voice Library e copie o *Voice ID*. Modelo padrão `eleven_multilingual_v2` (ótimo em pt-BR).

Gravação própria: microfone a 10–15 cm, ambiente sem eco (quarto com cortinas/roupas),
WAV 48 kHz, um arquivo por cena (`narracao/cena01.wav`). Para legenda sincronizada:
`pip install faster-whisper` (baixa o modelo na 1ª execução).

## 2. Música

A trilha sintetizada serve para rascunho. Para o vídeo final, use trilhas licenciadas:
- YouTube Audio Library (grátis, uso no YouTube), Pixabay Music (grátis), Uppbeat, Artlist/Epidemic (pagos, licença para redes).
- Organize por clima: `musica/calm/`, `musica/upbeat/`, `musica/epic/`... — o roteiro escolhe pelo `music.mood`.
- Guarde o comprovante/licença de cada trilha.

## 3. Efeitos sonoros

Coloque arquivos com o nome do efeito em `sfx/` (`whoosh.wav`, `pop.wav`, `ding.wav`, `impact.wav`,
`riser.wav`, `click.wav`, `coin.wav`...). Fontes: Pixabay SFX, Freesound (CC0), Zapsplat.

## 4. Imagens

Fotos em `imagens/`, nomeadas na ordem (`01_...jpg`). Resolução mínima recomendada:
1080 px no lado menor (vertical 9:16 ideal: 1080×1920 ou maior). Use apenas imagens suas,
licenciadas ou geradas por você. O nome do arquivo vira legenda sugerida em `--from-images`.

## 5. Ambiente

`bash scripts/setup.sh` instala numpy, pillow, edge-tts, gTTS, ffmpeg e espeak-ng.
Opcional: `pip install faster-whisper`. As chaves ficam em `.env` (nunca faça commit desse arquivo).
