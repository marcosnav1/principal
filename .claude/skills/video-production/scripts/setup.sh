#!/usr/bin/env bash
# Instala as dependências da skill de produção de vídeo.
set -u
ok() { printf '  \033[32m✔\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

echo "▶ Python"
python3 -m pip install -q --upgrade numpy pillow edge-tts gTTS 2>/dev/null \
  || python3 -m pip install -q --user numpy pillow edge-tts gTTS \
  || python3 -m pip install -q --break-system-packages numpy pillow edge-tts gTTS
python3 -c "import numpy, PIL" && ok "numpy, pillow" || warn "numpy/pillow falharam"
python3 -c "import edge_tts" 2>/dev/null && ok "edge-tts" || warn "edge-tts indisponível"
python3 -c "import gtts" 2>/dev/null && ok "gTTS" || warn "gTTS indisponível"

install_pkg() {
  if command -v apt-get >/dev/null; then (sudo -n true 2>/dev/null && SUDO=sudo) || SUDO=""
    $SUDO apt-get install -y -q "$@" >/dev/null 2>&1 || { $SUDO apt-get update -q >/dev/null 2>&1; $SUDO apt-get install -y -q "$@" >/dev/null 2>&1; }
  elif command -v brew >/dev/null; then brew install "$@" >/dev/null 2>&1
  fi
}

echo "▶ Sistema"
command -v ffmpeg >/dev/null || install_pkg ffmpeg
command -v ffmpeg >/dev/null && ok "ffmpeg" || warn "instale o ffmpeg (obrigatório)"
command -v espeak-ng >/dev/null || install_pkg espeak-ng
command -v espeak-ng >/dev/null && ok "espeak-ng (voz offline de reserva)" || warn "espeak-ng ausente (opcional)"
command -v fc-match >/dev/null && ok "fontconfig" || warn "fontconfig ausente: defina theme.font com caminho .ttf"

echo "▶ Voz neural (edge-tts)"
TMP=$(mktemp -d)
if timeout 25 edge-tts --voice pt-BR-FranciscaNeural --text "teste" --write-media "$TMP/t.mp3" >/dev/null 2>&1 && [ -s "$TMP/t.mp3" ]; then
  ok "edge-tts conectado"
else
  warn "edge-tts sem acesso à internet: será usado gTTS/espeak (ou defina ELEVENLABS_API_KEY / PIPER_MODEL)"
fi
rm -rf "$TMP"
