"""Generates the README images (banner, divider, icons and stack) in docs/images/.

"Monochrome Net" identity: black and white, modern and futuristic. A dark stage with a
spotlight, voice waves, frosted glass and a smooth orb robot. No color: only black, white and greys.

Usage (development only; not part of the agent or the Lambda):
    pip install fonttools
    python scripts/generate_images.py

The large title becomes an outline (Inter Display Bold), so the SVG does not
depend on an installed font. The technology icons come from Simple Icons (CC0).
Fonts and licenses: docs/images/SOURCES.md.
"""

from __future__ import annotations

import argparse
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "images"

TITLE_FONT = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
SIMPLE_ICONS = "https://raw.githubusercontent.com/simple-icons/simple-icons/13.0.0/icons/{}.svg"

# Monochrome Net palette
BLACK, G1, G2, G3 = "#050505", "#0f0f0f", "#1c1c1c", "#2e2e2e"
G4, G5, WHITE = "#6b6b6b", "#a8a8a8", "#f4f4f4"
SANS = "'Segoe UI','Helvetica Neue','Hiragino Sans','Yu Gothic UI',system-ui,sans-serif"
MONO = "'JetBrains Mono','Cascadia Code','Consolas',ui-monospace,monospace"

COMMAND = "Alexa, turn on the PC"
TAGLINE = "voice control for your PC, with Alexa"
LABEL = "Robot: voice control for your PC with Alexa"

STYLE = """
    .e{transform-box:fill-box;transform-origin:center}
    .c1{animation:cint 4.2s ease-in-out infinite}.c2{animation:cint 5.6s ease-in-out infinite 1.1s}
    .c3{animation:cint 3.6s ease-in-out infinite 2.2s}.c4{animation:cint 6.4s ease-in-out infinite .5s}
    @keyframes cint{0%,100%{opacity:.2;transform:scale(.7)}50%{opacity:1;transform:scale(1.15) rotate(45deg)}}
    .float{animation:float 7s ease-in-out infinite alternate}
    @keyframes float{to{transform:translateY(-7px)}}
    .blink{animation:blink 1.1s steps(1) infinite}
    @keyframes blink{50%{opacity:0}}
    .sweep{animation:sweep 3.4s ease-in-out infinite alternate}
    @keyframes sweep{from{transform:translateX(-46px)}to{transform:translateX(46px)}}
    .spin{transform-box:fill-box;transform-origin:center;animation:spin 40s linear infinite}
    @keyframes spin{to{transform:rotate(360deg)}}
    .eye{transform-box:fill-box;transform-origin:center;animation:eye 5s ease-in-out infinite}
    @keyframes eye{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.1)}}
    .arm{transform-box:fill-box;transform-origin:50% 0;animation:arm 3.6s ease-in-out infinite alternate}
    @keyframes arm{from{transform:rotate(-5deg)}to{transform:rotate(6deg)}}
    .shadow{transform-box:fill-box;transform-origin:center;animation:shadow 7s ease-in-out infinite alternate}
    @keyframes shadow{to{transform:scale(.82);opacity:.15}}
    .bar{transform-box:fill-box;transform-origin:center bottom;animation:bar 1.3s ease-in-out infinite alternate}
    @keyframes bar{from{transform:scaleY(.15)}to{transform:scaleY(1)}}
    .grid{animation:grid 3.2s linear infinite}
    @keyframes grid{0%{transform:translateY(0);opacity:0}15%{opacity:1}100%{transform:translateY(var(--d,100px));opacity:1}}
    .scan{animation:scan 7s linear infinite}
    @keyframes scan{from{transform:translateY(-20px)}to{transform:translateY(400px)}}
    .fa{opacity:0;animation:fa 6s steps(1) infinite 2s}.fb{opacity:0;animation:fb 6s steps(1) infinite 2s}
    @keyframes fa{0%,91%,95.5%,100%{opacity:0;transform:none}92%{opacity:.9;transform:translate(-7px,1px)}94%{opacity:.9;transform:translate(5px,-1px)}}
    @keyframes fb{0%,92%,95.5%,100%{opacity:0;transform:none}92.5%{opacity:.7;transform:translate(7px,-1px)}94.5%{opacity:.7;transform:translate(-5px,1px)}}
    @media (prefers-reduced-motion:reduce){*{animation:none!important}.fa,.fb{opacity:0}.grid{opacity:1}}
"""


