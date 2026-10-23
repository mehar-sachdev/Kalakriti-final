"""Product-specific local SVG illustrations for the Kalakriti catalogue.

Used by scripts/build_catalog.py. Every illustration keeps the existing Kalakriti
"craft study" card frame (cream card, maroon heading, product title, city · region), but the
artwork itself is chosen from the product's own catalogue data - its name, craft, city,
material and technique - so a plate is drawn as a plate, a bangle set as bangles, a Madhubani
fish painting as fish, a Bandhani dupatta with tie-dye dots, and so on.

Everything is plain SVG: no external URLs, fonts or images.
"""
from __future__ import annotations

from html import escape

# ---------------------------------------------------------------------------- palette (existing brand colours)
MAROON = "#5b1725"
DARK = "#3d0e19"
INK = "#251d18"
CREAM = "#f7f0e2"
PAPER = "#fffdf8"
GOLD = "#c58b2a"
BRASS = "#d4a445"
BRASS_DARK = "#8b5728"
TERRA = "#a94d32"
TERRA_LIGHT = "#c8683f"
INDIGO = "#123b63"
GREEN = "#214a3a"
LIGHT_BLUE = "#d6eef0"
MUTED = "#6d6259"


# ---------------------------------------------------------------------------- textile / surface patterns
def _patterns() -> dict[str, str]:
    """name -> <pattern> body (tile). Each is referenced as url(#p-name)."""
    return {
        "bandhani": '<pattern id="p-bandhani" width="14" height="14" patternUnits="userSpaceOnUse"><rect width="14" height="14" fill="#b3212d"/><circle cx="3.5" cy="3.5" r="1.7" fill="#fff4d6"/><circle cx="10.5" cy="10.5" r="1.7" fill="#f2c14e"/><circle cx="10.5" cy="3.5" r="0.9" fill="#fff4d6"/></pattern>',
        "ajrakh": '<pattern id="p-ajrakh" width="24" height="24" patternUnits="userSpaceOnUse"><rect width="24" height="24" fill="#1f2a55"/><path d="M12 3l9 9-9 9-9-9z" fill="#a3262a"/><path d="M12 8l4 4-4 4-4-4z" fill="#f4ead2"/><circle cx="0" cy="0" r="2.2" fill="#f4ead2"/><circle cx="24" cy="24" r="2.2" fill="#f4ead2"/><circle cx="24" cy="0" r="2.2" fill="#f4ead2"/><circle cx="0" cy="24" r="2.2" fill="#f4ead2"/></pattern>',
        "block": '<pattern id="p-block" width="26" height="26" patternUnits="userSpaceOnUse"><rect width="26" height="26" fill="#f6ead2"/><g transform="translate(13 12)"><circle r="2.6" fill="#b0302a"/><circle cx="0" cy="-4.6" r="2.3" fill="#b0302a"/><circle cx="0" cy="4.6" r="2.3" fill="#b0302a"/><circle cx="-4.6" cy="0" r="2.3" fill="#b0302a"/><circle cx="4.6" cy="0" r="2.3" fill="#b0302a"/><circle r="1.4" fill="#f2c14e"/><path d="M0 7v5" stroke="#3f6b3a" stroke-width="1.6"/></g></pattern>',
        "bagru": '<pattern id="p-bagru" width="24" height="24" patternUnits="userSpaceOnUse"><rect width="24" height="24" fill="#eadcbc"/><g transform="translate(12 12)" fill="#2b2320"><circle r="2"/><path d="M0-8q4 4 0 6q-4-2 0-6zM0 8q4-4 0-6q-4 2 0 6zM-8 0q4-4 6 0q-2 4-6 0zM8 0q-4-4-6 0q2 4 6 0z"/></g><circle cx="0" cy="0" r="2" fill="#9c3526"/><circle cx="24" cy="24" r="2" fill="#9c3526"/><circle cx="24" cy="0" r="2" fill="#9c3526"/><circle cx="0" cy="24" r="2" fill="#9c3526"/></pattern>',
        "kantha": '<pattern id="p-kantha" width="30" height="16" patternUnits="userSpaceOnUse"><rect width="30" height="16" fill="#f5ecd8"/><path d="M0 4h30" stroke="#b0302a" stroke-width="1.6" stroke-dasharray="3 2.5"/><path d="M0 12h30" stroke="#2d5a8a" stroke-width="1.6" stroke-dasharray="3 2.5"/><circle cx="15" cy="8" r="2" fill="#e0a526"/></pattern>',
        "kota": '<pattern id="p-kota" width="12" height="12" patternUnits="userSpaceOnUse"><rect width="12" height="12" fill="#f4e6c4"/><path d="M0 0h12M0 0v12" stroke="#c9a15a" stroke-width="1.4"/><path d="M6 0v12M0 6h12" stroke="#e8d3a3" stroke-width="0.8"/></pattern>',
        "ikat": '<pattern id="p-ikat" width="28" height="20" patternUnits="userSpaceOnUse"><rect width="28" height="20" fill="#7a1f2b"/><path d="M0 10l7-8 7 8-7 8zM14 10l7-8 7 8-7 8z" fill="#e4b94a"/><path d="M4 10l3-3.5 3 3.5-3 3.5zM18 10l3-3.5 3 3.5-3 3.5z" fill="#1f5a4a"/><path d="M7 0v2M21 0v2M7 18v2M21 18v2" stroke="#f6ead2" stroke-width="2"/></pattern>',
        "brocade": '<pattern id="p-brocade" width="22" height="22" patternUnits="userSpaceOnUse"><rect width="22" height="22" fill="#6d1424"/><g fill="#e2b85a"><path d="M11 4q5 5 0 10q-5-5 0-10z"/><circle cx="11" cy="17" r="1.4"/><circle cx="0" cy="0" r="1.6"/><circle cx="22" cy="0" r="1.6"/><circle cx="0" cy="22" r="1.6"/><circle cx="22" cy="22" r="1.6"/></g></pattern>',
        "baluchari": '<pattern id="p-baluchari" width="26" height="34" patternUnits="userSpaceOnUse"><rect width="26" height="34" fill="#8e1b2c"/><g fill="#f0c865"><circle cx="13" cy="7" r="3"/><path d="M8 26l5-16 5 16z"/><path d="M6 30h14" stroke="#f0c865" stroke-width="2"/></g></pattern>',
        "chikan": '<pattern id="p-chikan" width="24" height="24" patternUnits="userSpaceOnUse"><rect width="24" height="24" fill="#fbf8f0"/><g fill="none" stroke="#cfc6b3" stroke-width="1.3"><circle cx="12" cy="12" r="3"/><path d="M12 5q3 3.5 0 4q-3-.5 0-4zM12 19q3-3.5 0-4q-3 .5 0 4zM5 12q3.5-3 4 0q-.5 3-4 0zM19 12q-3.5-3-4 0q.5 3 4 0z"/></g><circle cx="0" cy="0" r="1.2" fill="#d8d0bf"/><circle cx="24" cy="24" r="1.2" fill="#d8d0bf"/></pattern>',
        "mirror": '<pattern id="p-mirror" width="26" height="26" patternUnits="userSpaceOnUse"><rect width="26" height="26" fill="#a3262a"/><circle cx="13" cy="13" r="5" fill="#e9eef2" stroke="#f2c14e" stroke-width="2"/><path d="M13 3v4M13 19v4M3 13h4M19 13h4" stroke="#2c6e49" stroke-width="2"/><circle cx="0" cy="0" r="3" fill="#f2c14e"/><circle cx="26" cy="26" r="3" fill="#f2c14e"/><circle cx="26" cy="0" r="3" fill="#f2c14e"/><circle cx="0" cy="26" r="3" fill="#f2c14e"/></pattern>',
        "embroidery": '<pattern id="p-embroidery" width="28" height="28" patternUnits="userSpaceOnUse"><rect width="28" height="28" fill="#f3e6cf"/><g transform="translate(14 14)"><circle r="3" fill="#e0a526"/><path d="M0-9q4 4 0 6q-4-2 0-6zM0 9q4-4 0-6q-4 2 0 6zM-9 0q4-4 6 0q-2 4-6 0zM9 0q-4-4-6 0q2 4 6 0z" fill="#b0302a"/></g><path d="M0 0l6 6M28 0l-6 6M0 28l6-6M28 28l-6-6" stroke="#2c6e49" stroke-width="2"/></pattern>',
        "tussar": '<pattern id="p-tussar" width="18" height="18" patternUnits="userSpaceOnUse"><rect width="18" height="18" fill="#dcc08a"/><path d="M0 4h18M0 11h18" stroke="#cda96b" stroke-width="1.2"/><path d="M4 0v18" stroke="#e7d2a6" stroke-width="0.8"/></pattern>',
        "wool": '<pattern id="p-wool" width="30" height="30" patternUnits="userSpaceOnUse"><rect width="30" height="30" fill="#d9ccb2"/><path d="M0 6h30M0 24h30" stroke="#8e1b2c" stroke-width="3"/><path d="M0 15h30" stroke="#2d4a6e" stroke-width="2"/><path d="M5 15l5-4 5 4 5-4 5 4" fill="none" stroke="#8e1b2c" stroke-width="1.4"/></pattern>',
        "sozni": '<pattern id="p-sozni" width="30" height="30" patternUnits="userSpaceOnUse"><rect width="30" height="30" fill="#2a2433"/><path d="M15 5q9 3 5 13q-3 6-8 3q6-2 3-8q-3-5-9-2q2-5 9-6z" fill="#c9423a"/><circle cx="15" cy="13" r="2" fill="#f2d69a"/><path d="M4 26q4-4 8 0" fill="none" stroke="#6fa37a" stroke-width="1.6"/></pattern>',
        "crewel": '<pattern id="p-crewel" width="30" height="30" patternUnits="userSpaceOnUse"><rect width="30" height="30" fill="#f4ecd9"/><path d="M15 26V10" stroke="#3f6b3a" stroke-width="1.6"/><path d="M15 10q-6-6 0-8q6 2 0 8z" fill="#b0302a"/><path d="M15 18q-7-1-7-5q5 0 7 5zM15 20q7-1 7-5q-5 0-7 5z" fill="#3f6b3a"/></pattern>',
        "durrie": '<pattern id="p-durrie" width="40" height="40" patternUnits="userSpaceOnUse"><rect width="40" height="40" fill="#efe3c8"/><path d="M0 4h40M0 36h40" stroke="#8e1b2c" stroke-width="4"/><path d="M20 10l10 10-10 10-10-10z" fill="#8e1b2c"/><path d="M20 15l5 5-5 5-5-5z" fill="#efe3c8"/><path d="M0 20l5-5M0 20l5 5M40 20l-5-5M40 20l-5 5" stroke="#2d4a6e" stroke-width="2"/></pattern>',
        "handloom": '<pattern id="p-handloom" width="24" height="24" patternUnits="userSpaceOnUse"><rect width="24" height="24" fill="#efe4cc"/><path d="M0 3h24M0 21h24M3 0v24M21 0v24" stroke="#a3262a" stroke-width="2"/><path d="M0 12h24M12 0v24" stroke="#2d4a6e" stroke-width="1.2"/></pattern>',
        "sujuni": '<pattern id="p-sujuni" width="34" height="30" patternUnits="userSpaceOnUse"><rect width="34" height="30" fill="#f6eedc"/><path d="M0 3h34M0 27h34" stroke="#b0302a" stroke-width="1.2" stroke-dasharray="2 2"/><g transform="translate(17 15)"><circle cy="-6" r="2.6" fill="#b0302a"/><path d="M-4 6l4-10 4 10z" fill="#2d5a8a"/><path d="M-7 -1h14" stroke="#e0a526" stroke-width="1.6"/></g></pattern>',
        "rogan": '<pattern id="p-rogan" width="30" height="30" patternUnits="userSpaceOnUse"><rect width="30" height="30" fill="#2b2233"/><path d="M15 27V9" stroke="#e0a526" stroke-width="1.6"/><path d="M15 9q-5-7 0-7q5 0 0 7z" fill="#d6452f"/><path d="M15 16q-8-2-8-7q6 1 8 7zM15 16q8-2 8-7q-6 1-8 7z" fill="#3f8f6b"/><path d="M15 23q-7-1-7-5q5 0 7 5zM15 23q7-1 7-5q-5 0-7 5z" fill="#e0a526"/></pattern>',
        "papier": '<pattern id="p-papier" width="26" height="26" patternUnits="userSpaceOnUse"><rect width="26" height="26" fill="#1d2d55"/><g transform="translate(13 13)"><circle r="3" fill="#f2c14e"/><path d="M0-9q4 4 0 6q-4-2 0-6zM0 9q4-4 0-6q-4 2 0 6zM-9 0q4-4 6 0q-2 4-6 0zM9 0q-4-4-6 0q2 4 6 0z" fill="#c9423a"/></g><path d="M0 0q3 3 6 0M20 26q3-3 6 0" fill="none" stroke="#6fa37a" stroke-width="1.6"/></pattern>',
        "naqashi": '<pattern id="p-naqashi" width="26" height="26" patternUnits="userSpaceOnUse"><rect width="26" height="26" fill="#f4ead6"/><g transform="translate(13 13)"><circle r="2.6" fill="#c9423a"/><path d="M0-8q4 4 0 5q-4-1 0-5zM0 8q4-4 0-5q-4 1 0 5zM-8 0q4-4 5 0q-1 4-5 0zM8 0q-4-4-5 0q1 4 5 0z" fill="#1d4a7a"/></g><circle cx="0" cy="0" r="2" fill="#c58b2a"/><circle cx="26" cy="26" r="2" fill="#c58b2a"/></pattern>',
        "blue": '<pattern id="p-blue" width="26" height="26" patternUnits="userSpaceOnUse"><rect width="26" height="26" fill="#eaf4f6"/><g transform="translate(13 13)"><circle r="3" fill="#123b63"/><path d="M0-9q4 4 0 6q-4-2 0-6zM0 9q4-4 0-6q-4 2 0 6zM-9 0q4-4 6 0q-2 4-6 0zM9 0q-4-4-6 0q2 4 6 0z" fill="#2f6fa3"/></g><path d="M0 0l4 4M26 0l-4 4M0 26l4-4M26 26l-4-4" stroke="#3a8f86" stroke-width="2"/></pattern>',
        "weave": '<pattern id="p-weave" width="16" height="16" patternUnits="userSpaceOnUse"><rect width="16" height="16" fill="#d7aa66"/><path d="M0 4h8M8 12h8" stroke="#a8773a" stroke-width="3"/><path d="M12 0v8M4 8v8" stroke="#b8894a" stroke-width="3"/></pattern>',
        "sikki": '<pattern id="p-sikki" width="16" height="12" patternUnits="userSpaceOnUse"><rect width="16" height="12" fill="#e2bf6e"/><path d="M0 3q4-3 8 0t8 0M0 9q4-3 8 0t8 0" fill="none" stroke="#b98b3a" stroke-width="1.6"/></pattern>',
        "jute": '<pattern id="p-jute" width="14" height="10" patternUnits="userSpaceOnUse"><rect width="14" height="10" fill="#c9a36a"/><path d="M0 2.5q3.5-3 7 0t7 0M0 7.5q3.5-3 7 0t7 0" fill="none" stroke="#9c7640" stroke-width="1.8"/></pattern>',
        "willow": '<pattern id="p-willow" width="14" height="14" patternUnits="userSpaceOnUse"><rect width="14" height="14" fill="#a88a64"/><path d="M0 3.5h7M7 10.5h7" stroke="#7a5f3e" stroke-width="3"/><path d="M10.5 0v7M3.5 7v7" stroke="#8b6f4a" stroke-width="3"/></pattern>',
        "wood": '<pattern id="p-wood" width="40" height="12" patternUnits="userSpaceOnUse"><rect width="40" height="12" fill="#8a5530"/><path d="M0 4q10-3 20 0t20 0M0 9q10-2 20 0t20 0" fill="none" stroke="#6e4122" stroke-width="1.2"/></pattern>',
        "walnut": '<pattern id="p-walnut" width="40" height="12" patternUnits="userSpaceOnUse"><rect width="40" height="12" fill="#6b4226"/><path d="M0 4q10-3 20 0t20 0M0 9q10-2 20 0t20 0" fill="none" stroke="#523019" stroke-width="1.2"/></pattern>',
        "leather": '<pattern id="p-leather" width="20" height="20" patternUnits="userSpaceOnUse"><rect width="20" height="20" fill="#a0522d"/><path d="M10 3l7 7-7 7-7-7z" fill="none" stroke="#e5c38a" stroke-width="1.4"/><circle cx="10" cy="10" r="1.6" fill="#e5c38a"/></pattern>',
        "madhubani": '<pattern id="p-madhubani" width="16" height="16" patternUnits="userSpaceOnUse"><rect width="16" height="16" fill="#f4dfb3"/><path d="M0 8h16" stroke="#251d18" stroke-width="1"/><path d="M4 4l4 4-4 4M12 4l-4 4 4 4" fill="none" stroke="#b0302a" stroke-width="1.2"/></pattern>',
        "terracotta_relief": '<pattern id="p-terracotta_relief" width="20" height="20" patternUnits="userSpaceOnUse"><rect width="20" height="20" fill="#b9643b"/><circle cx="10" cy="10" r="4" fill="none" stroke="#8a3f22" stroke-width="2"/></pattern>',
    }


