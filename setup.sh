#!/usr/bin/env bash
# Instala dependências e descarrega os modelos (Whisper + voz PT-PT). Correr uma vez por máquina.
set -e
cd "$(dirname "$0")"
pip install --break-system-packages -q faster-whisper piper-tts edge-tts pillow numpy 2>/dev/null \
  || pip install -q faster-whisper piper-tts edge-tts pillow numpy
mkdir -p models
V="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_PT/tug%C3%A3o/medium/pt_PT-tug%C3%A3o-medium.onnx"
[ -f models/pt_PT-voz.onnx ] || curl -sSL -o models/pt_PT-voz.onnx "$V"
[ -f models/pt_PT-voz.onnx.json ] || curl -sSL -o models/pt_PT-voz.onnx.json "$V.json"
HF_HUB_DISABLE_XET=1 python3 -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
echo "SFA Video Studio pronto."
