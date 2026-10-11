#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Draw the Unio logos and dot bands into docs/brand/.

The logo is the word UNIO set in Doto (SIL OFL 1.1, The Doto Project
Authors). Each of Doto's dots is its own outline, so the script reads every
dot's place on the letter's grid and draws it as an even rounded square at
80 % of the dot spacing, the same way the website draws its titles.

  logo/single/   strokes one dot wide, as in the font (the website's logo)
  logo/double/   strokes two dots wide: every dot grows to a 2 x 2 block
  patterns/      dot bands: a checkerboard 3 to 5 rows thick, its edges
                 rising and falling along the band; five shapes, each also
                 mirrored

Every logo comes in one ink, the agent tones (a still moment of the wave) and
animated (a ring build-in from the top-left, then the tones flow through the
word as a wave, in clusters of neighboring dots, without end), for light and
for dark backgrounds.

Needs fontTools and the site's Doto package:
    cd site && npm install && cd .. && python3 tools/make-brand-assets.py
"""
from pathlib import Path
import math
import random

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs' / 'brand'
FONT = ROOT / 'site/node_modules/@fontsource-variable/doto/files/doto-latin-full-normal.woff2'

# Agent tones from the owner's "Cradle" reference: on dark, and the deeper
# variants the dashboard uses on light backgrounds.
TONES_DARK = ['#cb7f72', '#caaa72', '#74b4a5', '#91a2b6', '#8795c9', '#a094d1']
TONES_LIGHT = ['#8b3b2d', '#8a682e', '#2e6b5d', '#455a73', '#344483', '#433285']
INK_LIGHT = '#1c1c1c'   # dots on light backgrounds
INK_DARK = '#d4d4d4'    # dots on dark backgrounds (the site's soft off-white)

PITCH = 10.0            # output units between dot centers
SQUARE = PITCH * 0.8
ROUND = SQUARE * 0.12
CYCLE = 3600            # ms for one pass through the six tones


# ---- letters as grids of dots ---------------------------------------------

def letter_grids(text='UNIO', wght=800):
    """Each letter of `text` as a set of (column, row) dots, from Doto."""
    font = instantiateVariableFont(TTFont(FONT), {'wght': wght, 'ROND': 0})
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    raw = []
    for ch in text:
        pen = RecordingPen()
        glyphs[cmap[ord(ch)]].draw(pen)
        centers, points = [], []
        for op, args in pen.value:
            points.extend(args)
            if op in ('closePath', 'endPath') and points:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                centers.append(((min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2))
                points = []
        raw.append(centers)
    # dot spacing: the usual distance to the nearest dot within a letter
    nearest = sorted(min(math.dist(a, b) for j, b in enumerate(cs) if j != i)
                     for cs in raw for i, a in enumerate(cs))
    pitch = nearest[len(nearest) // 2]
    top = min(c[1] for cs in raw for c in cs)
    grids = []
    for cs in raw:
        left = min(c[0] for c in cs)
        grids.append({(round((x - left) / pitch), round((y - top) / pitch)) for x, y in cs})
    return grids


def thicken(grid):
    """Every dot grows to a 2 x 2 block: strokes two dots wide."""
    return {(c + dc, r + dr) for c, r in grid for dc in (0, 1) for dr in (0, 1)}


def layout(grids, gap):
    """Place letters side by side with `gap` empty columns between them;
    return dots (x, y, letter) in output units and the drawing size."""
    dots, col = [], 0
    for i, grid in enumerate(grids):
        for c, r in grid:
            dots.append({'x': (col + c + 1) * PITCH, 'y': (r + 1) * PITCH, 'letter': i, 'left': (col + 1) * PITCH})
        col += max(c for c, _ in grid) + 1 + gap
    width = (col - gap + 1) * PITCH + PITCH
    height = (max(r for g in grids for _, r in g) + 2) * PITCH + PITCH
    return dots, width, height


# ---- drawing --------------------------------------------------------------

def square(x, y, fill=None, extra=''):
    fill_attr = f' fill="{fill}"' if fill else ''
    return (f'<rect x="{x - SQUARE / 2:.2f}" y="{y - SQUARE / 2:.2f}" width="{SQUARE:.2f}" '
            f'height="{SQUARE:.2f}" rx="{ROUND:.2f}"{fill_attr}{extra}/>')


def svg(width, height, body, label='Unio', style=''):
    # a band has no label: it is decoration, hidden from screen readers
    a11y = f'role="img" aria-label="{label}"><title>{label}</title>' if label else 'aria-hidden="true">'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
            f'viewBox="0 0 {width:.2f} {height:.2f}" {a11y}{style}{body}</svg>\n')


def clusters(dots, width, seed=11):
    """Group dots into 2 x 2 clusters inside one letter; give each a phase
    (ms into the tone cycle): a wave along the word plus a little chance."""
    rng = random.Random(seed)
    groups = {}
    for d in dots:
        key = (d['letter'], int((d['x'] - d['left']) // (PITCH * 2)), int((d['y'] - PITCH) // (PITCH * 2)))
        groups.setdefault(key, []).append(d)
    out = []
    for members in groups.values():
        cx = sum(d['x'] for d in members) / len(members)
        phase = round(((cx / width) * 1800 + rng.random() * 600) / 100) * 100
        out.append((members, phase))
    return out


def tone_at(phase_ms, tones):
    """The tone a cluster shows at time 0 of the (stepped) cycle."""
    return tones[int((CYCLE - phase_ms) % CYCLE // (CYCLE / 6))]


def write_logos(folder, dots, width, height):
    folder.mkdir(parents=True, exist_ok=True)
    groups = clusters(dots, width)
    far = max(math.hypot(d['x'], d['y']) for d in dots)
    for mode, ink, tones in (('light', INK_LIGHT, TONES_LIGHT), ('dark', INK_DARK, TONES_DARK)):
        body = f'<g fill="{ink}">' + ''.join(square(d['x'], d['y']) for d in dots) + '</g>'
        (folder / f'unio-logo_{mode}.svg').write_text(svg(width, height, body))
        body = ''.join(f'<g fill="{tone_at(phase, tones)}">' + ''.join(square(d['x'], d['y']) for d in members) + '</g>'
                       for members, phase in groups)
        (folder / f'unio-logo_tones-{mode}.svg').write_text(svg(width, height, body))
        rng = random.Random(7)
        keyframes = ' '.join(f'{i * 100 / 6:.1f}% {{ fill: {tone}; }}' for i, tone in enumerate(tones)) + f' 100% {{ fill: {tones[0]}; }}'
        style = ('<style>'
                 'rect { transform-box: fill-box; transform-origin: center; opacity: 0;'
                 ' animation: grow .22s ease-out forwards; }'
                 f' g {{ fill: {tones[0]}; animation: tones {CYCLE / 1000}s steps(6, end) infinite; }}'
                 ' @keyframes grow { from { opacity: 1; transform: scale(.36); } to { opacity: 1; transform: none; } }'
                 f' @keyframes tones {{ {keyframes} }}'
                 f' @media (prefers-reduced-motion: reduce) {{ rect {{ animation: none; opacity: 1; }} g {{ animation: none; fill: {ink}; }} }}'
                 '</style>')
        body = ''
        for members, phase in groups:
            rects = ''.join(square(d['x'], d['y'], extra=f' style="animation-delay:{max(0, round(math.hypot(d["x"], d["y"]) / far * 900 + (rng.random() - .5) * 60))}ms"')
                            for d in members)
            body += f'<g style="animation-delay:{phase - CYCLE}ms">{rects}</g>'
        (folder / f'unio-logo_animated-{mode}.svg').write_text(svg(width, height, body, style=style))


def smooth(rng, columns, period):
    """A gently wandering value in 0..1 along the band (value noise)."""
    knots = [rng.random() for _ in range(columns // period + 3)]
    out = []
    for c in range(columns):
        i, f = divmod(c / period, 1)
        f = f * f * (3 - 2 * f)
        out.append(knots[int(i)] * (1 - f) + knots[int(i) + 1] * f)
    return out


def write_band(name, seed, columns=80, mirror=False):
    """A checkerboard band 3 to 5 rows thick: its top edge (row 0 or 1) and
    bottom edge (row 3 or 4) each wander along the band, so the thickness
    rises and falls. Tones flow from one end to the other."""
    rng = random.Random(seed)
    top = smooth(rng, columns, rng.choice((7, 9, 11)))
    bottom = smooth(rng, columns, rng.choice((6, 8, 10)))
    parity = seed % 2
    body = ''
    for col in range(columns):
        first = 0 if top[col] > 0.5 else 1
        last = 4 if bottom[col] > 0.5 else 3
        for row in range(first, last + 1):
            if (row + col + parity) % 2:
                continue
            place = columns - 1 - col if mirror else col
            reach = place / (columns - 1)
            tone = TONES_DARK[min(5, max(0, int(reach * 6 + rng.choice((-1, 0, 0, 0, 1)) * 0.5)))]
            body += square(place * PITCH + PITCH / 2, row * PITCH + PITCH / 2, fill=tone)
    (OUT / 'patterns' / f'{name}.svg').write_text(svg(columns * PITCH, 5 * PITCH, body, label=''))


def main():
    grids = letter_grids()
    write_logos(OUT / 'logo' / 'single', *layout(grids, gap=1))
    write_logos(OUT / 'logo' / 'double', *layout([thicken(g) for g in grids], gap=2))
    (OUT / 'patterns').mkdir(parents=True, exist_ok=True)
    for i, seed in enumerate((5, 12, 23, 38, 41), start=1):
        write_band(f'band-{i}', seed)
        write_band(f'band-{i}-mirrored', seed, mirror=True)
    for sub in ('logo/single', 'logo/double', 'patterns'):
        print(sub + ':', ', '.join(sorted(p.name for p in (OUT / sub).glob('*.svg'))))


if __name__ == '__main__':
    main()