def outline(path: str, text: str, size: float, spacing: float = 0.0) -> tuple[str, float]:
    """Converts text to an SVG path with the origin on the baseline; returns (d, width)."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    cmap, glyphs = font.getBestCmap(), font.getGlyphSet()
    scale = size / font["head"].unitsPerEm
    x, parts = 0.0, []
    for letter in text:
        name = cmap[ord(letter)]
        pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.1f}")
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
        parts.append(pen.getCommands())
        x += glyphs[name].width * scale + spacing
    return " ".join(parts), x - spacing


def sparkle(x: float, y: float, color: str, css_class: str = "c1", r: float = 5) -> str:
    """A small sparkle dot as a thin cross."""
    return (f'<path d="M{x - r} {y}H{x + r}M{x} {y - r}V{y + r}" stroke="{color}" stroke-width="1.4" '
            f'stroke-linecap="square" fill="none" class="e {css_class}"/>')


def robot(cx: float) -> str:
    """Original orb robot: a smooth white squircle head, a pill visor with two lights and a loose ring."""
    return f"""<ellipse cx="{cx}" cy="318" rx="70" ry="9" fill="{WHITE}" opacity=".28" class="shadow"/>
    <ellipse cx="{cx}" cy="318" rx="38" ry="4" fill="{WHITE}" opacity=".5" class="shadow"/>
    <g class="float" transform="translate({cx} 0)">
      <circle cx="0" cy="168" r="168" fill="none" stroke="{WHITE}" stroke-opacity=".26" stroke-width="1" stroke-dasharray="1 8" stroke-linecap="round" class="spin"/>
      <path d="M-100 172A100 26 0 0 1 100 172" fill="none" stroke="{WHITE}" stroke-width="3" stroke-linecap="round" opacity=".85"/>
      <rect x="-76" y="92" width="152" height="150" rx="62" fill="url(#shell)" stroke="{BLACK}" stroke-width="5"/>
      <path d="M-52 128C-48 108 -34 100 -16 98" fill="none" stroke="{WHITE}" stroke-width="5" stroke-linecap="round"/>
      <rect x="-54" y="130" width="108" height="48" rx="24" fill="{BLACK}" stroke="{G3}" stroke-width="2"/>
      <g class="eye"><circle cx="-20" cy="154" r="8" fill="{WHITE}"/></g>
      <g class="eye"><circle cx="20" cy="154" r="8" fill="{WHITE}"/></g>
      <path d="M-100 172A100 26 0 0 0 100 172" fill="none" stroke="{WHITE}" stroke-width="3" stroke-linecap="round"/>
      <path d="M-14 208H14" stroke="{G4}" stroke-width="3" stroke-linecap="round" opacity=".7"/>
    </g>"""


def banner() -> str:
    cx = 1010
    title, _ = outline(TITLE_FONT, "ROBOT", 140, 12)
    command = COMMAND
    pill_width = round(len(command) * 11.4 + 92)
    dots = "".join(
        f'<rect x="{64 + i * 12}" y="{350 - height / 2:.1f}" width="4" height="{height}" rx="2" fill="{WHITE}" opacity="{0.35 + (i % 5) * 0.13:.2f}" '
        f'class="bar" style="animation-delay:{-(i * 0.37) % 1.3:.2f}s;animation-duration:{1.0 + (i * 7 % 5) * 0.12:.2f}s"/>'
        for i, height in enumerate([30, 22, 30, 14, 26, 30, 18, 28, 30, 12, 24, 30, 20, 30, 16, 28, 30, 22, 14, 30, 26, 18, 30, 24, 12, 28, 30, 20, 16, 26]))
    waves = "".join(
        f'<circle cx="{cx}" cy="168" r="230" fill="none" stroke="{WHITE}" stroke-width="1.2" opacity=".14" class="wave" style="animation-delay:{-i * 2}s"/>'
        for i in range(3))
    rings = "".join(
        f'<circle cx="{cx}" cy="168" r="{r}" fill="none" stroke="{WHITE}" stroke-opacity="{o}" stroke-width="1"/>'
        for r, o in ((118, .16), (190, .10), (272, .07)))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="380" viewBox="0 0 1280 380" role="img" aria-label="{LABEL}">
  <!-- Monochrome Net: a dark stage with a spotlight, voice waves and the orb robot. Generated by scripts/generate_images.py; the titles are outlines. -->
  <defs><style>{STYLE}
    .wave{{transform-box:fill-box;transform-origin:center;animation:wave 6s ease-out infinite}}
    @keyframes wave{{from{{transform:scale(.5);opacity:.32}}to{{transform:scale(1.35);opacity:0}}}}
  </style>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLACK}"/><stop offset=".6" stop-color="{G1}"/><stop offset="1" stop-color="{G2}"/></linearGradient>
    <radialGradient id="shell" cx=".35" cy=".28" r=".85"><stop offset="0" stop-color="#ffffff"/><stop offset=".55" stop-color="#e4e4e4"/><stop offset="1" stop-color="#8c8c8c"/></radialGradient>
    <radialGradient id="spotlight" cx="{cx / 1280:.3f}" cy=".46" r=".42"><stop offset="0" stop-color="{WHITE}" stop-opacity=".30"/><stop offset=".5" stop-color="{WHITE}" stop-opacity=".07"/><stop offset="1" stop-color="{WHITE}" stop-opacity="0"/></radialGradient>
    <radialGradient id="floor" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{WHITE}" stop-opacity=".45"/><stop offset="1" stop-color="{WHITE}" stop-opacity="0"/></radialGradient>
    <linearGradient id="glass" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{WHITE}" stop-opacity=".12"/><stop offset="1" stop-color="{WHITE}" stop-opacity=".04"/></linearGradient>
    <pattern id="dotgrid" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="{WHITE}"/></pattern>
    <radialGradient id="mask-g" cx=".5" cy=".5" r=".75"><stop offset=".35" stop-color="#000"/><stop offset="1" stop-color="#fff"/></radialGradient>
    <mask id="edge"><rect width="1280" height="380" fill="url(#mask-g)"/></mask>
    <filter id="neon" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="8"/></filter>
    <clipPath id="frame"><rect width="1280" height="380" rx="24"/></clipPath>
  </defs>
  <g clip-path="url(#frame)">
    <rect width="1280" height="380" fill="url(#bg)"/>
    <rect width="1280" height="380" fill="url(#dotgrid)" opacity=".16" mask="url(#edge)"/>
    <rect width="1280" height="380" fill="url(#spotlight)"/>
    {rings}{waves}
    <ellipse cx="{cx}" cy="322" rx="190" ry="20" fill="url(#floor)"/>

    <text x="66" y="64" font-family="'Hiragino Sans','Yu Gothic UI','Noto Sans JP',{SANS}" font-size="20" font-weight="500" letter-spacing="9" fill="{G5}">ロボット</text>
    <text x="1216" y="46" text-anchor="end" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{G5}">VOICE LINK <tspan fill="{WHITE}">ONLINE</tspan></text>
    <text x="1216" y="362" text-anchor="end" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{G5}">WOL · SQS · SHUTDOWN</text>
    <g transform="translate(64 206)"><path d="{title}" fill="{WHITE}"/></g>
    <text x="66" y="258" font-family="{SANS}" font-size="22" font-weight="600" fill="{WHITE}">{TAGLINE}</text>
    <rect x="64" y="276" width="{pill_width}" height="38" rx="19" fill="url(#glass)" stroke="{WHITE}" stroke-opacity=".28"/>
    <text x="86" y="301" font-family="{MONO}" font-size="18" font-weight="600" fill="{WHITE}">&gt; "{command}"</text>
    <rect x="{86 + round((len(command) + 4) * 10.8) + 8}" y="287" width="9" height="16" rx="1" fill="{WHITE}" class="blink"/>
    {dots}

    {robot(cx)}
  </g>
  <rect x="1" y="1" width="1278" height="378" rx="23" fill="none" stroke="{WHITE}" stroke-opacity=".3" stroke-width="2"/>
</svg>
"""