# ---------------------------------------------------------------------------- choosing a surface pattern
def _textile_pattern(text: str) -> str:
    rules = [
        (("bandhani", "tie-dye", "tie dyed", "tie-dyed"), "bandhani"),
        (("ajrakh",), "ajrakh"),
        (("rogan",), "rogan"),
        (("kantha",), "kantha"),
        (("kota doria",), "kota"),
        (("ikat", "patola", "patan"), "ikat"),
        (("baluchari", "bishnupur"), "baluchari"),
        (("hand-painted", "hand painted", "namda", "crewel"), "crewel"),
        (("brocade", "banarasi", "banaras", "kashi", "zari"), "brocade"),
        (("chikankari", "chikan"), "chikan"),
        (("mirror", "kutch embroidered", "kutch cushion", "hand-embroidered kutch", "bhuj"), "mirror"),
        (("tussar",), "tussar"),
        (("sozni", "kani", "pashmina"), "sozni"),
        (("sujuni",), "sujuni"),
        (("durrie", "floor mat"), "durrie"),
        (("wool", "woolen"), "wool"),
        (("sanganer", "sanganeri"), "block"),
        (("bagru", "dabu"), "bagru"),
        (("block", "print"), "block"),
        (("embroider",), "embroidery"),
        (("handwoven", "handloom", "weav"), "handloom"),
    ]
    for keys, name in rules:
        if any(k in text for k in keys):
            return name
    return "block"


