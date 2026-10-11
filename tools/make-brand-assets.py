#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Draw the Unio logo and the README dot patterns into docs/brand/.

The logo is the word UNIO set in Doto (SIL OFL 1.1, The Doto Project
Authors). Each of Doto's dots is its own outline, so the script takes every
dot's center from the font and draws it as an even rounded square at 80 % of
the dot spacing, the same way the website draws its titles. Colored versions
use the agent tones; the animated ones build in as a ring from the top-left,
then let the tones flow through the word as a wave, in clusters of
neighboring dots inside one letter, without end.

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


def word_dots(text='UNIO', wght=800):
    """Dot centers of `text` in Doto, in font units, y down."""
    font = instantiateVariableFont(TTFont(FONT), {'wght': wght, 'ROND': 0})
    glyphs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font['hmtx']
    dots, letters, x = [], [], 0
    for i, ch in enumerate(text):
        name = cmap[ord(ch)]
        pen = RecordingPen()
        glyphs[name].draw(pen)
        points = []
        for op, args in pen.value:
            points.extend(args)
            if op in ('closePath', 'endPath') and points:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                dots.append({'x': x + (min(xs) + max(xs)) / 2, 'y': -(min(ys) + max(ys)) / 2, 'letter': i})
                points = []
        letters.append(x)
        x += hmtx[name][0]
    return dots, letters


def logo_layout():
    dots, letters = word_dots()
    centers = [(d['x'], d['y']) for d in dots]
    nearest = sorted(min(math.dist(a, b) for b in centers if b is not a) for a in centers)
    pitch = nearest[len(nearest) // 2]
    k = PITCH / pitch
    x0 = min(d['x'] for d in dots)
    y0 = min(d['y'] for d in dots)
    for d in dots:
        d['x'] = (d['x'] - x0) * k + PITCH
        d['y'] = (d['y'] - y0) * k + PITCH
    width = max(d['x'] for d in dots) + PITCH
    height = max(d['y'] for d in dots) + PITCH
    letter_x = [(lx - x0) * k + PITCH for lx in letters]
    return dots, letter_x, width, height


def square(x, y, fill=None, extra=''):
    fill_attr = f' fill="{fill}"' if fill else ''
    return (f'<rect x="{x - SQUARE / 2:.2f}" y="{y - SQUARE / 2:.2f}" width="{SQUARE:.2f}" '
            f'height="{SQUARE:.2f}" rx="{ROUND:.2f}"{fill_attr}{extra}/>')


def clusters(dots, letter_x, width, seed=11):
    """Group dots into 2 x 2 clusters inside one letter; give each a phase
    (ms into the tone cycle): a wave along the word plus a little chance."""
    rng = random.Random(seed)
    groups = {}
    for d in dots:
        key = (d['letter'], int((d['x'] - letter_x[d['letter']]) // (PITCH * 2)), int(d['y'] // (PITCH * 2)))
        groups.setdefault(key, []).append(d)
    out = []
    for members in groups.values():
        cx = sum(d['x'] for d in members) / len(members)
        phase = round(((cx / width) * 1800 + rng.random() * 600) / 100) * 100
        out.append((members, phase))
    return out


def svg(width, height, body, label='Unio', style=''):
    # a pattern has no label: it is decoration, hidden from screen readers
    a11y = f'role="img" aria-label="{label}"><title>{label}</title>' if label else 'aria-hidden="true">'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
            f'viewBox="0 0 {width:.2f} {height:.2f}" {a11y}{style}{body}</svg>\n')


def tone_at(phase_ms, tones):
    """The tone a cluster shows at time 0 of the (stepped) cycle."""
    return tones[int((CYCLE - phase_ms) % CYCLE // (CYCLE / 6))]


def write_logos():
    dots, letter_x, width, height = logo_layout()
    groups = clusters(dots, letter_x, width)
    for mode, ink, tones in (('light', INK_LIGHT, TONES_LIGHT), ('dark', INK_DARK, TONES_DARK)):
        # plain: one ink
        body = f'<g fill="{ink}">' + ''.join(square(d['x'], d['y']) for d in dots) + '</g>'
        (OUT / f'unio-logo_{mode}.svg').write_text(svg(width, height, body))
        # tones: a still frame of the wave
        body = ''.join(f'<g fill="{tone_at(phase, tones)}">' + ''.join(square(d['x'], d['y']) for d in members) + '</g>'
                       for members, phase in groups)
        (OUT / f'unio-logo_tones-{mode}.svg').write_text(svg(width, height, body))
        # animated: build in as a ring, then the tones flow without end
        far = max(math.hypot(d['x'], d['y']) for d in dots)
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
        (OUT / f'unio-logo_animated-{mode}.svg').write_text(svg(width, height, body, style=style))


def write_pattern(name, start, extras, seed, columns=80):
    """Two checkerboard rows of dots; `start` is where the first row begins
    ('odd' = 1st, 3rd, ... square; 'even' = 2nd, 4th, ...), the second row
    takes the other half. With `extras`, a third and a fourth row (above and
    below) carry stray dots that grow more frequent toward the right end."""
    rng = random.Random(seed)
    first = 0 if start == 'odd' else 1
    rows = {1: first, 2: 1 - first, 0: 1 - first, 3: first}   # checkerboard parity per row
    width, height = columns * PITCH, 4 * PITCH
    body = ''
    for row, parity in rows.items():
        for col in range(columns):
            if col % 2 != parity:
                continue
            reach = col / (columns - 1)
            if row in (0, 3):
                if not extras or rng.random() > 0.75 * max(0.0, (reach - 0.3) / 0.7) ** 1.6:
                    continue
            # tones flow along the band, a little out of step here and there
            tone = TONES_DARK[min(5, max(0, int(reach * 6 + rng.choice((-1, 0, 0, 0, 1)) * 0.5)))]
            body += square(col * PITCH + PITCH / 2, row * PITCH + PITCH / 2, fill=tone)
    (OUT / f'{name}.svg').write_text(svg(width, height, body, label=''))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    write_logos()
    write_pattern('pattern-even', 'even', extras=False, seed=1)
    write_pattern('pattern-odd', 'odd', extras=False, seed=2)
    write_pattern('pattern-even-plus', 'even', extras=True, seed=3)
    write_pattern('pattern-odd-plus', 'odd', extras=True, seed=4)
    print('wrote', ', '.join(sorted(p.name for p in OUT.glob('*.svg'))))


if __name__ == '__main__':
    main()