def divider() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="720" height="30" viewBox="0 0 720 30" role="presentation">
  <defs><style>{STYLE}</style>
    <linearGradient id="d" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{WHITE}" stop-opacity="0"/><stop offset="1" stop-color="{WHITE}"/></linearGradient>
    <linearGradient id="e" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{WHITE}"/><stop offset="1" stop-color="{WHITE}" stop-opacity="0"/></linearGradient></defs>
  <path d="M0 15H318" stroke="url(#d)" stroke-width="1.6" fill="none"/>
  <path d="M402 15H720" stroke="url(#e)" stroke-width="1.6" fill="none"/>
  <path d="M0 21H300M420 21H720" stroke="{G4}" stroke-opacity=".5" stroke-width="1" stroke-dasharray="2 5" fill="none"/>
  <path d="M326 8H320V22H326M394 8H400V22H394" stroke="{WHITE}" stroke-width="1.6" fill="none" stroke-linecap="square"/>
  <rect x="354" y="9" width="12" height="12" fill="{WHITE}" class="e c1" transform="rotate(45 360 15)"/>
  {sparkle(338, 15, G5, "c2", 4)}{sparkle(382, 15, G5, "c3", 4)}
</svg>
"""


# 64x64 glyphs (3.2 stroke, square caps and straight joins: HUD look)
GLYPHS = {
    "turn-on": '<path d="M32 14v16"/><path d="M21 21a16 16 0 1 0 22 0"/>',
    "turn-off": '<path d="M42 38a14 14 0 1 1-16-20 11 11 0 0 0 16 20z"/>',
    "voice": '<rect x="25" y="14" width="14" height="24" rx="7"/><path d="M18 31a14 14 0 0 0 28 0"/><path d="M32 45v6M25 51h14"/>',
    "queue": '<path d="M22 44a9 9 0 0 1-1-18 12 12 0 0 1 23 2 8 8 0 0 1-2 16z"/><path d="M28 37h8m-3-3 3 3-3 3"/>',
    "agent": '<rect x="13" y="16" width="38" height="26" rx="3"/><path d="M25 50h14M32 42v8"/><path d="M22 26l5 5-5 5M31 36h8"/>',
    "security": '<path d="M32 12l17 6v12c0 11-7 19-17 23-10-4-17-12-17-23V18z"/><path d="M24 32l6 6 11-12"/>',
    "structure": '<path d="M14 20a3 3 0 0 1 3-3h10l4 5h16a3 3 0 0 1 3 3v19a3 3 0 0 1-3 3H17a3 3 0 0 1-3-3z"/><path d="M14 28h36"/>',
    "verify": '<circle cx="32" cy="32" r="19"/><path d="M23 33l6 6 12-14"/>',
    "config": '<circle cx="23" cy="32" r="8"/><path d="M31 32h20M44 32v7M51 32v5"/>',
    "status": '<circle cx="32" cy="32" r="6"/><circle cx="32" cy="32" r="14"/><path d="M32 32l13-13"/>',
    "showcase": '<path d="M12 20h40l-3 12H15z"/><path d="M16 32v16h32V32"/><path d="M28 48V38h8v10"/>',
}
ICONS = list(GLYPHS)


def icon(name: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" role="img" aria-label="{name}">
  <defs><filter id="b" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.2"/></filter></defs>
  <rect x="3" y="3" width="58" height="58" rx="8" fill="{G1}" stroke="{WHITE}" stroke-opacity=".7" stroke-width="2"/>
  <path d="M3 14V3h11M61 50v11H50" stroke="{WHITE}" stroke-width="3" fill="none" stroke-linecap="square"/>
  <g fill="none" stroke="{WHITE}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" filter="url(#b)" opacity=".55">{GLYPHS[name]}</g>
  <g fill="none" stroke="{WHITE}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">{GLYPHS[name]}</g>
</svg>
"""


