# SFA Video Studio

Editor automático de reels verticais (1080×1920) com legendas animadas palavra a palavra,
emojis, zooms, gancho, CTA, barra de progresso e música com ducking. Tudo corre localmente
(FFmpeg + Whisper), sem custos por vídeo. Voz automática feminina PT-PT (Raquel) gratuita.

## Instalar
```bash
./setup.sh
```

## Usar
```bash
# Faceless: roteiro -> voz PT-PT -> fundo animado -> legendas
python3 studio.py faceless --roteiro exemplos/roteiro.txt --plano exemplos/plano.json -o saida/reel.mp4

# Faceless com b-roll e música
python3 studio.py faceless --roteiro roteiro.txt --broll pasta_broll/ --musica musica.mp3 --estilo caixa

# Talking-head: corta silêncios, põe em 9:16, zooms nas palavras-chave
python3 studio.py talking --video bruto.mp4 --cortar-silencios --plano plano.json

# Só transcrever
python3 studio.py transcrever bruto.mp4
```

No Claude Code, basta pedir *"faz um reel faceless sobre X"*: a skill `editar-video`
(`.claude/skills/editar-video/SKILL.md`) escreve o roteiro e o plano de edição a partir do conteúdo
e corre o motor.

Estilos em `estilos.py` (`sfa`, `caixa`, `elegante`). Para acrescentar uma marca nova, copia um bloco.