# ---------------------------------------------------------------------------- object drawings
# Each returns SVG markup drawn in the card's art area (roughly x 60-300, y 100-300).
def _shadow(cx=180, cy=292, rx=100, ry=10) -> str:
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#e8dcc6"/>'


def _drape(fill: str, border: str = MAROON, saree: bool = False) -> str:
    """Cloth hanging over a wooden rod (dupatta, stole, scarf, shawl, saree)."""
    pallu = f'<path d="M205 118h52l14 150q-30 12-60 4z" fill="{fill}" stroke="{DARK}" stroke-width="4"/><path d="M211 250q30 6 58 -2" stroke="{border}" stroke-width="10" fill="none"/>' if saree else ""
    fringe = "".join(f'<path d="M{x} 280v12" stroke="{border}" stroke-width="3"/>' for x in range(108, 208, 9)) if not saree else ""
    return (
        _shadow(ry=8)
        + f'<path d="M84 112h192" stroke="{BRASS_DARK}" stroke-width="10" stroke-linecap="round"/><circle cx="80" cy="112" r="8" fill="{GOLD}"/><circle cx="280" cy="112" r="8" fill="{GOLD}"/>'
        + f'<path d="M102 116h110l-4 164q-54 10-104 0z" fill="{fill}" stroke="{DARK}" stroke-width="4"/>'
        + f'<path d="M104 262q52 9 104 0" stroke="{border}" stroke-width="12" fill="none"/><path d="M103 124l1 138M209 124l-1 138" stroke="{border}" stroke-width="6"/>'
        + f'<path d="M140 118q-8 80 4 162M176 118q8 80-4 162" stroke="#000" stroke-opacity=".12" stroke-width="5" fill="none"/>'
        + fringe + pallu
    )


def _cushion(fill: str) -> str:
    return (
        _shadow(ry=9)
        + f'<path d="M88 130q92-18 184 0q-12 78 0 150q-92 16-184 0q12-72 0-150z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M104 146q76-12 152 0q-9 62 0 118q-76 12-152 0q9-56 0-118z" fill="none" stroke="{GOLD}" stroke-width="4" stroke-dasharray="7 5"/>'
        + f'<path d="M88 130q14 8 20 22M272 130q-14 8-20 22M88 280q14-8 20-22M272 280q-14-8-20-22" stroke="{DARK}" stroke-width="4" fill="none"/>'
    )


def _runner(fill: str) -> str:
    return (
        f'<path d="M58 238l60-78h124l60 78z" fill="{BRASS_DARK}" opacity=".35"/>'
        + f'<path d="M138 132h84l34 150H104z" fill="{fill}" stroke="{DARK}" stroke-width="4"/>'
        + f'<path d="M136 146h88M112 262h136" stroke="{MAROON}" stroke-width="8"/>'
        + "".join(f'<path d="M{x} 282v12" stroke="{MAROON}" stroke-width="3"/>' for x in range(110, 252, 10))
    )


def _mats(fill: str, count: int = 3) -> str:
    out = _shadow(ry=8)
    for i in range(count):
        y = 250 - i * 26
        x = 94 + i * 6
        out += f'<rect x="{x}" y="{y - 70}" width="{172 - i * 12}" height="104" rx="8" fill="{fill}" stroke="{DARK}" stroke-width="4" transform="skewX(-8)"/>'
    out += f'<path d="M110 256h150" stroke="{MAROON}" stroke-width="6"/>'
    return out


def _wall_hanging(fill: str, tassels: bool = True) -> str:
    t = "".join(
        f'<path d="M{x} 286v14" stroke="{GOLD}" stroke-width="3"/><circle cx="{x}" cy="302" r="4" fill="{MAROON}"/>'
        for x in range(104, 260, 22)
    ) if tassels else ""
    return (
        f'<path d="M150 104l30-14 30 14" fill="none" stroke="{BRASS_DARK}" stroke-width="3"/>'
        + f'<path d="M80 108h200" stroke="{BRASS_DARK}" stroke-width="9" stroke-linecap="round"/>'
        + f'<rect x="96" y="110" width="168" height="176" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<rect x="106" y="120" width="148" height="156" fill="none" stroke="{MAROON}" stroke-width="6"/>'
        + t
    )


def _rug(fill: str) -> str:
    fringe = "".join(f'<path d="M{x} 124l-2-12M{x - 26} 290l-3 12" stroke="#cdb892" stroke-width="3"/>' for x in range(122, 262, 9))
    return (
        _shadow(ry=9)
        + fringe
        + f'<path d="M116 124h140l-26 166H90z" fill="{fill}" stroke="{DARK}" stroke-width="4"/>'
        + f'<path d="M116 124h140l-26 166H90z" fill="none" stroke="{MAROON}" stroke-width="10" stroke-opacity=".7"/>'
    )


def _kurta(fill: str) -> str:
    return (
        _shadow(ry=7)
        + f'<path d="M150 112h60l44 22 26 64-26 10-14-34v112H120V174l-14 34-26-10 26-64z" fill="{fill}" stroke="{DARK}" stroke-width="4"/>'
        + f'<path d="M166 112q14 26 28 0M180 124v48" stroke="#b9ad96" stroke-width="3" fill="none"/>'
    )


def _bowl(fill: str, rim: str) -> str:
    return (
        _shadow(cy=288, rx=86)
        + f'<path d="M86 184h188q-6 66-60 88h-68q-54-22-60-88z" fill="{fill}" stroke="{rim}" stroke-width="6"/>'
        + f'<ellipse cx="180" cy="184" rx="94" ry="20" fill="{PAPER}" stroke="{rim}" stroke-width="6"/>'
        + f'<ellipse cx="180" cy="186" rx="76" ry="12" fill="{fill}" opacity=".55"/>'
        + f'<path d="M160 272h40v12h-40z" fill="{rim}"/>'
    )


def _plate(fill: str, rim: str) -> str:
    return (
        _shadow(cy=286, rx=104, ry=12)
        + f'<ellipse cx="180" cy="206" rx="112" ry="76" fill="{PAPER}" stroke="{rim}" stroke-width="6"/>'
        + f'<ellipse cx="180" cy="206" rx="96" ry="64" fill="{fill}"/>'
        + f'<ellipse cx="180" cy="206" rx="46" ry="30" fill="{PAPER}" stroke="{rim}" stroke-width="4"/>'
        + f'<circle cx="180" cy="206" r="10" fill="{rim}"/>'
    )


def _vase(fill: str, rim: str) -> str:
    return (
        _shadow(cy=292, rx=70)
        + f'<path d="M156 110h48q-6 30 10 46q52 40 24 98q-12 28-58 34q-46-6-58-34q-28-58 24-98q16-16 10-46z" fill="{fill}" stroke="{rim}" stroke-width="6"/>'
        + f'<ellipse cx="180" cy="110" rx="28" ry="7" fill="{PAPER}" stroke="{rim}" stroke-width="5"/>'
        + f'<path d="M126 176h108M116 250h128" stroke="{rim}" stroke-width="5"/>'
    )


def _jar(fill: str, rim: str) -> str:
    return (
        _shadow(cy=292, rx=80)
        + f'<path d="M112 170q-6 90 26 112h84q32-22 26-112z" fill="{fill}" stroke="{rim}" stroke-width="6"/>'
        + f'<path d="M104 170h152q-4-34-76-34t-76 34z" fill="{fill}" stroke="{rim}" stroke-width="6"/>'
        + f'<circle cx="180" cy="126" r="11" fill="{GOLD}" stroke="{rim}" stroke-width="4"/>'
        + f'<path d="M110 196h140" stroke="{rim}" stroke-width="5"/>'
    )


def _lidded_round_box(fill: str, rim: str) -> str:
    return (
        _shadow(cy=290, rx=96)
        + f'<path d="M86 196v56q0 32 94 32t94-32v-56z" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + f'<ellipse cx="180" cy="196" rx="94" ry="30" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + f'<path d="M92 184q88-66 176 0" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + f'<circle cx="180" cy="150" r="10" fill="{GOLD}" stroke="{rim}" stroke-width="4"/>'
        + f'<path d="M86 214q94 34 188 0" stroke="{GOLD}" stroke-width="4" fill="none"/>'
    )


def _box(fill: str, trim: str = GOLD) -> str:
    return (
        _shadow(cy=292, rx=110)
        + f'<path d="M78 196h204v84H78z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M78 196l24-40h156l24 40z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M78 196h204" stroke="{DARK}" stroke-width="8"/>'
        + f'<rect x="100" y="212" width="160" height="52" rx="6" fill="none" stroke="{trim}" stroke-width="4"/>'
        + f'<path d="M180 214q20 22 0 46q-20-24 0-46z" fill="{trim}"/><rect x="170" y="192" width="20" height="16" rx="3" fill="{trim}" stroke="{DARK}" stroke-width="3"/>'
    )


