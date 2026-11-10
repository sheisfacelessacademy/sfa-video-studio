"""Estilos de legendas e de marca.

Cores em hexadecimal normal (#RRGGBB). O motor converte-as para o formato ASS.
Para criar um estilo novo, copia um bloco, muda o nome e ajusta.
"""

ESTILOS = {
    # Bold, maiúsculas, palavra ativa rosa com "pop". O clássico dos reels virais.
    "sfa": {
        "fonte": "Inter Display Black",
        "tamanho": 92,
        "maiusculas": True,
        "palavras_por_ecra": 3,
        "cor_texto": "#FFFFFF",
        "cor_ativa": "#FF4FA3",       # palavra a ser dita
        "cor_destaque": "#FFD84D",    # palavras-chave do plano
        "contorno": 7,
        "cor_contorno": "#000000",
        "sombra": 4,
        "posicao_v": 620,             # distância ao fundo do ecrã (px)
        "pop": True,
        "fundo": ("#1A0B2E", "#FF4FA3", "#5B2A86"),  # gradiente do modo faceless
        "barra_progresso": "#FF4FA3",
    },
    # Caixa colorida atrás da palavra ativa, estilo "karaoke".
    "caixa": {
        "fonte": "Inter Display ExtraBold",
        "tamanho": 84,
        "maiusculas": False,
        "palavras_por_ecra": 3,
        "cor_texto": "#FFFFFF",
        "cor_ativa": "#FFFFFF",
        "caixa_ativa": "#7C3AED",
        "cor_destaque": "#FFD84D",
        "contorno": 6,
        "cor_contorno": "#000000",
        "sombra": 0,
        "posicao_v": 620,
        "pop": True,
        "fundo": ("#0F172A", "#7C3AED", "#0EA5E9"),
        "barra_progresso": "#7C3AED",
    },
    # Minimalista e elegante (premium, imobiliário de luxo).
    "elegante": {
        "fonte": "Inter Display SemiBold",
        "tamanho": 74,
        "maiusculas": False,
        "palavras_por_ecra": 5,
        "cor_texto": "#FFFFFF",
        "cor_ativa": "#E8C77A",
        "cor_destaque": "#E8C77A",
        "contorno": 3,
        "cor_contorno": "#000000",
        "sombra": 3,
        "desfoque": 4,
        "posicao_v": 520,
        "pop": False,
        "fundo": ("#0B0B0B", "#3A3226", "#1C1C1C"),
        "barra_progresso": "#E8C77A",
    },
}
