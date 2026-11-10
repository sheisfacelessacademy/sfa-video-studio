---
name: editar-video
description: Edita automaticamente reels verticais (faceless ou talking-head) com legendas animadas instagramáveis, emojis, zooms, gancho e CTA, decidindo a edição a partir do conteúdo. Usa quando a Maria pedir para editar, legendar ou criar um reel/vídeo, ou disser "faz um vídeo faceless sobre…". PT-PT.
---

# Editar vídeo (SFA Video Studio)

O motor está em `studio.py`. Tu (Claude) és o "editor criativo": lês o conteúdo e escreves o
**plano de edição**. O motor trata do resto (voz, cortes, legendas, emojis, render).

## 1. Perceber o pedido
- **Faceless com roteiro**: a Maria dá um tema ou um texto. Se for só um tema, escreve tu o roteiro
  (20–45 s, ~2,5 palavras/segundo, gancho forte na 1.ª frase, CTA no fim, PT-PT, frases curtas).
  Guarda em `trabalhos/<nome>/roteiro.txt`.
- **Faceless com narração própria**: `--audio narracao.mp3` (+ `--roteiro` se houver texto exato).
- **Talking-head**: `--video bruto.mp4 --cortar-silencios`.
- **B-roll**: se ela der vídeos/imagens, põe numa pasta e usa `--broll pasta/`. Sem b-roll, o motor
  cria um fundo animado com as cores do estilo.
- **Estilo**: `sfa` (bold rosa, viral), `caixa` (caixa roxa na palavra), `elegante` (premium/luxo).
  Para um cliente novo, acrescenta um estilo em `estilos.py` com as cores da marca dele.

## 2. Ler o conteúdo
Se não houver roteiro escrito (talking-head ou áudio), corre primeiro:
`python3 studio.py transcrever <ficheiro>` e lê o texto.

## 3. Escrever o plano (`trabalhos/<nome>/plano.json`)
Decide com base no conteúdo. Não destacar tudo: menos é mais.
```json
{
  "gancho": "Texto curto do topo, 1.os 3 s (máx. 6 palavras, 2 linhas com \n)",
  "destaques": ["4 a 8 palavras-chave: números, promessas, dores, a palavra do CTA"],
  "emojis": {"palavra": "emoji", "...": "3 a 6 no total, só em momentos fortes"},
  "zoom": ["palavras onde dar punch-in (só talking-head)"],
  "cta": "Comenta GUIA"
}
```
Regras: as palavras do plano têm de existir no texto falado (o motor compara sem acentos/pontuação
à palavra, uma a uma). Sem emojis no gancho e no CTA (o libass não os desenha a cores).

## 4. Renderizar
```
python3 studio.py faceless --roteiro trabalhos/X/roteiro.txt --plano trabalhos/X/plano.json --estilo sfa -o trabalhos/X/reel.mp4
```
Voz automática: `--voz raquel` (feminina PT-PT, padrão), `--voz duarte` (masculina) ou `--voz offline`
(local, sem internet). Se a voz online falhar, o motor usa a local sozinho.
Opções úteis: `--musica musica.mp3` (baixa sozinha quando há voz), `--ritmo 2` (cortes de b-roll mais
rápidos), `--velocidade 1.12` (voz mais rápida), `--modelo medium` (transcrição mais exata, mais lenta),
`--enquadramento desfocado` (talking-head horizontal com fundo desfocado).

## 5. Verificar antes de entregar
Extrai 3–4 fotogramas (`ffmpeg -ss T -i reel.mp4 -frames:v 1 f.png`) e olha para eles: legendas legíveis,
nada a sair do ecrã, gancho e CTA visíveis. Depois envia o vídeo à Maria e pergunta se quer ajustes
(estilo, ritmo, destaques, voz).