def _tray(fill: str, trim: str = GOLD) -> str:
    return (
        _shadow(cy=282, rx=120)
        + f'<path d="M66 180l32-38h164l32 38-26 90H92z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M98 176l18-20h128l18 20-16 72H114z" fill="none" stroke="{trim}" stroke-width="4"/>'
        + f'<path d="M180 170q26 30 0 60q-26-30 0-60zM150 200q30-26 60 0q-30 26-60 0z" fill="{trim}" opacity=".85"/>'
        + f'<path d="M66 180h-12M294 180h12" stroke="{DARK}" stroke-width="10" stroke-linecap="round"/>'
    )


def _jali_panel(fill: str) -> str:
    holes = "".join(
        f'<path d="M{x} {y}l9 9-9 9-9-9z" fill="{PAPER}" stroke="{DARK}" stroke-width="2"/>'
        for x in range(122, 250, 26) for y in range(136, 262, 26)
    )
    return (
        _shadow(ry=8)
        + f'<path d="M100 290V130q0-26 80-38q80 12 80 38v160z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + holes
    )


def _diyas(fill: str, rim: str, count: int) -> str:
    out = _shadow(cy=290, rx=116)
    positions = {2: [130, 230], 3: [110, 180, 250], 4: [96, 152, 208, 264]}.get(count, [110, 180, 250])
    for i, x in enumerate(positions):
        y = 262 if i % 2 == 0 else 250
        out += (
            f'<path d="M{x - 34} {y - 20}q34 42 68 0z" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
            f'<path d="M{x + 30} {y - 22}l10-6" stroke="{rim}" stroke-width="5"/>'
            f'<path d="M{x + 38} {y - 30}q-10-18 0-34q10 16 0 34z" fill="#f2b02e" stroke="{TERRA}" stroke-width="3"/>'
            f'<path d="M{x - 26} {y - 10}h52" stroke="{GOLD}" stroke-width="3" opacity=".8"/>'
        )
    return out


def _tile(fill: str, rim: str, round_: bool = False) -> str:
    if round_:
        return (
            _shadow(cy=292, rx=86)
            + f'<circle cx="180" cy="196" r="94" fill="{fill}" stroke="{rim}" stroke-width="7"/>'
            + f'<circle cx="180" cy="196" r="72" fill="none" stroke="{rim}" stroke-width="5" stroke-dasharray="10 6"/>'
            + f'<path d="M180 146q30 50 0 100q-30-50 0-100zM130 196q50-30 100 0q-50 30-100 0z" fill="{rim}" opacity=".75"/>'
            + f'<circle cx="180" cy="196" r="12" fill="{PAPER}" opacity=".6"/>'
        )
    return (
        _shadow(cy=292, rx=96)
        + f'<rect x="86" y="104" width="188" height="180" rx="10" fill="{fill}" stroke="{rim}" stroke-width="7"/>'
        + f'<rect x="102" y="120" width="156" height="148" rx="6" fill="none" stroke="{rim}" stroke-width="4"/>'
    )


def _relief_figure(rim: str) -> str:
    """Temple-style relief: arch with a seated figure."""
    return (
        f'<path d="M128 256v-66q0-46 52-60q52 14 52 60v66z" fill="none" stroke="{rim}" stroke-width="6"/>'
        f'<circle cx="180" cy="172" r="14" fill="{rim}" opacity=".85"/>'
        f'<path d="M154 250q2-44 26-58q24 14 26 58z" fill="{rim}" opacity=".85"/>'
        f'<path d="M110 270h140" stroke="{rim}" stroke-width="6"/>'
    )


def _horse(fill: str, rim: str, bankura: bool = True) -> str:
    neck = "M196 196l-4-78q0-12 12-12h14q10 0 14 12l12 30q2 8-6 10l-18 4 2 34" if bankura else "M200 196l10-58 26 10-4 44"
    return (
        _shadow(cy=292, rx=100)
        + f'<path d="{neck}z" fill="{fill}" stroke="{rim}" stroke-width="5" stroke-linejoin="round"/>'
        + f'<path d="M204 108l-4-18 12 12M222 106l6-16 4 18" fill="{fill}" stroke="{rim}" stroke-width="4"/>'
        + f'<path d="M108 194h120q14 0 14 14v18q0 12-12 12H108q-12 0-12-12v-18q0-14 12-14z" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + f'<path d="M110 238v46M136 238v46M204 238v46M230 238v46" stroke="{rim}" stroke-width="14" stroke-linecap="round"/>'
        + f'<path d="M110 238v46M136 238v46M204 238v46M230 238v46" stroke="{fill}" stroke-width="8" stroke-linecap="round"/>'
        + f'<path d="M96 204q-22 10-18 40" stroke="{rim}" stroke-width="6" fill="none"/>'
        + f'<circle cx="220" cy="126" r="4" fill="{INK}"/>'
        + f'<path d="M118 210h108M200 150q10 4 22 0" stroke="#f1dcae" stroke-width="4" stroke-dasharray="6 5" fill="none"/>'
    )


def _elephant(fill: str, rim: str) -> str:
    return (
        _shadow(cy=292, rx=110)
        + f'<path d="M92 214q4-66 82-68h40q56 4 58 56v6l-8 70h-24l-6-44h-70l-6 44h-24l-6-44q-18-4-24-12z" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + f'<path d="M266 196q34 22 18 74q-6 16-18 12" stroke="{rim}" stroke-width="12" fill="none" stroke-linecap="round"/>'
        + f'<path d="M266 196q34 22 18 74q-6 16-18 12" stroke="{fill}" stroke-width="6" fill="none" stroke-linecap="round"/>'
        + f'<path d="M216 160q-30 10-24 48q18 8 32-4" fill="{GOLD}" stroke="{rim}" stroke-width="4"/>'
        + f'<circle cx="252" cy="182" r="5" fill="{INK}"/><path d="M140 150q30-20 64 0v34h-64z" fill="#a3262a" stroke="{rim}" stroke-width="4"/>'
        + f'<path d="M144 172h56" stroke="{GOLD}" stroke-width="4"/>'
    )


def _figurine(fill: str, rim: str) -> str:
    return (
        _shadow(cy=294, rx=70)
        + f'<rect x="134" y="274" width="92" height="16" rx="4" fill="{fill}" stroke="{rim}" stroke-width="4"/>'
        + f'<path d="M180 138v14M150 176l-24 44M210 176l20 36" stroke="{rim}" stroke-width="12" stroke-linecap="round"/>'
        + f'<path d="M150 176l-24 44M210 176l20 36" stroke="{fill}" stroke-width="6" stroke-linecap="round"/>'
        + f'<path d="M156 160h48l10 60-12 54h-44l-12-54z" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + f'<circle cx="180" cy="124" r="22" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + f'<path d="M160 116q20-22 40 0" stroke="{rim}" stroke-width="4" fill="none"/>'
        + f'<path d="M160 192q20 8 40 0M158 212q22 8 44 0M160 232q20 8 40 0" stroke="{rim}" stroke-width="3" fill="none"/>'
        + f'<ellipse cx="232" cy="216" rx="16" ry="10" fill="{fill}" stroke="{rim}" stroke-width="4"/>'
    )


def _bell(x: float, y: float, s: float, fill: str, rim: str) -> str:
    return (
        f'<g transform="translate({x} {y}) scale({s})">'
        f'<path d="M0 -40v14" stroke="{rim}" stroke-width="4"/><circle cx="0" cy="-44" r="6" fill="none" stroke="{rim}" stroke-width="4"/>'
        f'<path d="M-8 -26h16q2 16 12 30q10 16 16 34H-36q6-18 16-34q10-14 12-30z" fill="{fill}" stroke="{rim}" stroke-width="4"/>'
        f'<path d="M-30 20h60" stroke="{rim}" stroke-width="3"/><path d="M-20 2h40" stroke="{rim}" stroke-width="2" stroke-dasharray="4 3"/>'
        f'<circle cx="0" cy="44" r="7" fill="{rim}"/></g>'
    )


def _bells(fill: str, rim: str, count: int) -> str:
    if count == 1:
        return f'<path d="M180 96v36" stroke="{rim}" stroke-width="4"/><path d="M150 96h60" stroke="{BRASS_DARK}" stroke-width="8" stroke-linecap="round"/>' + _bell(180, 196, 1.7, fill, rim)
    out = f'<path d="M84 106h192" stroke="{BRASS_DARK}" stroke-width="10" stroke-linecap="round"/>'
    xs = [110, 180, 250] if count == 3 else [100, 153, 207, 260]
    for i, x in enumerate(xs):
        drop = 40 + (i % 2) * 34
        out += f'<path d="M{x} 106v{drop}" stroke="{rim}" stroke-width="3" stroke-dasharray="4 3"/>'
        out += _bell(x, 106 + drop + 44, 1.0, fill, rim)
    return out


def _lantern(fill: str, rim: str) -> str:
    holes = "".join(f'<circle cx="{x}" cy="{y}" r="6" fill="#ffd36b" stroke="{rim}" stroke-width="2"/>' for x in (148, 180, 212) for y in (176, 212, 248))
    return (
        _shadow(cy=294, rx=80)
        + f'<path d="M152 132q28-44 56 0" fill="none" stroke="{rim}" stroke-width="6"/>'
        + f'<path d="M132 150h96l14 20v96l-14 22h-96l-14-22v-96z" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + holes
        + f'<path d="M124 170h112M124 266h112" stroke="{rim}" stroke-width="4"/>'
    )


