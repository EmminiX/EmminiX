#!/usr/bin/env python3
"""Render a 6-month contribution activity chart as a self-contained SVG.

stdin : JSON array of {"date":"YYYY-MM-DD","count":N} (any order, any length)
stdout: SVG (tokyo-night, green area + glow line, month axis, peak marker)

GitHub sanitizes README SVGs (no <script>, SMIL animation often stripped), so
this uses only static shapes + <linearGradient> — guaranteed to render. The
"glow" is a fat translucent underlay stroke, not a filter.

Self-check: `render_activity.py --selftest` renders synthetic data and asserts
the SVG is well-formed with the expected point count.
"""
import sys
import json
import datetime as dt
import xml.dom.minidom as minidom

WINDOW_DAYS = 182

# ── geometry ────────────────────────────────────────────────────────────────
W, H = 900, 340
PAD_L, PAD_R, PAD_T, PAD_B = 58, 26, 64, 38
X0, X1 = PAD_L, W - PAD_R
Y0, Y1 = PAD_T, H - PAD_B

# ── palette (tokyo-night, matches the rest of the profile) ──────────────────
BG_A, BG_B = "#0F172A", "#0B1120"
GRID = "#1E293B"
AXIS = "#94A3B8"
TITLE = "#F8FAFC"
LINE = "#22C55E"
LINE_HI = "#4ADE80"
AREA_TOP = "#22C55E"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def load_days(raw):
    """Parse -> sort by date -> keep last WINDOW_DAYS. Returns [(date, count)]."""
    rows = []
    for r in raw:
        d = dt.date.fromisoformat(r["date"])
        rows.append((d, int(r["count"])))
    rows.sort(key=lambda t: t[0])
    return rows[-WINDOW_DAYS:]


