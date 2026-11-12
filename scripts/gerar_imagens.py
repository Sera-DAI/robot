"""Gera as imagens do README (banner, divisor, ícones e pilha) em docs/imagens/.

Identidade "Monochrome Net": preto e branco, moderna e futurista. Palco escuro com
holofote, ondas de voz, vidro fosco e um robô-orbe liso. Sem cor: só preto, branco e cinzas.

Uso (só em desenvolvimento; não faz parte do agente nem da Lambda):
    pip install fonttools
    python scripts/gerar_imagens.py

O título grande vira contorno (Inter Display Bold), então o SVG não
depende de fonte instalada. Os ícones das tecnologias vêm do Simple Icons (CC0).
Fontes e licenças: docs/imagens/FONTES.md.
"""

from __future__ import annotations

import argparse
import re
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "docs" / "imagens"

FONTE_TITULO = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
SIMPLE_ICONS = "https://raw.githubusercontent.com/simple-icons/simple-icons/13.0.0/icons/{}.svg"

# Paleta Monochrome Net
PRETO, G1, G2, G3 = "#050505", "#0f0f0f", "#1c1c1c", "#2e2e2e"
G4, G5, BRANCO = "#6b6b6b", "#a8a8a8", "#f4f4f4"
SANS = "'Segoe UI','Helvetica Neue','Hiragino Sans','Yu Gothic UI',system-ui,sans-serif"
MONO = "'JetBrains Mono','Cascadia Code','Consolas',ui-monospace,monospace"

COMANDOS = {
    "en": ("Alexa, turn on the PC", 358),
    "pt": ("Alexa, ligar o PC", 318),
}
TAGLINES = {
    "en": "voice control for your PC, with Alexa",
    "pt": "controle do PC por voz, com a Alexa",
}
ROTULOS = {
    "en": "Robot: voice control for your PC with Alexa",
    "pt": "Robot: controle do PC por voz com a Alexa",
}

ESTILO = """
    .e{transform-box:fill-box;transform-origin:center}
    .c1{animation:cint 4.2s ease-in-out infinite}.c2{animation:cint 5.6s ease-in-out infinite 1.1s}
    .c3{animation:cint 3.6s ease-in-out infinite 2.2s}.c4{animation:cint 6.4s ease-in-out infinite .5s}
    @keyframes cint{0%,100%{opacity:.2;transform:scale(.7)}50%{opacity:1;transform:scale(1.15) rotate(45deg)}}
    .flutua{animation:flutua 7s ease-in-out infinite alternate}
    @keyframes flutua{to{transform:translateY(-7px)}}
    .pisca{animation:pisca 1.1s steps(1) infinite}
    @keyframes pisca{50%{opacity:0}}
    .varre{animation:varre 3.4s ease-in-out infinite alternate}
    @keyframes varre{from{transform:translateX(-46px)}to{transform:translateX(46px)}}
    .gira{transform-box:fill-box;transform-origin:center;animation:gira 40s linear infinite}
    @keyframes gira{to{transform:rotate(360deg)}}
    .olho{transform-box:fill-box;transform-origin:center;animation:olho 5s ease-in-out infinite}
    @keyframes olho{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.1)}}
    .braco{transform-box:fill-box;transform-origin:50% 0;animation:braco 3.6s ease-in-out infinite alternate}
    @keyframes braco{from{transform:rotate(-5deg)}to{transform:rotate(6deg)}}
    .sombra{transform-box:fill-box;transform-origin:center;animation:sombra 7s ease-in-out infinite alternate}
    @keyframes sombra{to{transform:scale(.82);opacity:.15}}
    .barra{transform-box:fill-box;transform-origin:center bottom;animation:barra 1.3s ease-in-out infinite alternate}
    @keyframes barra{from{transform:scaleY(.15)}to{transform:scaleY(1)}}
    .grade{animation:grade 3.2s linear infinite}
    @keyframes grade{0%{transform:translateY(0);opacity:0}15%{opacity:1}100%{transform:translateY(var(--d,100px));opacity:1}}
    .scan{animation:scan 7s linear infinite}
    @keyframes scan{from{transform:translateY(-20px)}to{transform:translateY(400px)}}
    .fa{opacity:0;animation:fa 6s steps(1) infinite 2s}.fb{opacity:0;animation:fb 6s steps(1) infinite 2s}
    @keyframes fa{0%,91%,95.5%,100%{opacity:0;transform:none}92%{opacity:.9;transform:translate(-7px,1px)}94%{opacity:.9;transform:translate(5px,-1px)}}
    @keyframes fb{0%,92%,95.5%,100%{opacity:0;transform:none}92.5%{opacity:.7;transform:translate(7px,-1px)}94.5%{opacity:.7;transform:translate(-5px,1px)}}
    @media (prefers-reduced-motion:reduce){*{animation:none!important}.fa,.fb{opacity:0}.grade{opacity:1}}
"""