def _cup(fill: str, rim: str) -> str:
    return (
        _shadow(cy=288, rx=86)
        + f'<path d="M118 160h124l-12 108q-50 14-100 0z" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + f'<ellipse cx="180" cy="160" rx="62" ry="12" fill="#8a3f22" stroke="{rim}" stroke-width="5"/>'
        + f'<path d="M238 180q40 4 30 40q-8 20-34 22" stroke="{rim}" stroke-width="8" fill="none"/>'
        + f'<path d="M132 196q48 18 96 0M136 228q44 16 88 0" stroke="{rim}" stroke-width="3" fill="none" stroke-dasharray="6 4"/>'
        + f'<path d="M160 206l20-12 20 12-20 12z" fill="none" stroke="{rim}" stroke-width="3"/>'
    )


def _samovar(fill: str, rim: str) -> str:
    return (
        _shadow(cy=294, rx=80)
        + f'<path d="M140 280h80l-8-18h-64z" fill="{fill}" stroke="{rim}" stroke-width="4"/>'
        + f'<path d="M136 262q-24-60 8-100h72q32 40 8 100z" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + f'<path d="M150 162q-6-26 30-34q36 8 30 34z" fill="{fill}" stroke="{rim}" stroke-width="5"/><circle cx="180" cy="120" r="8" fill="{rim}"/>'
        + f'<path d="M224 214h34v10" stroke="{rim}" stroke-width="6" fill="none"/><path d="M134 186q-26 10-18 40M226 186q26 10 18 40" stroke="{rim}" stroke-width="6" fill="none"/>'
        + f'<path d="M144 206q36 16 72 0" stroke="{rim}" stroke-width="3" fill="none" stroke-dasharray="5 4"/>'
    )


def _metal_bowl(fill: str, rim: str) -> str:
    return (
        _shadow(cy=288, rx=100)
        + f'<path d="M78 180h204q-8 74-66 98h-72q-58-24-66-98z" fill="{fill}" stroke="{rim}" stroke-width="5"/>'
        + f'<ellipse cx="180" cy="180" rx="104" ry="18" fill="#e7c36a" stroke="{rim}" stroke-width="5"/>'
        + f'<path d="M100 210q80 30 160 0M116 240q64 24 128 0" stroke="{rim}" stroke-width="3" fill="none" stroke-dasharray="6 4"/>'
        + "".join(f'<path d="M{x} 214q8 10 0 20q-8-10 0-20z" fill="{rim}" opacity=".7"/>' for x in (130, 160, 200, 230))
    )


def _pendant(glass: str, frame: str, cord: str = MAROON) -> str:
    return (
        f'<path d="M104 96q76 96 152 0" stroke="{cord}" stroke-width="4" fill="none"/>'
        + f'<circle cx="180" cy="150" r="7" fill="none" stroke="{frame}" stroke-width="4"/>'
        + f'<path d="M180 158l62 62-62 70-62-70z" fill="{frame}" stroke="{DARK}" stroke-width="4"/>'
        + f'<path d="M180 174l44 46-44 52-44-52z" fill="{glass}" stroke="{DARK}" stroke-width="3"/>'
        + f'<path d="M180 190l20 30-20 32-20-32z" fill="none" stroke="{frame}" stroke-width="3"/><circle cx="180" cy="220" r="6" fill="{frame}"/>'
        + f'<circle cx="180" cy="298" r="6" fill="{glass}" stroke="{frame}" stroke-width="3"/>'
    )


def _cuff(glass: str, frame: str) -> str:
    return (
        _shadow(cy=286, rx=96)
        + f'<path d="M88 176q92-54 184 0v72q-92-54-184 0z" fill="{frame}" stroke="{DARK}" stroke-width="5"/>'
        + f'<rect x="146" y="168" width="68" height="56" rx="8" fill="{glass}" stroke="{DARK}" stroke-width="4"/>'
        + f'<path d="M156 196q24-26 48 0q-24 26-48 0z" fill="none" stroke="{frame}" stroke-width="3"/><circle cx="180" cy="196" r="5" fill="{frame}"/>'
        + f'<path d="M100 196q30-12 40-8M220 188q20-4 40 8" stroke="{DARK}" stroke-width="3" fill="none"/>'
    )


def _bangles() -> str:
    colours = ["#a3262a", "#e0a526", "#2c6e49", "#a3262a", "#1d4a7a", "#e0a526"]
    out = _shadow(cy=286, rx=100)
    for i, c in enumerate(colours):
        y = 270 - i * 20
        out += f'<ellipse cx="180" cy="{y}" rx="86" ry="24" fill="none" stroke="{DARK}" stroke-width="15"/>'
        out += f'<ellipse cx="180" cy="{y}" rx="86" ry="24" fill="none" stroke="{c}" stroke-width="11"/>'
        out += "".join(f'<circle cx="{180 + dx}" cy="{y + 23}" r="2.6" fill="#fff4d6"/>' for dx in (-50, -25, 0, 25, 50))
    return out


def _juttis(fill: str) -> str:
    def shoe(x: float, y: float) -> str:
        return (
            f'<g transform="translate({x} {y})">'
            f'<path d="M0 30q-4-34 34-38h54q26 2 36 -18q6 18-2 34q-10 22-44 26H10q-10 0-10-4z" fill="{fill}" stroke="{DARK}" stroke-width="4"/>'
            f'<path d="M50 -8q18 14 44 8" stroke="#e5c38a" stroke-width="4" fill="none"/>'
            f'<path d="M58 4l6 6M74 2l6 6M90 -2l6 6" stroke="#e0a526" stroke-width="3"/><circle cx="70" cy="18" r="4" fill="#2c6e49"/></g>'
        )
    return _shadow(cy=290, rx=116) + shoe(62, 206) + shoe(96, 252)


def _pouch(fill: str, coin: bool = False) -> str:
    if coin:
        return (
            _shadow(cy=288, rx=90)
            + f'<path d="M104 176q76-40 152 0l10 90q-86 30-172 0z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
            + f'<path d="M112 176q68-26 136 0" stroke="{GOLD}" stroke-width="8" fill="none"/><circle cx="160" cy="160" r="8" fill="{GOLD}"/><circle cx="200" cy="160" r="8" fill="{GOLD}"/>'
            + f'<path d="M120 210q60 20 120 0" stroke="#e5c38a" stroke-width="3" stroke-dasharray="6 4" fill="none"/>'
        )
    return (
        _shadow(cy=290, rx=90)
        + f'<path d="M112 156h136l18 124H94z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M112 156q68 60 136 0" fill="#8a4424" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M150 150q30-50 60 0" stroke="{DARK}" stroke-width="6" fill="none"/>'
        + f'<path d="M110 236h140" stroke="#e5c38a" stroke-width="3" stroke-dasharray="6 4"/><circle cx="180" cy="196" r="8" fill="{GOLD}" stroke="{DARK}" stroke-width="3"/>'
    )


def _journal(fill: str) -> str:
    return (
        _shadow(cy=294, rx=96)
        + f'<path d="M106 110h132q20 0 20 20v160H126q-20 0-20-20z" fill="{PAPER}" stroke="{DARK}" stroke-width="4"/>'
        + f'<path d="M98 104h132q20 0 20 20v160H118q-20 0-20-20z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M124 124h104v136H124z" fill="none" stroke="#e5c38a" stroke-width="3" stroke-dasharray="6 4"/>'
        + f'<path d="M176 150l30 42-30 42-30-42z" fill="none" stroke="#e5c38a" stroke-width="4"/><circle cx="176" cy="192" r="7" fill="#e5c38a"/>'
        + f'<path d="M250 196h36" stroke="{DARK}" stroke-width="6" stroke-linecap="round"/>'
    )


def _bookmarks(fill: str) -> str:
    out = _shadow(cy=292, rx=100)
    for i, x in enumerate((110, 164, 218)):
        out += (
            f'<rect x="{x}" y="{120 + i * 8}" width="40" height="156" rx="4" fill="{fill}" stroke="{DARK}" stroke-width="4"/>'
            f'<path d="M{x + 20} {140 + i * 8}l12 16-12 16-12-16zM{x + 20} {190 + i * 8}l12 16-12 16-12-16z" fill="none" stroke="#e5c38a" stroke-width="3"/>'
            f'<circle cx="{x + 20}" cy="{128 + i * 8}" r="4" fill="{PAPER}"/><path d="M{x + 20} {124 + i * 8}q-10-26 6-30" stroke="{["#a3262a", "#2c6e49", "#1d4a7a"][i]}" stroke-width="4" fill="none"/>'
        )
    return out


def _basket(fill: str, bands: bool = False) -> str:
    b = f'<path d="M104 218h152M110 246h140" stroke="#a3262a" stroke-width="7"/><path d="M104 232h152" stroke="#2c6e49" stroke-width="5"/>' if bands else ""
    return (
        _shadow(cy=292, rx=96)
        + f'<path d="M126 180q54-110 108 0" stroke="{BRASS_DARK}" stroke-width="10" fill="none"/>'
        + f'<path d="M92 180h176l-20 104H112z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M86 172h188v16H86z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + b
    )


