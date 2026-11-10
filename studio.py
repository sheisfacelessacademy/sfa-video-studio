#!/usr/bin/env python3
"""SFA Video Studio: edição automática de vídeos verticais com legendas animadas.

Modos:
  faceless   roteiro (texto) -> voz PT-PT -> fundo (b-roll ou gradiente) -> legendas
  talking    vídeo gravado -> corta silêncios -> 9:16 -> zooms -> legendas
  transcrever  só gera a transcrição (para o Claude criar o plano de edição)

Exemplos:
  python3 studio.py faceless --roteiro exemplos/roteiro.txt --estilo sfa -o saida/reel.mp4
  python3 studio.py talking --video bruto.mp4 --cortar-silencios --plano plano.json -o saida/reel.mp4
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from estilos import ESTILOS

AQUI = Path(__file__).resolve().parent
LARG, ALT, FPS = 1080, 1920, 30
VOZ = AQUI / "models" / "pt_PT-voz.onnx"
EXT_VIDEO = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
EXT_IMG = {".jpg", ".jpeg", ".png", ".webp"}


# ---------------------------------------------------------------- utilitários
def corre(cmd, silencioso=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-3000:])
        raise SystemExit(f"Falhou: {' '.join(map(str, cmd[:6]))} ...")
    return r


def duracao(ficheiro):
    r = corre(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(ficheiro)])
    return float(r.stdout.strip())


def tem_audio(ficheiro):
    r = corre(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
               "stream=index", "-of", "csv=p=0", str(ficheiro)])
    return bool(r.stdout.strip())


def info(msg):
    print(f"▸ {msg}", flush=True)


def cor_ass(hexa, alpha="00"):
    h = hexa.lstrip("#")
    return f"&H{alpha}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def limpa(palavra):
    return re.sub(r"[^\wÀ-ÿ%€$]", "", palavra.lower())


# ---------------------------------------------------------------- voz e transcrição
def gerar_voz(texto, saida, velocidade=1.0):
    """Texto -> WAV com voz portuguesa (Piper, corre localmente)."""
    from piper import PiperVoice
    from piper.config import SynthesisConfig

    voz = PiperVoice.load(str(VOZ))
    cfg = SynthesisConfig(length_scale=1.0 / velocidade)
    with wave.open(str(saida), "wb") as wf:
        voz.synthesize_wav(texto, wf, syn_config=cfg)


def transcrever(audio, texto_guia=None, modelo="small"):
    """Devolve lista de palavras [{w, s, e}] com tempos ao centésimo."""
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from faster_whisper import WhisperModel

    import numpy as np

    # descodificamos com o ffmpeg (evita incompatibilidades do PyAV)
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-f", "s16le",
                          "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
    som = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(som, language="pt", word_timestamps=True,
                           initial_prompt=texto_guia, vad_filter=True)
    palavras = []
    for seg in segs:
        for w in seg.words:
            t = w.word.strip()
            if t:
                palavras.append({"w": t, "s": round(w.start, 2), "e": round(w.end, 2)})
    if texto_guia:
        palavras = alinhar_com_roteiro(palavras, texto_guia)
    return palavras


def alinhar_com_roteiro(palavras, roteiro):
    """Quando sabemos o texto exato, usamos a grafia do roteiro (sem erros do Whisper)."""
    import difflib

    ref = roteiro.split()
    a = [limpa(p["w"]) for p in palavras]
    b = [limpa(r) for r in ref]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                p = dict(palavras[i1 + k]); p["w"] = ref[j1 + k]; out.append(p)
        elif op == "replace" and i2 > i1:
            s, e = palavras[i1]["s"], palavras[i2 - 1]["e"]
            n = j2 - j1
            for k in range(n):
                out.append({"w": ref[j1 + k], "s": round(s + (e - s) * k / n, 2),
                            "e": round(s + (e - s) * (k + 1) / n, 2)})
        elif op == "delete":
            out.extend(palavras[i1:i2])
        # "insert": palavras do roteiro que não se ouviram -> ignorar
    return out


# ---------------------------------------------------------------- plano de edição
PALAVRAS_FORTES = {
    "dinheiro": "💸", "euros": "💶", "€": "💶", "grátis": "🎁", "segredo": "🤫",
    "erro": "❌", "erros": "❌", "nunca": "🚫", "sempre": "✅", "rápido": "⚡",
    "crescer": "📈", "cresce": "📈", "vendas": "💰", "vender": "💰", "clientes": "🤝",
    "instagram": "📱", "conteúdo": "🎬", "conteúdos": "🎬", "ideia": "💡",
    "ideias": "💡", "tempo": "⏰", "casa": "🏡", "liberdade": "🕊️", "sonho": "✨",
    "atenção": "👀", "importante": "❗", "amor": "💖", "rosto": "🙈",
    "aparecer": "🙈", "faceless": "🎭", "ia": "🤖", "comenta": "💬", "segue": "👉",
}


def plano_automatico(palavras):
    """Plano simples quando o Claude não fez um: destaca números e palavras fortes."""
    destaques, emojis = [], {}
    for p in palavras:
        c = limpa(p["w"])
        if re.search(r"\d", c) or c in PALAVRAS_FORTES:
            destaques.append(c)
        if c in PALAVRAS_FORTES and len(emojis) < 6 and c not in emojis:
            emojis[c] = PALAVRAS_FORTES[c]
    return {"gancho": None, "destaques": destaques, "emojis": emojis,
            "zoom": destaques[:], "cta": None}


def carregar_plano(caminho, palavras):
    base = plano_automatico(palavras)
    if caminho:
        dado = json.loads(Path(caminho).read_text(encoding="utf-8"))
        base.update({k: v for k, v in dado.items() if v is not None})
    base["destaques"] = {limpa(x) for x in base.get("destaques", [])}
    base["emojis"] = {limpa(k): v for k, v in base.get("emojis", {}).items()}
    base["zoom"] = {limpa(x) for x in base.get("zoom", [])}
    return base


# ---------------------------------------------------------------- legendas ASS
def paginas(palavras, maximo):
    """Agrupa palavras em "ecrãs" curtos, quebrando em pausas e pontuação."""
    out, atual = [], []
    for i, p in enumerate(palavras):
        atual.append(p)
        prox = palavras[i + 1] if i + 1 < len(palavras) else None
        pausa = prox and prox["s"] - p["e"] > 0.35
        pontuacao = p["w"][-1] in ".,!?;:"
        chars = sum(len(x["w"]) for x in atual)
        if len(atual) >= maximo or pausa or pontuacao or chars > 16 or not prox:
            # não deixar "a", "o", "e", "de"... pendurados no fim de um ecrã
            if prox and not pausa and not pontuacao and len(atual) > 1 and len(limpa(p["w"])) <= 2:
                atual.pop(); out.append(atual); atual = [p]
                continue
            out.append(atual); atual = []
    return out


def sem_emoji(txt):
    """O libass não desenha emojis a cores: no gancho/CTA ficam de fora."""
    return re.sub(r"[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F]", "", txt).strip()


def ts(t):
    t = max(0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def gerar_ass(palavras, plano, est, dur, saida):
    up = (lambda s: s.upper()) if est["maiusculas"] else (lambda s: s)
    branco, ativa = cor_ass(est["cor_texto"]), cor_ass(est["cor_ativa"])
    destaque = cor_ass(est["cor_destaque"])
    caixa = est.get("caixa_ativa")
    linhas = []

    for pag in paginas(palavras, est["palavras_por_ecra"]):
        fim_pag = pag[-1]["e"] + 0.12
        for k, atual in enumerate(pag):
            ini = atual["s"] if k else max(0, atual["s"] - 0.05)
            fim = pag[k + 1]["s"] if k + 1 < len(pag) else fim_pag
            partes = []
            for j, p in enumerate(pag):
                txt = up(p["w"]).replace("{", "").replace("}", "")
                eh_dest = limpa(p["w"]) in plano["destaques"]
                if j == k:
                    tags = f"\\c{destaque if eh_dest else ativa}"
                    if caixa:
                        tags += f"\\3c{cor_ass(caixa)}\\bord{est['contorno'] + 14}"
                    if est["pop"]:
                        tags += "\\fscx88\\fscy88\\t(0,90,\\fscx112\\fscy112)\\t(90,170,\\fscx104\\fscy104)"
                    partes.append(f"{{{tags}}}{txt}{{\\r}}")
                else:
                    cor = destaque if eh_dest else branco
                    partes.append(f"{{\\c{cor}}}{txt}{{\\r}}")
            entrada = "{\\fad(60,0)}" if k == 0 else ""
            if est.get("desfoque"):
                entrada += f"{{\\blur{est['desfoque']}}}"
            linhas.append(f"Dialogue: 1,{ts(ini)},{ts(fim)},Leg,,0,0,0,,{entrada}{' '.join(partes)}")

    if plano.get("gancho"):
        g = sem_emoji(plano["gancho"]).replace("\n", "\\N")
        linhas.append(f"Dialogue: 2,{ts(0)},{ts(min(3.0, dur))},Gancho,,0,0,0,,"
                      f"{{\\fad(0,250)\\fscx90\\fscy90\\t(0,150,\\fscx100\\fscy100)}}{g}")
    if plano.get("cta"):
        c = sem_emoji(plano["cta"]).replace("\n", "\\N")
        linhas.append(f"Dialogue: 2,{ts(max(0, dur - 3.2))},{ts(dur)},CTA,,0,0,0,,"
                      f"{{\\fad(200,0)\\fscx80\\fscy80\\t(0,200,\\fscx100\\fscy100)}}{c}")

    sombra_cor = cor_ass("#000000", "60")
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {LARG}
PlayResY: {ALT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Leg,{est['fonte']},{est['tamanho']},{branco},{branco},{cor_ass(est['cor_contorno'])},{sombra_cor},0,0,0,0,100,100,1,0,1,{est['contorno']},{est['sombra']},2,70,70,{est['posicao_v']},1
Style: Gancho,{est['fonte']},74,{cor_ass('#111111')},{branco},{cor_ass('#FFFFFF')},{cor_ass('#FFFFFF')},0,0,0,0,100,100,0,0,3,22,0,8,90,90,260,1
Style: CTA,{est['fonte']},70,{branco},{branco},{cor_ass(est['barra_progresso'])},{cor_ass(est['barra_progresso'])},0,0,0,0,100,100,0,0,3,26,0,5,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    Path(saida).write_text(cab + "\n".join(linhas) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- emojis
def emoji_png(emoji, saida, tam=150):
    from PIL import Image, ImageDraw, ImageFont

    f = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)
    img = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((80, 80), emoji, font=f, embedded_color=True, anchor="mm")
    img = img.crop(img.getbbox() or (0, 0, 160, 160)).resize((tam, tam), Image.LANCZOS)
    img.save(saida)


def eventos_emoji(palavras, plano, tmp):
    eventos, usados = [], set()
    for i, p in enumerate(palavras):
        c = limpa(p["w"])
        if c in plano["emojis"] and c not in usados:
            usados.add(c)
            png = tmp / f"emoji_{len(eventos)}.png"
            emoji_png(plano["emojis"][c], png)
            eventos.append((png, p["s"], p["s"] + 1.4))
    return eventos


# ---------------------------------------------------------------- fundos e b-roll
def fundo_gradiente(cores, dur, saida):
    c0, c1, c2 = cores
    corre(["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"gradients=s={LARG}x{ALT}:r={FPS}:d={dur:.2f}:c0={c0}:c1={c1}:c2={c2}:"
           f"nb_colors=3:speed=0.012:type=radial",
           "-vf", "noise=alls=6:allf=t,format=yuv420p",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(saida)])


def montar_broll(pasta, dur, saida, tmp, ritmo=2.8):
    """Corta b-roll em pedaços de ~ritmo segundos (estilo reel), com Ken Burns nas imagens."""
    ficheiros = sorted(p for p in Path(pasta).iterdir()
                       if p.suffix.lower() in EXT_VIDEO | EXT_IMG)
    if not ficheiros:
        raise SystemExit(f"Não há vídeos/imagens em {pasta}")
    pedacos, t, i = [], 0.0, 0
    cobrir = f"scale={LARG}:{ALT}:force_original_aspect_ratio=increase,crop={LARG}:{ALT}"
    while t < dur:
        f = ficheiros[i % len(ficheiros)]
        d = min(ritmo, dur - t) + 0.05
        out = tmp / f"broll_{i:03d}.mp4"
        if f.suffix.lower() in EXT_IMG:
            frames = int(d * FPS) + 1
            z = "min(zoom+0.0009,1.12)" if i % 2 == 0 else "if(eq(on,0),1.12,max(zoom-0.0009,1))"
            vf = (f"scale={LARG * 2}:{ALT * 2}:force_original_aspect_ratio=increase,"
                  f"crop={LARG * 2}:{ALT * 2},zoompan=z='{z}':d={frames}:"
                  f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':s={LARG}x{ALT}:fps={FPS}")
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(f), "-t", f"{d:.2f}", "-vf", vf]
        else:
            fd = duracao(f)
            inicio = random.uniform(0, max(0, fd - d)) if fd > d else 0
            cmd = ["ffmpeg", "-y", "-ss", f"{inicio:.2f}", "-stream_loop", "-1", "-i", str(f),
                   "-t", f"{d:.2f}", "-vf", f"{cobrir},fps={FPS}"]
        cmd += ["-an", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", str(out)]
        corre(cmd)
        pedacos.append(out); t += d - 0.05; i += 1
    lista = tmp / "lista.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in pedacos))
    corre(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
           "-vf", "eq=brightness=-0.06:saturation=1.1", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "20", str(saida)])


# ---------------------------------------------------------------- talking head
def cortar_silencios(entrada, saida, limiar="-35dB", minimo=0.45, folga=0.12):
    r = subprocess.run(["ffmpeg", "-i", str(entrada), "-af",
                        f"silencedetect=noise={limiar}:d={minimo}", "-f", "null", "-"],
                       capture_output=True, text=True)
    ini = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    fim = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    total = duracao(entrada)
    manter, cursor = [], 0.0
    for s, e in zip(ini, fim + [total] * (len(ini) - len(fim))):
        if s - cursor > 0.05:
            manter.append((max(0, cursor - folga), min(total, s + folga)))
        cursor = e
    if total - cursor > 0.05:
        manter.append((max(0, cursor - folga), total))
    if not manter:
        shutil.copy(entrada, saida); return 0
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in manter)
    corre(["ffmpeg", "-y", "-i", str(entrada),
           "-vf", f"select='{expr}',setpts=N/FRAME_RATE/TB",
           "-af", f"aselect='{expr}',asetpts=N/SR/TB",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(saida)])
    return total - sum(b - a for a, b in manter)


def reenquadrar(entrada, saida, palavras, plano, modo="preencher"):
    """Põe em 9:16 (com fundo desfocado se for horizontal) e faz 'punch-in' nas palavras-chave."""
    zooms = [(p["s"], p["s"] + 1.6) for p in palavras if limpa(p["w"]) in plano["zoom"]]
    fator = "1"
    if zooms:
        soma = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in zooms[:40])
        fator = f"(1+0.10*min(1,{soma}))"
    corre(["ffmpeg", "-y", "-i", str(entrada), "-filter_complex",
           (f"[0:v]fps={FPS},scale={LARG}:{ALT}:force_original_aspect_ratio=increase,"
            f"crop={LARG}:{ALT},"
            f"crop=w='iw/{fator}':h='ih/{fator}':x='(iw-ow)/2':y='(ih-oh)/2',"
            f"scale={LARG}:{ALT},setsar=1,format=yuv420p[v]") if modo == "preencher" else
           f"[0:v]fps={FPS},split[a][b];"
           f"[a]scale={LARG}:{ALT}:force_original_aspect_ratio=increase,crop={LARG}:{ALT},"
           f"boxblur=30:2,eq=brightness=-0.1[fundo];"
           f"[b]scale={LARG}:{ALT}:force_original_aspect_ratio=decrease[frente];"
           f"[fundo][frente]overlay=(W-w)/2:(H-h)/2,"
           f"crop=w='iw/{fator}':h='ih/{fator}':x='(iw-ow)/2':y='(ih-oh)/2',"
           f"scale={LARG}:{ALT},setsar=1,format=yuv420p[v]",
           "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "18", "-c:a", "aac", str(saida)])


# ---------------------------------------------------------------- composição final
def compor(video, voz, ass, emojis, musica, dur, est, saida, tmp):
    entradas = ["-i", str(video), "-i", str(voz)]
    for png, _, _ in emojis:
        entradas += ["-i", str(png)]
    idx_musica = None
    if musica:
        idx_musica = 2 + len(emojis)
        entradas += ["-stream_loop", "-1", "-i", str(musica)]
    entradas += ["-f", "lavfi", "-i", f"color=c={est['barra_progresso']}:s={LARG}x10:r={FPS}"]
    idx_barra = 2 + len(emojis) + (1 if musica else 0)

    assp = str(ass).replace(":", "\\:")
    f = [f"[0:v]ass='{assp}'[v0]"]
    ult = "v0"
    for i, (_, a, b) in enumerate(emojis):
        # emoji aparece por cima das legendas com um pequeno "salto"
        y = ALT - est["posicao_v"] - est["tamanho"] - 190
        f.append(f"[{ult}][{2 + i}:v]overlay=x=(W-w)/2:"
                 f"y='{y}-30*max(0,1-(t-{a:.2f})*6)':enable='between(t,{a:.2f},{b:.2f})'[e{i}]")
        ult = f"e{i}"
    f.append(f"[{ult}][{idx_barra}:v]overlay=x='-w+w*t/{dur:.2f}':y=0:shortest=1[vout]")
    if musica:
        f.append(f"[1:a]asplit[voz][chave];[{idx_musica}:a]volume=0.22[m];"
                 f"[m][chave]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[mduck];"
                 f"[voz][mduck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[aout]")
    else:
        f.append("[1:a]loudnorm=I=-14:TP=-1.5[aout]")

    Path(saida).parent.mkdir(parents=True, exist_ok=True)
    corre(["ffmpeg", "-y", *entradas, "-filter_complex", ";".join(f),
           "-map", "[vout]", "-map", "[aout]", "-t", f"{dur:.2f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(saida)])


# ---------------------------------------------------------------- comandos
def cmd_faceless(a):
    est = ESTILOS[a.estilo]
    tmp = Path(tempfile.mkdtemp(prefix="studio_"))
    if a.audio:
        voz = Path(a.audio)
        roteiro = Path(a.roteiro).read_text(encoding="utf-8").strip() if a.roteiro else None
    else:
        roteiro = Path(a.roteiro).read_text(encoding="utf-8").strip()
        voz = tmp / "voz.wav"
        info("A gerar a narração em português de Portugal…")
        gerar_voz(roteiro, voz, a.velocidade)
    dur = duracao(voz) + 0.4
    info("A transcrever com tempos palavra a palavra…")
    palavras = transcrever(voz, roteiro, a.modelo)
    guardar_transcricao(palavras, a.saida)
    plano = carregar_plano(a.plano, palavras)
    fundo = tmp / "fundo.mp4"
    if a.broll:
        info("A montar o b-roll com cortes dinâmicos…")
        montar_broll(a.broll, dur, fundo, tmp, a.ritmo)
    else:
        info("A criar fundo animado com as cores da marca…")
        fundo_gradiente(est["fundo"], dur, fundo)
    finalizar(fundo, voz, palavras, plano, est, dur, a, tmp)


def cmd_talking(a):
    est = ESTILOS[a.estilo]
    tmp = Path(tempfile.mkdtemp(prefix="studio_"))
    base = Path(a.video)
    if a.cortar_silencios:
        info("A cortar silêncios e pausas…")
        cortado = tmp / "cortado.mp4"
        poupado = cortar_silencios(base, cortado)
        info(f"  {poupado:.1f}s de silêncio removidos")
        base = cortado
    voz = tmp / "voz.wav"
    corre(["ffmpeg", "-y", "-i", str(base), "-vn", "-ac", "1", "-ar", "16000", str(voz)])
    info("A transcrever…")
    palavras = transcrever(voz, Path(a.roteiro).read_text(encoding="utf-8") if a.roteiro else None,
                           a.modelo)
    guardar_transcricao(palavras, a.saida)
    plano = carregar_plano(a.plano, palavras)
    info("A reenquadrar para 9:16 com zooms nas palavras-chave…")
    vert = tmp / "vertical.mp4"
    reenquadrar(base, vert, palavras, plano, a.enquadramento)
    voz_full = tmp / "voz_full.wav"
    corre(["ffmpeg", "-y", "-i", str(vert), "-vn", "-ar", "48000", str(voz_full)])
    finalizar(vert, voz_full, palavras, plano, est, duracao(vert), a, tmp)


def finalizar(fundo, voz, palavras, plano, est, dur, a, tmp):
    info("A desenhar legendas animadas, emojis e barra de progresso…")
    ass = tmp / "legendas.ass"
    gerar_ass(palavras, plano, est, dur, ass)
    emojis = eventos_emoji(palavras, plano, tmp) if not a.sem_emojis else []
    compor(fundo, voz, ass, emojis, a.musica, dur, est, a.saida, tmp)
    shutil.copy(ass, Path(a.saida).with_suffix(".ass"))
    if not a.manter_temp:
        shutil.rmtree(tmp, ignore_errors=True)
    info(f"Pronto: {a.saida}  ({dur:.1f}s)")


def guardar_transcricao(palavras, saida):
    p = Path(saida).with_suffix(".transcricao.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(palavras, ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_transcrever(a):
    tmp = Path(tempfile.mkdtemp(prefix="studio_"))
    voz = tmp / "voz.wav"
    corre(["ffmpeg", "-y", "-i", a.ficheiro, "-vn", "-ac", "1", "-ar", "16000", str(voz)])
    palavras = transcrever(voz)
    texto = " ".join(p["w"] for p in palavras)
    out = Path(a.saida or Path(a.ficheiro).with_suffix(".transcricao.json"))
    out.write_text(json.dumps(palavras, ensure_ascii=False, indent=1), encoding="utf-8")
    print(texto)
    info(f"Transcrição em {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="modo", required=True)

    def comuns(p):
        p.add_argument("--estilo", default="sfa", choices=list(ESTILOS))
        p.add_argument("--plano", help="JSON com gancho, destaques, emojis, zoom, cta")
        p.add_argument("--musica", help="música de fundo (baixa sozinha quando há voz)")
        p.add_argument("--sem-emojis", action="store_true")
        p.add_argument("--manter-temp", action="store_true")
        p.add_argument("--modelo", default="small", help="Whisper: small (rápido) ou medium (mais exato)")
        p.add_argument("-o", "--saida", default="saida/reel.mp4")

    f = sub.add_parser("faceless", help="roteiro/narração + b-roll ou fundo animado")
    f.add_argument("--roteiro", help="ficheiro .txt com o texto")
    f.add_argument("--audio", help="narração já gravada (em vez da voz automática)")
    f.add_argument("--broll", help="pasta com vídeos/imagens")
    f.add_argument("--ritmo", type=float, default=2.8, help="segundos por corte de b-roll")
    f.add_argument("--velocidade", type=float, default=1.08, help="velocidade da voz automática")
    comuns(f)
    f.set_defaults(func=cmd_faceless)

    t = sub.add_parser("talking", help="vídeo gravado a falar para a câmara")
    t.add_argument("--video", required=True)
    t.add_argument("--roteiro", help="texto exato (opcional, melhora a grafia)")
    t.add_argument("--cortar-silencios", action="store_true")
    t.add_argument("--enquadramento", default="preencher", choices=["preencher", "desfocado"],
                   help="preencher = corta para 9:16; desfocado = vídeo inteiro com fundo desfocado")
    comuns(t)
    t.set_defaults(func=cmd_talking)

    tr = sub.add_parser("transcrever", help="só gera a transcrição palavra a palavra")
    tr.add_argument("ficheiro")
    tr.add_argument("-o", "--saida")
    tr.set_defaults(func=cmd_transcrever)

    a = ap.parse_args()
    if a.modo == "faceless" and not (a.roteiro or a.audio):
        ap.error("faceless precisa de --roteiro ou --audio")
    a.func(a)


if __name__ == "__main__":
    main()