def nice_max(m):
    """Round a peak up to a friendly axis ceiling."""
    if m <= 5:
        return 5
    for step in (10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if m <= step * 4:
            import math
            return int(math.ceil(m / step) * step)
    import math
    return int(math.ceil(m / 1000) * 1000)


def smooth_path(pts):
    """Catmull-Rom -> cubic bezier 'd' through the points (open curve)."""
    if not pts:
        return ""
    if len(pts) == 1:
        # single point (e.g. empty-data fallback): emit a bare moveto so the
        # path is still valid SVG (callers append L/Z for the area fill).
        return f"M {pts[0][0]:.2f} {pts[0][1]:.2f}"
    d = [f"M {pts[0][0]:.2f} {pts[0][1]:.2f}"]
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else pts[0]
        p1 = pts[i]
        p2 = pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else pts[n - 1]
        c1x = p1[0] + (p2[0] - p0[0]) / 6.0
        c1y = p1[1] + (p2[1] - p0[1]) / 6.0
        c2x = p2[0] - (p3[0] - p1[0]) / 6.0
        c2y = p2[1] - (p3[1] - p1[1]) / 6.0
        d.append(f"C {c1x:.2f} {c1y:.2f} {c2x:.2f} {c2y:.2f} {p2[0]:.2f} {p2[1]:.2f}")
    return " ".join(d)


def render(days):
    if not days:
        days = [(dt.date.today(), 0)]
    counts = [c for _, c in days]
    dates = [d for d, _ in days]
    total = sum(counts)
    peak = max(counts)
    ymax = nice_max(peak)
    n = len(days)

    def xpos(i):
        return X0 if n == 1 else X0 + (i / (n - 1)) * (X1 - X0)

    def ypos(v):
        return Y1 - (v / ymax) * (Y1 - Y0)

    pts = [(xpos(i), ypos(counts[i])) for i in range(n)]
    line_d = smooth_path(pts)
    area_d = f"{line_d} L {pts[-1][0]:.2f} {Y1:.2f} L {pts[0][0]:.2f} {Y1:.2f} Z"

    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Contribution activity, last 6 months">')
    # defs: bg + area gradients
    s.append('<defs>')
    s.append(f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="{BG_A}"/>'
             f'<stop offset="1" stop-color="{BG_B}"/></linearGradient>')
    s.append(f'<linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="{AREA_TOP}" stop-opacity="0.42"/>'
             f'<stop offset="0.7" stop-color="{AREA_TOP}" stop-opacity="0.08"/>'
             f'<stop offset="1" stop-color="{AREA_TOP}" stop-opacity="0"/>'
             f'</linearGradient>')
    s.append('</defs>')
    s.append(f'<rect x="0" y="0" width="{W}" height="{H}" rx="14" fill="url(#bg)"/>')

    # title + subtitle
    s.append(f'<text x="{W/2:.0f}" y="32" text-anchor="middle" '
             f'font-family="ui-monospace,Menlo,monospace" font-size="17" '
             f'font-weight="700" fill="{TITLE}" letter-spacing="0.5">last 6 months</text>')
    s.append(f'<text x="{W/2:.0f}" y="50" text-anchor="middle" '
             f'font-family="ui-monospace,Menlo,monospace" font-size="11" '
             f'fill="{AXIS}">{total:,} contributions · peak {peak}</text>')

    # y gridlines + labels (0,25,50,75,100%)
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        val = round(ymax * frac)
        y = ypos(val)
        s.append(f'<line x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}" '
                 f'stroke="{GRID}" stroke-width="1" stroke-dasharray="2 4"/>')
        s.append(f'<text x="{X0-10}" y="{y+3.5:.1f}" text-anchor="end" '
                 f'font-family="ui-monospace,Menlo,monospace" font-size="10" '
                 f'fill="{AXIS}">{val}</text>')

    # x month gridlines + labels at true month starts only (day==1), so the
    # partial first month doesn't collide with the next label.
    last_label_x = -999
    for i, d in enumerate(dates):
        if d.day != 1:
            continue
        x = xpos(i)
        if x - last_label_x < 34:   # belt-and-braces: never crowd two labels
            continue
        last_label_x = x
        s.append(f'<line x1="{x:.1f}" y1="{Y0}" x2="{x:.1f}" y2="{Y1}" '
                 f'stroke="{GRID}" stroke-width="1" stroke-opacity="0.6"/>')
        s.append(f'<text x="{x:.1f}" y="{Y1+20:.0f}" text-anchor="middle" '
                 f'font-family="ui-monospace,Menlo,monospace" font-size="10" '
                 f'fill="{AXIS}">{MONTHS[d.month-1]}</text>')

    # area + glow underlay + crisp line
    s.append(f'<path d="{area_d}" fill="url(#area)"/>')
    s.append(f'<path d="{line_d}" fill="none" stroke="{LINE}" stroke-opacity="0.20" '
             f'stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>')
    s.append(f'<path d="{line_d}" fill="none" stroke="{LINE}" '
             f'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')

    # peak marker + latest dot
    pi = counts.index(peak)
    px, py = pts[pi]
    s.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{LINE_HI}" '
             f'stroke="{BG_B}" stroke-width="2"/>')
    s.append(f'<text x="{px:.1f}" y="{py-10:.1f}" text-anchor="middle" '
             f'font-family="ui-monospace,Menlo,monospace" font-size="10" '
             f'font-weight="700" fill="{LINE_HI}">{peak}</text>')
    lx, ly = pts[-1]
    s.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{TITLE}"/>')

    # rotated y-axis caption
    s.append(f'<text x="16" y="{(Y0+Y1)/2:.0f}" text-anchor="middle" '
             f'font-family="ui-monospace,Menlo,monospace" font-size="10" '
             f'fill="{AXIS}" transform="rotate(-90 16 {(Y0+Y1)/2:.0f})">Contributions</text>')

    s.append('</svg>')
    return "\n".join(s)


def _selftest():
    base = dt.date.today() - dt.timedelta(days=200)
    raw = [{"date": (base + dt.timedelta(days=i)).isoformat(),
            "count": (i * 7) % 90} for i in range(200)]
    days = load_days(raw)
    assert len(days) == WINDOW_DAYS, f"expected {WINDOW_DAYS} got {len(days)}"
    svg = render(days)
    doc = minidom.parseString(svg)            # must be well-formed XML
    assert doc.getElementsByTagName("svg"), "no <svg>"
    assert svg.count("<path") >= 3, "expected area + glow + line paths"
    assert nice_max(282) >= 282 and nice_max(5) == 5
    assert smooth_path([(0, 0), (1, 1)]).startswith("M ")
    assert smooth_path([(3, 4)]) == "M 3.00 4.00"     # 1-point -> valid moveto
    # empty input -> single-point fallback: every path 'd' must start with M
    import re
    esvg = render(load_days([]))
    minidom.parseString(esvg)
    for dval in re.findall(r'<path d="([^"]+)"', esvg):
        assert dval.lstrip().startswith("M"), f"invalid path data: {dval[:24]!r}"
    print("selftest OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
        sys.exit(0)
    data = json.load(sys.stdin)
    sys.stdout.write(render(load_days(data)))