def _coiled_lidded(fill: str, accent: str = "#a3262a") -> str:
    return (
        _shadow(cy=292, rx=96)
        + f'<path d="M92 190q-4 80 40 96h96q44-16 40-96z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M96 214h168M100 238h160M110 262h140" stroke="{accent}" stroke-width="6"/>'
        + f'<path d="M84 190q96-96 192 0z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M110 168q70-44 140 0" stroke="#2c6e49" stroke-width="6" fill="none"/>'
        + f'<circle cx="180" cy="138" r="9" fill="{accent}" stroke="{DARK}" stroke-width="3"/>'
    )


def _hamper(fill: str) -> str:
    return (
        _shadow(cy=292, rx=110)
        + f'<path d="M82 156h196v130H82z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M74 140h212l-8 20H82z" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M82 196h196M82 240h196" stroke="#a3262a" stroke-width="6"/><path d="M82 218h196" stroke="#2c6e49" stroke-width="4"/>'
        + f'<path d="M150 140q30-34 60 0" stroke="{BRASS_DARK}" stroke-width="7" fill="none"/>'
    )


def _coasters(fill: str) -> str:
    out = _shadow(cy=292, rx=110)
    for i, (x, y) in enumerate(((120, 250), (236, 250), (178, 176))):
        out += (
            f'<ellipse cx="{x}" cy="{y}" rx="54" ry="36" fill="{fill}" stroke="{DARK}" stroke-width="4"/>'
            f'<ellipse cx="{x}" cy="{y}" rx="38" ry="25" fill="none" stroke="{["#a3262a", "#2c6e49", "#a3262a"][i]}" stroke-width="5"/>'
            f'<ellipse cx="{x}" cy="{y}" rx="20" ry="13" fill="none" stroke="#6b3fa0" stroke-width="4"/>'
        )
    return out


def _organizer(fill: str) -> str:
    out = _shadow(cy=292, rx=110)
    for x, h, w in ((96, 120, 60), (160, 160, 64), (228, 96, 56)):
        out += (
            f'<rect x="{x}" y="{284 - h}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{DARK}" stroke-width="4"/>'
            f'<ellipse cx="{x + w / 2}" cy="{284 - h}" rx="{w / 2}" ry="7" fill="#8a6a3e" stroke="{DARK}" stroke-width="3"/>'
        )
    out += '<path d="M184 124l-6-40M196 124l8-44" stroke="#3d0e19" stroke-width="5" stroke-linecap="round"/>'
    return out


def _ornament(fill: str) -> str:
    return (
        f'<path d="M180 96v34" stroke="{GOLD}" stroke-width="3"/><rect x="168" y="126" width="24" height="16" rx="4" fill="{GOLD}" stroke="{DARK}" stroke-width="3"/>'
        + f'<circle cx="180" cy="206" r="68" fill="{fill}" stroke="{DARK}" stroke-width="5"/>'
        + f'<path d="M112 206h136" stroke="{GOLD}" stroke-width="5"/><circle cx="180" cy="206" r="68" fill="none" stroke="{GOLD}" stroke-width="3" stroke-dasharray="4 5"/>'
        + f'<path d="M180 274v18" stroke="{GOLD}" stroke-width="4"/><circle cx="180" cy="296" r="6" fill="#a3262a"/>'
    )


# ---------------------------------------------------------------------------- painting subjects
def _frame(inner: str, bg: str = "#f4dfb3", frame: str = MAROON, border_pattern: str | None = None) -> str:
    border = f'<rect x="94" y="114" width="172" height="164" fill="none" stroke="url(#p-{border_pattern})" stroke-width="12"/>' if border_pattern else ""
    return (
        _shadow(cy=296, rx=100, ry=7)
        + f'<rect x="80" y="100" width="200" height="192" rx="6" fill="{frame}" stroke="{DARK}" stroke-width="4"/>'
        + f'<rect x="92" y="112" width="176" height="168" fill="{bg}"/>' + border
        + inner
    )


def _fish_pair() -> str:
    def fish(y: float, flip: bool) -> str:
        t = f"translate(180 {y}) scale({-1 if flip else 1} 1)"
        return (
            f'<g transform="{t}"><path d="M-58 0q30-34 70-10l20-16v52l-20-16q-40 24-70-10z" fill="#e0a526" stroke="{INK}" stroke-width="3"/>'
            f'<path d="M-30-14v28M-16-17v34M-2-16v32" stroke="#b0302a" stroke-width="4"/><circle cx="-44" cy="-4" r="4" fill="{INK}"/></g>'
        )
    return fish(170, False) + fish(228, True) + f'<path d="M110 199h140" stroke="{GREEN}" stroke-width="3" stroke-dasharray="6 5"/>'


def _peacock() -> str:
    feathers = "".join(
        f'<g transform="rotate({a} 196 206)"><path d="M196 206q-8-60 0-78q8 18 0 78z" fill="#2c6e49" stroke="{INK}" stroke-width="2"/><circle cx="196" cy="136" r="7" fill="#1d4a7a" stroke="#e0a526" stroke-width="3"/></g>'
        for a in (-70, -45, -20, 5, 30, 55)
    )
    return (
        feathers
        + f'<path d="M150 250q-10-50 30-58q12-30 6-50q-2-12 10-14q10 4 6 20l-6 40q30 16 20 62z" fill="#1d4a7a" stroke="{INK}" stroke-width="3"/>'
        + f'<circle cx="192" cy="130" r="3" fill="#fff"/><path d="M204 132l12 4-12 4" fill="#e0a526"/>'
        + f'<path d="M190 112l-4-10M196 112v-12M202 112l4-10" stroke="{INK}" stroke-width="2"/>'
        + f'<path d="M156 214q20 10 40 0M160 232q18 8 36 0" stroke="#e0a526" stroke-width="3" fill="none"/>'
    )


def _tree_of_life(bird: str = "#b0302a") -> str:
    leaves = "".join(
        f'<path d="M180 {y}q{s * 40} -24 {s * 60} -6q{-s * 30} 18 {-s * 60} 6z" fill="#2c6e49" stroke="{INK}" stroke-width="2"/>'
        for y in (150, 180, 210, 240) for s in (-1, 1)
    )
    return (
        f'<path d="M180 272V128" stroke="{BRASS_DARK}" stroke-width="8"/>' + leaves
        + f'<circle cx="180" cy="126" r="14" fill="#e0a526" stroke="{INK}" stroke-width="3"/>'
        + f'<path d="M116 262q14-18 30 0q-8 12-30 0zM214 262q14-18 30 0q-8 12-30 0z" fill="{bird}" stroke="{INK}" stroke-width="2"/>'
        + f'<path d="M140 272h80" stroke="{BRASS_DARK}" stroke-width="6"/>'
    )


def _lotus(bg_water: bool = False) -> str:
    petals = "".join(
        f'<path d="M180 232q{dx} -60 0 -96q{-dx} 36 0 96z" fill="{c}" stroke="{INK}" stroke-width="2.5" transform="rotate({a} 180 232)"/>'
        for a, dx, c in ((-60, 24, "#e88ea0"), (-30, 24, "#f2a7b4"), (0, 26, "#f7c1c9"), (30, 24, "#f2a7b4"), (60, 24, "#e88ea0"))
    )
    water = f'<path d="M96 262q21-10 42 0t42 0t42 0t42 0" stroke="#2f6fa3" stroke-width="4" fill="none"/>' if bg_water else ""
    return (
        f'<ellipse cx="136" cy="250" rx="34" ry="12" fill="#2c6e49" stroke="{INK}" stroke-width="2"/><ellipse cx="226" cy="252" rx="30" ry="10" fill="#2c6e49" stroke="{INK}" stroke-width="2"/>'
        + petals + water
    )


def _cat() -> str:
    return (
        f'<path d="M126 262q-10-62 34-86l-4-30 20 18h8l20-18-4 30q44 24 34 86z" fill="#f4f0e6" stroke="{INK}" stroke-width="4"/>'
        + f'<path d="M140 222q40 20 80 0M146 246q34 14 68 0" stroke="{INK}" stroke-width="4" fill="none"/>'
        + f'<circle cx="170" cy="176" r="4" fill="{INK}"/><circle cx="194" cy="176" r="4" fill="{INK}"/>'
        + f'<path d="M160 196q22 10 44 0" stroke="#b0302a" stroke-width="3" fill="none"/>'
        + f'<path d="M162 192q-26 4-34-6q10-12 34-4z" fill="#8aa7b8" stroke="{INK}" stroke-width="3"/>'
        + f'<path d="M234 250q24-8 20-40" stroke="{INK}" stroke-width="6" fill="none"/>'
    )