def contorno(caminho: str, texto: str, tamanho: float, espaco: float = 0.0) -> tuple[str, float]:
    """Converte texto em caminho SVG com a origem na linha de base; devolve (d, largura)."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont

    fonte = TTFont(caminho)
    cmap, glifos = fonte.getBestCmap(), fonte.getGlyphSet()
    escala = tamanho / fonte["head"].unitsPerEm
    x, partes = 0.0, []
    for letra in texto:
        nome = cmap[ord(letra)]
        pen = SVGPathPen(glifos, ntos=lambda v: f"{v:.1f}")
        glifos[nome].draw(TransformPen(pen, (escala, 0, 0, -escala, x, 0)))
        partes.append(pen.getCommands())
        x += glifos[nome].width * escala + espaco
    return " ".join(partes), x - espaco


def mira(x: float, y: float, cor: str, classe: str = "c1", r: float = 5) -> str:
    """Pontinho de brilho em cruz fina."""
    return (f'<path d="M{x - r} {y}H{x + r}M{x} {y - r}V{y + r}" stroke="{cor}" stroke-width="1.4" '
            f'stroke-linecap="square" fill="none" class="e {classe}"/>')


def robo(cx: float) -> str:
    """Robô-orbe original: cabeça em squircle branco liso, visor de pílula com dois pontos de luz e um anel solto."""
    return f"""<ellipse cx="{cx}" cy="318" rx="70" ry="9" fill="{BRANCO}" opacity=".28" class="sombra"/>
    <ellipse cx="{cx}" cy="318" rx="38" ry="4" fill="{BRANCO}" opacity=".5" class="sombra"/>
    <g class="flutua" transform="translate({cx} 0)">
      <circle cx="0" cy="168" r="168" fill="none" stroke="{BRANCO}" stroke-opacity=".26" stroke-width="1" stroke-dasharray="1 8" stroke-linecap="round" class="gira"/>
      <path d="M-100 172A100 26 0 0 1 100 172" fill="none" stroke="{BRANCO}" stroke-width="3" stroke-linecap="round" opacity=".85"/>
      <rect x="-76" y="92" width="152" height="150" rx="62" fill="url(#casco)" stroke="{PRETO}" stroke-width="5"/>
      <path d="M-52 128C-48 108 -34 100 -16 98" fill="none" stroke="{BRANCO}" stroke-width="5" stroke-linecap="round"/>
      <rect x="-54" y="130" width="108" height="48" rx="24" fill="{PRETO}" stroke="{G3}" stroke-width="2"/>
      <g class="olho"><circle cx="-20" cy="154" r="8" fill="{BRANCO}"/></g>
      <g class="olho"><circle cx="20" cy="154" r="8" fill="{BRANCO}"/></g>
      <path d="M-100 172A100 26 0 0 0 100 172" fill="none" stroke="{BRANCO}" stroke-width="3" stroke-linecap="round"/>
      <path d="M-14 208H14" stroke="{G4}" stroke-width="3" stroke-linecap="round" opacity=".7"/>
    </g>"""


def banner(idioma: str) -> str:
    cx = 1010
    titulo, _ = contorno(FONTE_TITULO, "ROBOT", 140, 12)
    comando, x_cursor = COMANDOS[idioma]
    largura_pilula = round(len(comando) * 11.4 + 92)
    pontos = "".join(
        f'<rect x="{64 + i * 12}" y="{350 - alt / 2:.1f}" width="4" height="{alt}" rx="2" fill="{BRANCO}" opacity="{0.35 + (i % 5) * 0.13:.2f}" '
        f'class="barra" style="animation-delay:{-(i * 0.37) % 1.3:.2f}s;animation-duration:{1.0 + (i * 7 % 5) * 0.12:.2f}s"/>'
        for i, alt in enumerate([30, 22, 30, 14, 26, 30, 18, 28, 30, 12, 24, 30, 20, 30, 16, 28, 30, 22, 14, 30, 26, 18, 30, 24, 12, 28, 30, 20, 16, 26]))
    ondas = "".join(
        f'<circle cx="{cx}" cy="168" r="230" fill="none" stroke="{BRANCO}" stroke-width="1.2" opacity=".14" class="onda" style="animation-delay:{-i * 2}s"/>'
        for i in range(3))
    aneis = "".join(
        f'<circle cx="{cx}" cy="168" r="{r}" fill="none" stroke="{BRANCO}" stroke-opacity="{o}" stroke-width="1"/>'
        for r, o in ((118, .16), (190, .10), (272, .07)))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="380" viewBox="0 0 1280 380" role="img" aria-label="{ROTULOS[idioma]}">
  <!-- Monochrome Net: palco escuro com holofote, ondas de voz e o robô-orbe. Gerado por scripts/gerar_imagens.py; os títulos são contornos. -->
  <defs><style>{ESTILO}
    .onda{{transform-box:fill-box;transform-origin:center;animation:onda 6s ease-out infinite}}
    @keyframes onda{{from{{transform:scale(.5);opacity:.32}}to{{transform:scale(1.35);opacity:0}}}}
  </style>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{PRETO}"/><stop offset=".6" stop-color="{G1}"/><stop offset="1" stop-color="{G2}"/></linearGradient>
    <radialGradient id="casco" cx=".35" cy=".28" r=".85"><stop offset="0" stop-color="#ffffff"/><stop offset=".55" stop-color="#e4e4e4"/><stop offset="1" stop-color="#8c8c8c"/></radialGradient>
    <radialGradient id="holofote" cx="{cx / 1280:.3f}" cy=".46" r=".42"><stop offset="0" stop-color="{BRANCO}" stop-opacity=".30"/><stop offset=".5" stop-color="{BRANCO}" stop-opacity=".07"/><stop offset="1" stop-color="{BRANCO}" stop-opacity="0"/></radialGradient>
    <radialGradient id="piso" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{BRANCO}" stop-opacity=".45"/><stop offset="1" stop-color="{BRANCO}" stop-opacity="0"/></radialGradient>
    <linearGradient id="vidro" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BRANCO}" stop-opacity=".12"/><stop offset="1" stop-color="{BRANCO}" stop-opacity=".04"/></linearGradient>
    <pattern id="pontos" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="{BRANCO}"/></pattern>
    <radialGradient id="mascara-g" cx=".5" cy=".5" r=".75"><stop offset=".35" stop-color="#000"/><stop offset="1" stop-color="#fff"/></radialGradient>
    <mask id="borda"><rect width="1280" height="380" fill="url(#mascara-g)"/></mask>
    <filter id="neon" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="8"/></filter>
    <clipPath id="moldura"><rect width="1280" height="380" rx="24"/></clipPath>
  </defs>
  <g clip-path="url(#moldura)">
    <rect width="1280" height="380" fill="url(#bg)"/>
    <rect width="1280" height="380" fill="url(#pontos)" opacity=".16" mask="url(#borda)"/>
    <rect width="1280" height="380" fill="url(#holofote)"/>
    {aneis}{ondas}
    <ellipse cx="{cx}" cy="322" rx="190" ry="20" fill="url(#piso)"/>

    <text x="66" y="64" font-family="'Hiragino Sans','Yu Gothic UI','Noto Sans JP',{SANS}" font-size="20" font-weight="500" letter-spacing="9" fill="{G5}">ロボット</text>
    <text x="1216" y="46" text-anchor="end" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{G5}">VOICE LINK <tspan fill="{BRANCO}">ONLINE</tspan></text>
    <text x="1216" y="362" text-anchor="end" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{G5}">WOL · SQS · SHUTDOWN</text>
    <g transform="translate(64 206)"><path d="{titulo}" fill="{BRANCO}"/></g>
    <text x="66" y="258" font-family="{SANS}" font-size="22" font-weight="600" fill="{BRANCO}">{TAGLINES[idioma]}</text>
    <rect x="64" y="276" width="{largura_pilula}" height="38" rx="19" fill="url(#vidro)" stroke="{BRANCO}" stroke-opacity=".28"/>
    <text x="86" y="301" font-family="{MONO}" font-size="18" font-weight="600" fill="{BRANCO}">&gt; "{comando}"</text>
    <rect x="{86 + round((len(comando) + 4) * 10.8) + 8}" y="287" width="9" height="16" rx="1" fill="{BRANCO}" class="pisca"/>
    {pontos}

    {robo(cx)}
  </g>
  <rect x="1" y="1" width="1278" height="378" rx="23" fill="none" stroke="{BRANCO}" stroke-opacity=".3" stroke-width="2"/>
</svg>
"""