def simple_icons_path(name: str) -> str:
    with urllib.request.urlopen(SIMPLE_ICONS.format(name), timeout=30) as r:
        return re.search(r'<path d="([^"]+)"', r.read().decode()).group(1)


def technology(name: str, d: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 56 56" role="img" aria-label="{name}">
  <rect x="1" y="1" width="54" height="54" rx="8" fill="{BLACK}" stroke="{WHITE}" stroke-opacity=".55" stroke-width="2"/>
  <g transform="translate(14 14) scale(1.1667)" fill="{WHITE}"><path d="{d}"/></g>
</svg>
"""


# Claude glyph (Simple Icons, CC0): it left the package in v13, so it is embedded here.
CLAUDE_D = "m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help= "do not download the technology icons")
    args = ap.parse_args()
    (OUTPUT / "icons").mkdir(parents=True, exist_ok=True)
    (OUTPUT / "stack").mkdir(parents=True, exist_ok=True)
    (OUTPUT / "banner.svg").write_text(banner(), encoding="utf-8")
    (OUTPUT / "divider.svg").write_text(divider(), encoding="utf-8")
    for name in ICONS:
        (OUTPUT / "icons" / f"{name}.svg").write_text(icon(name), encoding="utf-8")
    if args.offline:
        return
    stack = [("python", "Python"), ("amazonalexa", "Alexa"), ("awslambda", "AWS Lambda"),
             ("amazonsqs", "Amazon SQS"), ("githubactions", "GitHub Actions"), ("claude", "Claude")]
    for slug, label in stack:
        d = CLAUDE_D if slug == "claude" else simple_icons_path(slug)
        (OUTPUT / "stack" / f"{slug}.svg").write_text(technology(label, d), encoding="utf-8")


if __name__ == "__main__":
    main()