def _kalighat_figure() -> str:
    return (
        f'<path d="M150 272q-6-80 30-96q36 16 30 96z" fill="#e0a526" stroke="{INK}" stroke-width="4"/>'
        + f'<path d="M150 272q14-60 30-64q16 4 30 64" fill="#b0302a" opacity=".85"/>'
        + f'<ellipse cx="180" cy="152" rx="20" ry="24" fill="#f3d9b8" stroke="{INK}" stroke-width="4"/>'
        + f'<path d="M160 144q20-30 40 0q-4-24-20-26q-16 2-20 26z" fill="{INK}"/>'
        + f'<path d="M172 150q4-3 7 0M185 150q4-3 7 0" stroke="{INK}" stroke-width="2" fill="none"/><path d="M176 166q4 3 8 0" stroke="#b0302a" stroke-width="2" fill="none"/>'
        + f'<path d="M154 200q-26 10-30 40M206 200q26 6 26 30" stroke="{INK}" stroke-width="7" fill="none" stroke-linecap="round"/>'
        + f'<circle cx="232" cy="232" r="10" fill="#2c6e49" stroke="{INK}" stroke-width="3"/>'
    )


def _serpent() -> str:
    return (
        f'<path d="M120 256q-16-40 20-54t40-40q4-26 34-28" stroke="{INK}" stroke-width="16" fill="none" stroke-linecap="round"/>'
        + f'<path d="M120 256q-16-40 20-54t40-40q4-26 34-28" stroke="#2c8a57" stroke-width="10" fill="none" stroke-linecap="round"/>'
        + f'<path d="M120 256q-16-40 20-54t40-40q4-26 34-28" stroke="#f2c14e" stroke-width="3" fill="none" stroke-dasharray="4 6"/>'
        + f'<path d="M206 124q20-12 32 4q-10 16-30 10z" fill="#2c8a57" stroke="{INK}" stroke-width="3"/><circle cx="224" cy="126" r="3" fill="{INK}"/>'
        + f'<path d="M238 130l12 2M238 130l10 8" stroke="#b0302a" stroke-width="2"/>'
        + f'<path d="M232 256q14-22 22 0q-8 18-22 0z" fill="#e05a7a" stroke="{INK}" stroke-width="2"/><path d="M110 150q12-22 24 0q-12 16-24 0z" fill="#e05a7a" stroke="{INK}" stroke-width="2"/>'
    )


def _lake_palace() -> str:
    return (
        f'<rect x="92" y="112" width="176" height="96" fill="#7fb3c8"/><circle cx="234" cy="138" r="12" fill="#f7e6a6"/>'
        + f'<rect x="92" y="208" width="176" height="72" fill="#2f6fa3"/>'
        + f'<path d="M116 208v-40h128v40z" fill="#f4f0e6" stroke="{INK}" stroke-width="3"/>'
        + f'<path d="M132 168q14-26 28 0M200 168q14-26 28 0M164 168q16-34 32 0" fill="#f4f0e6" stroke="{INK}" stroke-width="3"/>'
        + "".join(f'<path d="M{x} 208v-18q7-10 14 0v18" fill="#2f6fa3" stroke="{INK}" stroke-width="2"/>' for x in (124, 148, 172, 196, 220))
        + f'<path d="M116 222h128M126 238h108M140 254h80" stroke="#bfe0ea" stroke-width="3" opacity=".7"/>'
    )


def _pichwai_lotus() -> str:
    return (
        f'<rect x="92" y="112" width="176" height="168" fill="#1f3d2e"/>'
        + "".join(f'<circle cx="{x}" cy="{y}" r="16" fill="#e88ea0" stroke="#f7c1c9" stroke-width="3"/><circle cx="{x}" cy="{y}" r="6" fill="#f2c14e"/>' for x in (122, 180, 238) for y in (146, 204))
        + "".join(f'<ellipse cx="{x}" cy="258" rx="26" ry="10" fill="#3f8f6b" stroke="#9fd0a8" stroke-width="2"/>' for x in (124, 180, 236))
    )


def _miniature_figure(bg: str = "#e0a526") -> str:
    return (
        f'<rect x="92" y="112" width="176" height="168" fill="{bg}"/><path d="M92 250h176v30H92z" fill="#2c6e49"/>'
        + f'<path d="M154 250q-4-66 26-76q30 10 26 76z" fill="#b0302a" stroke="{INK}" stroke-width="3"/>'
        + f'<circle cx="180" cy="158" r="16" fill="#f3d9b8" stroke="{INK}" stroke-width="3"/><path d="M168 146q12-20 26-2" fill="{INK}"/>'
        + f'<path d="M184 158l8 2" stroke="{INK}" stroke-width="2"/><path d="M132 250q-10-50 10-70q10 30 0 70zM228 250q10-50-10-70q-10 30 0 70z" fill="#3f8f6b" stroke="{INK}" stroke-width="2"/>'
    )


def _floral_miniature() -> str:
    flowers = "".join(
        f'<g transform="translate({x} {y})"><circle r="10" fill="{c}" stroke="{INK}" stroke-width="2"/><circle r="4" fill="#f2c14e"/></g>'
        for x, y, c in ((140, 160, "#b0302a"), (220, 160, "#e88ea0"), (180, 200, "#b0302a"), (136, 236, "#e88ea0"), (224, 236, "#b0302a"))
    )
    return (
        f'<rect x="92" y="112" width="176" height="168" fill="#f6ebc8"/>'
        + f'<path d="M180 270V150M140 160q20 30 40 40M220 160q-20 30-40 40M136 236q24-10 44-36M224 236q-24-10-44-36" stroke="#3f6b3a" stroke-width="4" fill="none"/>'
        + flowers
    )


def _pachedi() -> str:
    return (
        f'<rect x="92" y="112" width="176" height="168" fill="#6d1424"/>'
        + f'<path d="M154 262q-4-76 26-88q30 12 26 88z" fill="{INK}" stroke="#f4ead2" stroke-width="3"/>'
        + f'<circle cx="180" cy="158" r="16" fill="#f4ead2" stroke="{INK}" stroke-width="3"/><path d="M164 150q16-26 32 0" fill="#f4ead2" stroke="{INK}" stroke-width="3"/>'
        + f'<path d="M150 198l-24-16M210 198l24-16M150 214l-24 8M210 214l24 8" stroke="#f4ead2" stroke-width="4"/>'
        + "".join(f'<rect x="{x}" y="{y}" width="26" height="30" fill="none" stroke="#f4ead2" stroke-width="2"/><path d="M{x + 13} {y + 26}l-8-12h16z" fill="#f4ead2"/>' for x in (100, 234) for y in (122, 162, 202, 242))
    )


def _rogan_panel() -> str:
    left = "".join(
        f'<path d="M180 {y}q-50-6-56-34q34 0 56 34z" fill="{c}" stroke="#f2c14e" stroke-width="1.6"/>'
        f'<path d="M180 {y}q50-6 56-34q-34 0-56 34z" fill="{c}" stroke="#f2c14e" stroke-width="1.6"/>'
        for y, c in ((170, "#d6452f"), (210, "#3f8f6b"), (250, "#e0a526"))
    )
    return (
        f'<rect x="92" y="112" width="176" height="168" fill="#2b2233"/>'
        + f'<path d="M180 272V132" stroke="#f2c14e" stroke-width="4"/>' + left
        + f'<path d="M180 132q-16-22 0-30q16 8 0 30z" fill="#d6452f" stroke="#f2c14e" stroke-width="2"/>'
    )


def _basohli() -> str:
    return (
        f'<rect x="92" y="112" width="176" height="168" fill="#d8452f"/><rect x="104" y="124" width="152" height="144" fill="#f2c14e"/>'
        + f'<path d="M150 262q-4-66 30-80q34 14 30 80z" fill="#2c6e49" stroke="{INK}" stroke-width="3"/>'
        + f'<ellipse cx="180" cy="160" rx="18" ry="20" fill="#f3d9b8" stroke="{INK}" stroke-width="3"/>'
        + f'<path d="M164 160q2-24 16-26q14 2 16 26q-4-14-16-14t-16 14z" fill="{INK}"/><circle cx="186" cy="160" r="4" fill="#fff" stroke="{INK}" stroke-width="2"/>'
        + f'<path d="M120 140l10 10M240 140l-10 10" stroke="#b0302a" stroke-width="4"/>'
    )


def _painting_inner(name: str, text: str) -> str:
    if "fish" in name:
        return _frame(_fish_pair(), border_pattern="madhubani")
    if "peacock" in name:
        return _frame(_peacock(), border_pattern="madhubani")
    if "cat" in name:
        return _frame(_cat(), bg="#f7efdd")
    if "serpent" in name or "manjusha" in name:
        return _frame(_serpent(), bg="#f7d9df", border_pattern="madhubani")
    if "lake palace" in name or ("mewar" in name and "miniature" in name):
        return _frame(_lake_palace())
    if "pichwai" in name:
        return _frame(_pichwai_lotus())
    if "lotus" in name:
        return _frame(_lotus(), border_pattern="madhubani")
    if "basohli" in name:
        return _frame(_basohli())
    if "pahari" in name or "floral miniature" in name:
        return _frame(_floral_miniature())
    if "pachedi" in name or "mata ni" in name:
        return _frame(_pachedi(), frame=INK)
    if "rogan" in name:
        return _frame(_rogan_panel(), frame=INK)
    if "kalighat" in name:
        return _frame(_kalighat_figure(), bg="#f7efdd")
    if "tree" in name:
        return _frame(_tree_of_life(), border_pattern="madhubani")
    if "madhubani" in text or "mithila" in text:
        return _frame(_tree_of_life(), border_pattern="madhubani")
    return _frame(_floral_miniature())