def divisor() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="720" height="30" viewBox="0 0 720 30" role="presentation">
  <defs><style>{ESTILO}</style>
    <linearGradient id="d" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BRANCO}" stop-opacity="0"/><stop offset="1" stop-color="{BRANCO}"/></linearGradient>
    <linearGradient id="e" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BRANCO}"/><stop offset="1" stop-color="{BRANCO}" stop-opacity="0"/></linearGradient></defs>
  <path d="M0 15H318" stroke="url(#d)" stroke-width="1.6" fill="none"/>
  <path d="M402 15H720" stroke="url(#e)" stroke-width="1.6" fill="none"/>
  <path d="M0 21H300M420 21H720" stroke="{G4}" stroke-opacity=".5" stroke-width="1" stroke-dasharray="2 5" fill="none"/>
  <path d="M326 8H320V22H326M394 8H400V22H394" stroke="{BRANCO}" stroke-width="1.6" fill="none" stroke-linecap="square"/>
  <rect x="354" y="9" width="12" height="12" fill="{BRANCO}" class="e c1" transform="rotate(45 360 15)"/>
  {mira(338, 15, G5, "c2", 4)}{mira(382, 15, G5, "c3", 4)}
</svg>
"""


# Glifos de 64x64 (traço de 3.2, pontas quadradas e juntas retas: visual de HUD)
GLIFOS = {
    "ligar": '<path d="M32 14v16"/><path d="M21 21a16 16 0 1 0 22 0"/>',
    "desligar": '<path d="M42 38a14 14 0 1 1-16-20 11 11 0 0 0 16 20z"/>',
    "voz": '<rect x="25" y="14" width="14" height="24" rx="7"/><path d="M18 31a14 14 0 0 0 28 0"/><path d="M32 45v6M25 51h14"/>',
    "fila": '<path d="M22 44a9 9 0 0 1-1-18 12 12 0 0 1 23 2 8 8 0 0 1-2 16z"/><path d="M28 37h8m-3-3 3 3-3 3"/>',
    "agente": '<rect x="13" y="16" width="38" height="26" rx="3"/><path d="M25 50h14M32 42v8"/><path d="M22 26l5 5-5 5M31 36h8"/>',
    "seguranca": '<path d="M32 12l17 6v12c0 11-7 19-17 23-10-4-17-12-17-23V18z"/><path d="M24 32l6 6 11-12"/>',
    "estrutura": '<path d="M14 20a3 3 0 0 1 3-3h10l4 5h16a3 3 0 0 1 3 3v19a3 3 0 0 1-3 3H17a3 3 0 0 1-3-3z"/><path d="M14 28h36"/>',
    "verificar": '<circle cx="32" cy="32" r="19"/><path d="M23 33l6 6 12-14"/>',
    "config": '<circle cx="23" cy="32" r="8"/><path d="M31 32h20M44 32v7M51 32v5"/>',
    "estado": '<circle cx="32" cy="32" r="6"/><circle cx="32" cy="32" r="14"/><path d="M32 32l13-13"/>',
    "vitrine": '<path d="M12 20h40l-3 12H15z"/><path d="M16 32v16h32V32"/><path d="M28 48V38h8v10"/>',
}
ICONES = list(GLIFOS)


def icone(nome: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" role="img" aria-label="{nome}">
  <defs><filter id="b" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.2"/></filter></defs>
  <rect x="3" y="3" width="58" height="58" rx="8" fill="{G1}" stroke="{BRANCO}" stroke-opacity=".7" stroke-width="2"/>
  <path d="M3 14V3h11M61 50v11H50" stroke="{BRANCO}" stroke-width="3" fill="none" stroke-linecap="square"/>
  <g fill="none" stroke="{BRANCO}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" filter="url(#b)" opacity=".55">{GLIFOS[nome]}</g>
  <g fill="none" stroke="{BRANCO}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">{GLIFOS[nome]}</g>
</svg>
"""


