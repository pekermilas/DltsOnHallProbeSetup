"""HDS-4 Hall/DLTS selector: circuit diagrams (rev 3: SELECT-only, one relay module, triax jacks, StandardFirmata).

Run:  python selector_schematic.py  ->  selector_signal_path.png, selector_control.png
Requires: matplotlib
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
K = '#222'
BLUE, GREEN, RED, GREY = '#1f5fa8', '#2e7d32', '#b71c1c', '#666'


def L(ax, *pts, c=K, lw=1.4, ls='-'):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=c, lw=lw, ls=ls, solid_capstyle='round')


def dot(ax, x, y, c=K):
    ax.plot(x, y, 'o', color=c, ms=4.5)


def box(ax, x, y, w, h, title, fc='#f4f6f8', ec=K, fs=10):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.3', fc=fc, ec=ec, lw=1.3))
    ax.text(x + w / 2, y + h + 0.8, title, ha='center', va='bottom', fontsize=fs, weight='bold')


def triax(ax, x, y, label):
    """Triax jack: outer (grey), guard (blue), centre (black). Returns terminal points."""
    for r, c in ((2.2, GREY), (1.5, BLUE), (0.5, K)):
        ax.add_patch(Circle((x, y), r, fill=False, ec=c, lw=1.3))
    ax.text(x, y + 3.0, label, ha='center', va='bottom', fontsize=9.5, weight='bold')
    return {'C': (x, y), 'G': (x, y - 1.5), 'S': (x, y - 2.2)}


def spdt(ax, x, y, name, c=K):
    """Changeover relay contact: common at (x,y); NC at (x+6,y+2.5), NO at (x+6,y-2.5). Drawn released (NC)."""
    L(ax, (x, y), (x + 1.5, y), c=c); dot(ax, x + 1.5, y, c)
    L(ax, (x + 1.5, y), (x + 4.4, y + 2.3), c=c)
    for dy, t in ((2.5, 'NC'), (-2.5, 'NO')):
        ax.plot(x + 4.5, y + dy, 'o', mfc='white', mec=c, ms=4.5)
        L(ax, (x + 4.5, y + dy), (x + 6, y + dy), c=c)
        ax.text(x + 4.5, y + dy + (0.7 if dy > 0 else -0.7), t, ha='center',
                va='bottom' if dy > 0 else 'top', fontsize=7, color=GREY)
    ax.text(x + 3, y + 4.4, name, ha='center', va='bottom', fontsize=8.5, color=c)
    return (x + 6, y + 2.5), (x + 6, y - 2.5)


# --------------------------------------------------------------------------
# 1. Signal path, one channel (repeat for P1..P4)
# --------------------------------------------------------------------------
def signal_path():
    fig = plt.figure(figsize=(15, 7.6), dpi=130)
    ax = fig.add_axes([0.01, 0.01, 0.98, 0.87]); ax.set_xlim(-6, 108); ax.set_ylim(-6, 52); ax.axis('off')
    fig.text(0.01, 0.955, 'HDS-4 signal path, one channel Pn (built 4 times: P1–P4)', fontsize=15, weight='bold')
    fig.text(0.01, 0.92, 'Relays shown released (no coil power) = HALL. Energized = DLTS. Each contact is a changeover, '
             'so Hall and DLTS are never connected together. Centre and guard are switched by two relays driven '
             'together; the outer shields are bonded to the case.', fontsize=9.5, color='#444', wrap=True)

    st = triax(ax, 4, 28, 'STAGE Pn\n(front)')
    hl = triax(ax, 100, 42, 'HALL Pn (rear)\n→ switch box Pn')
    dl = triax(ax, 100, 12, 'DLTS Pn (rear)\n→ MFIA')

    # Centre (black)
    yC = 32
    L(ax, st['C'], (9, 28), (9, yC), (36, yC)); nc, no = spdt(ax, 36, yC, 'K_Cn  (centre)')
    L(ax, nc, (64, nc[1]), (64, 44), (96, 44), (hl['C'][0] - 0.5, hl['C'][1]))
    L(ax, no, (70, no[1]), (70, 14), (96, 14), (dl['C'][0] - 0.5, dl['C'][1]))
    ax.text(84, 44.6, 'centre', fontsize=8); ax.text(84, 14.6, 'centre', fontsize=8)

    # Guard (blue)
    yG = 20
    L(ax, st['G'], (6, 26.5), (6, yG), (44, yG), c=BLUE); ncg, nog = spdt(ax, 44, yG, 'K_Gn  (guard)', c=BLUE)
    L(ax, ncg, (60, ncg[1]), (60, 40.5), (96, 40.5), (hl['G'][0] - 0.5, hl['G'][1]), c=BLUE)
    L(ax, nog, (76, nog[1]), (76, 10.5), (96, 10.5), (dl['G'][0] - 0.5, dl['G'][1]), c=BLUE)
    ax.text(84, 41.1, 'guard (inner shield)', fontsize=8, color=BLUE)
    ax.text(84, 11.1, 'guard (inner shield)', fontsize=8, color=BLUE)

    ax.text(42, 41, 'K_Cn and K_Gn coils driven together\nby one Nano pin (CONTROL Pn)', ha='center', fontsize=8.5,
            color=GREEN)

    # Outer shields
    yS = -2
    for j in (st, hl, dl):
        L(ax, j['S'], (j['S'][0], yS), c=GREY, ls='--')
    L(ax, (st['S'][0], yS), (hl['S'][0], yS), c=GREY, ls='--')
    ax.text(52, yS - 1.2, 'outer shields of all 12 jacks → common bus → case → earth lug', ha='center', va='top',
            fontsize=8.5, color=GREY)

    tx, ty = 18, 6
    ax.text(tx, ty + 3, 'Pn state     CONTROL Pn     K_Cn, K_Gn', fontsize=9, family='monospace', weight='bold')
    ax.text(tx, ty + 0.8, 'A = Hall     off (LOW)      released (NC)   <- also at boot and with no coil power',
            fontsize=9, family='monospace')
    ax.text(tx, ty - 1.4, 'B = DLTS     on  (HIGH)     energized (NO)', fontsize=9, family='monospace')
    fig.savefig(os.path.join(HERE, 'selector_signal_path.png'))
    plt.close(fig)


# --------------------------------------------------------------------------
# 2. Control and power wiring
# --------------------------------------------------------------------------
def control():
    fig = plt.figure(figsize=(15, 7.8), dpi=130)
    ax = fig.add_axes([0.01, 0.01, 0.98, 0.87]); ax.set_xlim(-4, 116); ax.set_ylim(-5, 56); ax.axis('off')
    fig.text(0.01, 0.955, 'HDS-4 control and power wiring (Arduino Nano with StandardFirmata + one 8-channel 5 V relay module)',
             fontsize=15, weight='bold')
    fig.text(0.01, 0.92, 'Use a HIGH-level-trigger relay module (IN = HIGH energizes = DLTS): StandardFirmata drives every pin LOW at boot, which must mean Hall. Each Nano pin drives two '
             'module inputs: the centre and guard relay of one channel. Remove the module\'s JD-VCC jumper: the coils run '
             'from the external 5 V supply through RELAY POWER.', fontsize=9.5, color='#444', wrap=True)

    inA = [46 - 3.2 * i for i in range(8)]
    box(ax, 0, 1, 16, 48, 'Arduino Nano')
    box(ax, 44, inA[-1] - 2.8, 22, inA[0] - inA[-1] + 5.6, 'Relay module (8 ch)', fc='#eef5ee')
    labs = ['K_C1', 'K_G1', 'K_C2', 'K_G2', 'K_C3', 'K_G3', 'K_C4', 'K_G4']
    for i, (y, t) in enumerate(zip(inA, labs)):
        ax.text(44.6, y, f'IN{i + 1}  {t}', ha='left', va='center', fontsize=8.5)

    pins = [('D2', 'CONTROL P1'), ('D3', 'CONTROL P2'), ('D4', 'CONTROL P3'), ('D5', 'CONTROL P4')]
    for i, (p, name) in enumerate(pins):
        y1, y2 = inA[2 * i], inA[2 * i + 1]
        ax.text(15.5, y1, p, ha='right', va='center', fontsize=9)
        ax.text(1, y1, name, ha='left', va='center', fontsize=7.5, color=GREY)
        L(ax, (16, y1), (44, y1), c=GREEN); dot(ax, 40, y1, GREEN)
        L(ax, (40, y1), (40, y2), (44, y2), c=GREEN)
    ax.text(55, inA[-1] - 3.6, 'VCC ← Nano 5V,  GND ← common GND', ha='center', va='top', fontsize=8, color=GREY)
    ax.text(8, 13, 'USB → PC\n(StandardFirmata,\npyfirmata2)', ha='center', va='center', fontsize=8.5)

    # External coil supply, RELAY POWER, JD-VCC
    box(ax, 82, 42, 22, 6.5, 'External 5 V, ≥ 1 A', fc='#fff6e5')
    ax.text(93, 45.2, '8 coils × ≈ 70 mA worst case', ha='center', va='center', fontsize=8)
    L(ax, (93, 42), (93, 37)); dot(ax, 93, 37)
    L(ax, (93, 37), (91.5, 34.3)); ax.plot(93, 34, 'o', mfc='white', mec=K, ms=4.5)
    ax.text(94.5, 35.5, 'RELAY POWER\n(front toggle)', fontsize=8.5, va='center')
    L(ax, (93, 34), (93, 28)); dot(ax, 93, 28)
    L(ax, (93, 28), (66.3, 28)); ax.text(70, 28.6, 'JD-VCC (switched 5 V)', fontsize=8)

    # Sense divider -> A0
    L(ax, (93, 28), (93, 24)); ax.text(94.5, 22.5, '10 kΩ', fontsize=8); L(ax, (93, 24), (93, 20))
    dot(ax, 93, 20); L(ax, (93, 20), (93, 16)); ax.text(94.5, 18, '10 kΩ', fontsize=8)
    L(ax, (91, 16), (95, 16)); ax.text(96, 16, 'GND', fontsize=8, va='center')
    L(ax, (93, 20), (108, 20), (108, 3), (16, 3), c=RED)
    ax.text(15.5, 3, 'A0', ha='right', va='center', fontsize=9)
    ax.text(60, 2.3, 'power sense → A0  (relay_power() = True above ≈ 2 V)', fontsize=8, color=RED, ha='center', va='top')

    # LEDs
    box(ax, 82, 6, 22, 6, 'Front LEDs (1 kΩ each)', fc='#f8f8f8')
    ax.text(93, 9, 'D10 HALL (green)\nD11 DLTS (blue)', ha='center', va='center', fontsize=8)
    L(ax, (16, 7), (81.7, 7), c=GREY)
    ax.text(15.5, 7, 'D10, D11', ha='right', va='center', fontsize=8.5)

    ax.text(-2, -4, 'Common GND: Nano GND, module GND, external supply 0 V. The case/earth lug is NOT joined to the signal '
            'guard or centre conductors. No coil power = every contact on HALL.', fontsize=8.5, color='#444')
    fig.savefig(os.path.join(HERE, 'selector_control.png'))
    plt.close(fig)


if __name__ == '__main__':
    signal_path()
    control()
    print('wrote selector_signal_path.png and selector_control.png')