# ---------------------------------------------------------------------------- main dispatcher
def _has(name: str, *words: str) -> bool:
    return any(w in name for w in words)


def artwork(product: dict) -> tuple[str, set[str]]:
    """Return (svg markup for the art area, set of pattern names used)."""
    name = product["name"].casefold()
    craft = product["craft"].casefold()
    text = " ".join(str(product.get(k, "")) for k in ("name", "material", "technique", "city", "description")).casefold()
    used: set[str] = set()

    def pat(p: str) -> str:
        used.add(p)
        return f"url(#p-{p})"

    blue_pottery = "blue pottery" in name
    metal_fill, metal_rim = ("#c9733f", "#6e3317") if "copper" in name else (BRASS, BRASS_DARK)
    terra_fill, terra_rim = (TERRA_LIGHT, "#6e2e17")

    # ---- paintings (checked before textiles: a "Rogan ... cushion panel" is still painted)
    if craft == "painting":
        if _has(name, "cushion"):
            return _cushion(pat("rogan")), used
        if _has(name, "shrine cloth"):
            return _wall_hanging("#6d1424") + _pachedi_overlay(), used
        if _has(name, "textile artwork"):
            return _wall_hanging(pat("rogan")), used
        inner = _painting_inner(name, text)
        if "url(#p-madhubani)" in inner:
            used.add("madhubani")
        return inner, used

    # ---- pottery / terracotta
    if craft == "pottery":
        fill, rim = (pat("blue"), INDIGO) if blue_pottery else (terra_fill, terra_rim)
        if _has(name, "horse"):
            return _horse(terra_fill, terra_rim), used
        if _has(name, "plate"):
            return _plate(fill, rim), used
        if _has(name, "vase"):
            return _vase(fill, rim), used
        if _has(name, "jar"):
            return _jar(fill, rim), used
        if _has(name, "diya"):
            return _diyas(terra_fill, terra_rim, 3), used
        if _has(name, "medallion"):
            return _tile(terra_fill, terra_rim, round_=True), used
        if _has(name, "temple", "relief plaque"):
            return _tile(terra_fill, terra_rim) + _relief_figure(terra_rim), used
        if _has(name, "tile", "plaque", "panel"):
            return _tile(pat("terracotta_relief") if "painted" not in name else "#d9a066", terra_rim) + _tree_of_life("#6e2e17").replace("#2c6e49", "#6e2e17"), used
        return _bowl(fill, rim), used

    # ---- metalwork
    if craft == "metalwork":
        if _has(name, "elephant"):
            return _elephant(metal_fill, metal_rim), used
        if _has(name, "figurine", "figure"):
            return _figurine(metal_fill, metal_rim), used
        if _has(name, "pendant"):
            return _pendant("#b9853a", metal_fill, cord="#6e3317"), used
        if _has(name, "lamp"):
            return _lantern(metal_fill, metal_rim), used
        if _has(name, "diya pair"):
            return _diyas(metal_fill, metal_rim, 2), used
        if _has(name, "diya"):
            return _diyas(metal_fill, metal_rim, 4), used
        if _has(name, "bell set", "bells", "hanging set"):
            return _bells(metal_fill, metal_rim, 4), used
        if _has(name, "bell"):
            return _bells(metal_fill, metal_rim, 1), used
        if _has(name, "samovar"):
            return _samovar(metal_fill, metal_rim), used
        if _has(name, "cup"):
            return _cup(metal_fill, metal_rim), used
        return _metal_bowl(metal_fill, metal_rim), used

    # ---- woodwork
    if craft == "woodwork":
        wood = pat("walnut") if _has(name, "walnut") else pat("wood")
        if _has(name, "tray"):
            return _tray(wood), used
        if _has(name, "jali", "panel"):
            return _jali_panel(wood), used
        return _box(wood), used

    # ---- papier-mache
    if "papier" in craft:
        fill = pat("naqashi") if _has(name, "naqashi") else pat("papier")
        if _has(name, "vase"):
            return _vase(fill, DARK), used
        if _has(name, "ornament"):
            return _ornament(fill), used
        if _has(name, "bowl"):
            return _bowl(fill, DARK), used
        return _lidded_round_box(fill, DARK), used

    # ---- jewellery
    if craft == "jewellery":
        if _has(name, "bangle"):
            return _bangles(), used
        if _has(name, "cuff"):
            return _cuff("#1f7a4d", "#d4a445"), used
        if _has(name, "kundan"):
            return _pendant("#b3212d", "#d4a445"), used
        return _pendant("#1f7a4d", "#d4a445"), used

    # ---- leatherwork
    if craft == "leatherwork":
        leather = pat("leather")
        if _has(name, "jutti", "mojari", "shoe"):
            return _juttis(pat("leather") if "embroidered" not in name else "#7a2230"), used
        if _has(name, "coin purse"):
            return _pouch(leather, coin=True), used
        if _has(name, "keepsake case", "box"):
            return _box(leather), used
        if _has(name, "pouch", "case"):
            return _pouch(leather), used
        if _has(name, "bookmark"):
            return _bookmarks(leather), used
        return _journal(leather), used

    # ---- basketry (sikki grass, jute, willow)
    if craft == "basketry":
        material = pat("jute") if _has(text, "jute") else pat("willow") if _has(text, "willow") else pat("sikki")
        if _has(name, "coaster"):
            return _coasters(material), used
        if _has(name, "organizer", "organiser"):
            return _organizer(material), used
        if _has(name, "hamper"):
            return _hamper(material), used
        if _has(name, "lidded", "jewellery", "box", "case", "keepsake"):
            return _coiled_lidded(material), used
        return _basket(material, bands=_has(text, "sikki")), used

    # ---- textiles (default)
    fill = pat(_textile_pattern(" ".join((name, str(product.get("technique", "")).casefold(), str(product.get("material", "")).casefold()))))
    if _has(name, "saree"):
        return _drape(fill, saree=True), used
    if _has(name, "kurta"):
        return _kurta(fill), used
    if _has(name, "cushion"):
        return _cushion(fill), used
    if _has(name, "runner"):
        return _runner(fill), used
    if _has(name, "mat set", "table mat", "table linen"):
        return _mats(fill), used
    if _has(name, "durrie", "rug", "floor mat"):
        return _rug(fill), used
    if _has(name, "wall", "panel", "hanging"):
        return _wall_hanging(fill), used
    if _has(name, "dupatta", "stole", "scarf", "shawl"):
        return _drape(fill), used
    return _wall_hanging(fill, tassels=False), used


def _pachedi_overlay() -> str:
    return (
        f'<path d="M160 268q-4-70 20-80q24 10 20 80z" fill="{INK}" stroke="#f4ead2" stroke-width="3"/>'
        f'<circle cx="180" cy="170" r="14" fill="#f4ead2" stroke="{INK}" stroke-width="3"/>'
        + "".join(f'<rect x="{x}" y="{y}" width="24" height="28" fill="none" stroke="#f4ead2" stroke-width="2"/>' for x in (112, 224) for y in (128, 170, 212))
    )


# ---------------------------------------------------------------------------- full card
def _wrap_title(title: str, max_chars: int = 30) -> list[str]:
    """One line if it fits, otherwise the most balanced two-line split."""
    if len(title) <= max_chars:
        return [title]
    words = title.split()
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(a), len(b))
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1] if best else [title]


def render_svg(product: dict) -> str:
    art, used = artwork(product)
    pats = _patterns()
    defs = "".join(pats[p] for p in sorted(used) if p in pats)
    title = product["name"]
    city = product.get("city") or product["origin"].split(",")[0]
    lines = _wrap_title(title)
    longest = max(len(line) for line in lines)
    size = 16 if longest <= 30 else 14
    if len(lines) == 1:
        title_svg = f'<text x="180" y="330" text-anchor="middle" font-family="Georgia,serif" font-size="{size}" font-weight="bold" fill="{DARK}">{escape(lines[0])}</text>'
        city_y = 356
    else:
        title_svg = "".join(
            f'<text x="180" y="{322 + i * 19}" text-anchor="middle" font-family="Georgia,serif" font-size="{size}" font-weight="bold" fill="{DARK}">{escape(line)}</text>'
            for i, line in enumerate(lines)
        )
        city_y = 362
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 420" role="img" aria-label="Illustration of {escape(title)}, {escape(city)}, {escape(product["region"])}">\n'
        f'<defs>{defs}</defs>\n'
        f'<rect width="360" height="420" rx="24" fill="{CREAM}"/><path d="M20 35h320v350H20z" fill="{PAPER}" stroke="#e3d7c4" stroke-width="3"/>\n'
        f'<text x="180" y="72" text-anchor="middle" font-family="Georgia,serif" font-size="17" fill="{MAROON}">KALAKRITI · CRAFT STUDY</text>\n'
        f'{art}\n'
        f'{title_svg}\n'
        f'<text x="180" y="{city_y}" text-anchor="middle" font-family="Arial,sans-serif" font-size="13" fill="{MUTED}">{escape(city)} · {escape(product["region"])}</text>\n'
        f'<text x="180" y="{city_y + 20}" text-anchor="middle" font-family="Arial,sans-serif" font-size="10" fill="{BRASS_DARK}">Original local academic/demo illustration</text></svg>'
    )