def caminho_simple_icons(nome: str) -> str:
    with urllib.request.urlopen(SIMPLE_ICONS.format(nome), timeout=30) as r:
        return re.search(r'<path d="([^"]+)"', r.read().decode()).group(1)


def tecnologia(nome: str, d: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 56 56" role="img" aria-label="{nome}">
  <rect x="1" y="1" width="54" height="54" rx="8" fill="{PRETO}" stroke="{BRANCO}" stroke-opacity=".55" stroke-width="2"/>
  <g transform="translate(14 14) scale(1.1667)" fill="{BRANCO}"><path d="{d}"/></g>
</svg>
"""


# Glifo do Claude (Simple Icons, CC0): saiu da v13 do pacote, então fica embutido aqui.
CLAUDE_D = "m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sem-rede", action="store_true", help="não baixa os ícones das tecnologias")
    args = ap.parse_args()
    (SAIDA / "icones").mkdir(parents=True, exist_ok=True)
    (SAIDA / "stack").mkdir(parents=True, exist_ok=True)
    (SAIDA / "banner.svg").write_text(banner("en"), encoding="utf-8")
    (SAIDA / "banner.pt.svg").write_text(banner("pt"), encoding="utf-8")
    (SAIDA / "divisor.svg").write_text(divisor(), encoding="utf-8")
    for nome in ICONES:
        (SAIDA / "icones" / f"{nome}.svg").write_text(icone(nome), encoding="utf-8")
    if args.sem_rede:
        return
    stack = [("python", "Python"), ("amazonalexa", "Alexa"), ("awslambda", "AWS Lambda"),
             ("amazonsqs", "Amazon SQS"), ("githubactions", "GitHub Actions"), ("claude", "Claude")]
    for slug, rotulo in stack:
        d = CLAUDE_D if slug == "claude" else caminho_simple_icons(slug)
        (SAIDA / "stack" / f"{slug}.svg").write_text(tecnologia(rotulo, d), encoding="utf-8")


if __name__ == "__main__":
    main()
