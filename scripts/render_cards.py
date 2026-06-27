#!/usr/bin/env python3
"""Render accurate, private-inclusive GitHub profile cards as self-contained SVGs.

  render_cards.py --kind stats  < stats-graphql.json   > stats.svg
  render_cards.py --kind langs  < langs-graphql.json    > top-langs.svg

Input is the raw `gh api graphql` response. Cards are committed + refreshed by a
workflow, so unlike the public github-readme-stats instance they see private repos
(PRs 476 not 18) and never rate-limit. Static shapes + gradients only (GitHub strips
script/animation from README SVGs). `--selftest` checks both kinds.
"""
import sys
import json
import xml.dom.minidom as minidom

# ── palette (tokyo-night, matches metrics.svg / activity.svg) ───────────────
BG_A, BG_B = "#0F172A", "#0B1120"
TITLE = "#F8FAFC"
LABEL = "#94A3B8"
VALUE = "#F8FAFC"
ACCENT = "#22C55E"
RING_BG = "#1E293B"
FONT = "ui-monospace,'JetBrains Mono',Menlo,monospace"

LEVELS = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
THRESHOLDS = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def fmt(n):
    return f"{int(n):,}"


# ── rank: faithful port of github-readme-stats calculateRank (v2) ───────────
def calculate_rank(commits, prs, issues, reviews, stars, followers, all_commits=True):
    def exp_cdf(x):
        return 1 - 2 ** (-x)

    def log_normal_cdf(x):
        return x / (1 + x)

    cm = 1000 if all_commits else 250
    weights = {"c": 2, "p": 3, "i": 1, "r": 1, "s": 4, "f": 1}
    total_w = sum(weights.values())
    rank = 1 - (
        weights["c"] * exp_cdf(commits / cm)
        + weights["p"] * exp_cdf(prs / 50)
        + weights["i"] * exp_cdf(issues / 25)
        + weights["r"] * exp_cdf(reviews / 2)
        + weights["s"] * log_normal_cdf(stars / 50)
        + weights["f"] * log_normal_cdf(followers / 10)
    ) / total_w
    pct = rank * 100
    level = next(LEVELS[i] for i, t in enumerate(THRESHOLDS) if pct <= t)
    return level, pct


# ── small vector icons (~14px box), drawn in ACCENT ─────────────────────────
def _icon(kind, x, y, color=ACCENT):
    if kind == "star":
        d = ("M7 0.6 L8.9 4.9 L13.6 5.3 L10 8.4 L11.1 13 L7 10.5 "
             "L2.9 13 L4 8.4 L0.4 5.3 L5.1 4.9 Z")
        body = f'<path d="{d}" fill="{color}"/>'
    elif kind == "pr":
        body = (f'<circle cx="3" cy="3" r="2" fill="none" stroke="{color}" stroke-width="1.6"/>'
                f'<circle cx="3" cy="11" r="2" fill="none" stroke="{color}" stroke-width="1.6"/>'
                f'<circle cx="11" cy="11" r="2" fill="none" stroke="{color}" stroke-width="1.6"/>'
                f'<path d="M3 5 V9 M11 9 V7 a4 4 0 0 0 -4 -4 H5.2" fill="none" '
                f'stroke="{color}" stroke-width="1.6"/>')
    elif kind == "issue":
        body = (f'<circle cx="7" cy="7" r="6" fill="none" stroke="{color}" stroke-width="1.6"/>'
                f'<circle cx="7" cy="7" r="1.6" fill="{color}"/>')
    elif kind == "repo":
        body = (f'<path d="M2 1 H10 a1.2 1.2 0 0 1 1.2 1.2 V13 L7 11 L2.8 13 V2.2 '
                f'a1.2 1.2 0 0 1 1.2 -1.2 Z" fill="none" stroke="{color}" stroke-width="1.6"/>')
    else:
        body = f'<circle cx="7" cy="7" r="3" fill="{color}"/>'
    return f'<g transform="translate({x},{y})">{body}</g>'


def _bg(w, h):
    return (f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{BG_A}"/>'
            f'<stop offset="1" stop-color="{BG_B}"/></linearGradient></defs>'
            f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="12" '
            f'fill="url(#bg)" stroke="{RING_BG}" stroke-width="1"/>')


# ── stats card ──────────────────────────────────────────────────────────────
def parse_stats(raw):
    u = raw["data"]["user"]
    cc = u["contributionsCollection"]
    stars = sum(n["stargazerCount"] for n in u["repositories"]["nodes"])
    commits = cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
    return {
        "name": u.get("name") or "GitHub",
        "stars": stars,
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "contributed": cc["totalRepositoriesWithContributedCommits"],
        "reviews": cc["totalPullRequestReviewContributions"],
        "followers": u["followers"]["totalCount"],
        "commits": commits,
    }


def render_stats(d):
    W, H = 467, 195
    level, pct = calculate_rank(d["commits"], d["prs"], d["issues"],
                                d["reviews"], d["stars"], d["followers"])
    rows = [
        ("star", "Total Stars Earned", d["stars"]),
        ("pr", "Total PRs", d["prs"]),
        ("issue", "Total Issues", d["issues"]),
        ("repo", "Contributed to (last year)", d["contributed"]),
    ]
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" role="img" aria-label="{esc(d["name"])} GitHub stats">']
    s.append(_bg(W, H))
    s.append(f'<text x="25" y="34" font-family="{FONT}" font-size="18" font-weight="700" '
             f'fill="{ACCENT}">{esc(d["name"])}’s GitHub Stats</text>')

    ry = 66
    for kind, label, val in rows:
        s.append(_icon(kind, 26, ry - 11, ACCENT))
        s.append(f'<text x="50" y="{ry}" font-family="{FONT}" font-size="14" '
                 f'fill="{LABEL}">{esc(label)}:</text>')
        s.append(f'<text x="300" y="{ry}" font-family="{FONT}" font-size="14" '
                 f'font-weight="700" fill="{VALUE}">{fmt(val)}</text>')
        ry += 30

    # rank ring (right side); fill proportional to standing (higher rank = fuller)
    import math
    cx, cy, r = 393, 98, 40
    frac = max(0.04, min(1.0, (100 - pct) / 100))
    circ = 2 * math.pi * r
    s.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{RING_BG}" stroke-width="6"/>')
    s.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{ACCENT}" '
             f'stroke-width="6" stroke-linecap="round" '
             f'stroke-dasharray="{circ*frac:.1f} {circ:.1f}" '
             f'transform="rotate(-90 {cx} {cy})"/>')
    s.append(f'<text x="{cx}" y="{cy+7}" text-anchor="middle" font-family="{FONT}" '
             f'font-size="26" font-weight="700" fill="{TITLE}">{level}</text>')
    s.append('</svg>')
    return "\n".join(s)


# ── top-languages card ──────────────────────────────────────────────────────
def parse_langs(raw, top=8):
    agg = {}
    for repo in raw["data"]["user"]["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            api_color = e["node"]["color"]
            color = api_color or "#94A3B8"
            entry = agg.setdefault(name, {"size": 0, "color": color})
            entry["size"] += e["size"]
            if entry["color"] == "#94A3B8" and api_color:
                entry["color"] = api_color
    items = sorted(agg.items(), key=lambda kv: -kv[1]["size"])[:top]
    total = sum(v["size"] for _, v in items) or 1
    return [{"name": n, "color": v["color"], "pct": v["size"] * 100 / total}
            for n, v in items]


def render_langs(langs):
    W, H = 360, 195
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" role="img" aria-label="Most used languages">']
    s.append(_bg(W, H))
    s.append(f'<text x="22" y="32" font-family="{FONT}" font-size="16" font-weight="700" '
             f'fill="{ACCENT}">Most Used Languages</text>')

    # stacked bar
    bx, by, bw, bh = 22, 48, W - 44, 11
    x = bx
    for i, lg in enumerate(langs):
        w = bw * lg["pct"] / 100
        if i == len(langs) - 1:
            w = (bx + bw) - x
        rx = ' rx="5"' if i == 0 else ''
        s.append(f'<rect x="{x:.3f}" y="{by}" width="{max(0.5, w):.3f}" height="{bh}" '
                 f'fill="{lg["color"]}"{rx}/>')
        x += w

    # legend, 2 columns
    col_x = [22, 196]
    ly0 = 86
    for i, lg in enumerate(langs):
        col = i % 2
        row = i // 2
        lx = col_x[col]
        ly = ly0 + row * 26
        s.append(f'<circle cx="{lx+5}" cy="{ly-4}" r="5" fill="{lg["color"]}"/>')
        s.append(f'<text x="{lx+16}" y="{ly}" font-family="{FONT}" font-size="12" '
                 f'fill="{LABEL}">{esc(lg["name"])} '
                 f'<tspan fill="{VALUE}" font-weight="700">{lg["pct"]:.1f}%</tspan></text>')
    s.append('</svg>')
    return "\n".join(s)


def _selftest():
    # rank: faithful values + valid level
    lvl, pct = calculate_rank(4021, 476, 202, 10, 15, 22)
    assert lvl in LEVELS, lvl
    assert 0 <= pct <= 100
    # stats card from a synthetic raw response
    raw_s = {"data": {"user": {
        "name": "Emmi", "followers": {"totalCount": 22},
        "pullRequests": {"totalCount": 476}, "issues": {"totalCount": 202},
        "contributionsCollection": {"totalCommitContributions": 246,
            "restrictedContributionsCount": 3775,
            "totalPullRequestReviewContributions": 10,
            "totalRepositoriesWithContributedCommits": 7},
        "repositories": {"nodes": [{"stargazerCount": 11}, {"stargazerCount": 4}]}}}}
    d = parse_stats(raw_s)
    assert d["stars"] == 15 and d["prs"] == 476
    svg_s = render_stats(d)
    minidom.parseString(svg_s)
    # langs card + percentages sum ~100
    raw_l = {"data": {"user": {"repositories": {"nodes": [
        {"languages": {"edges": [{"size": 600, "node": {"name": "TypeScript", "color": "#3178c6"}},
                                 {"size": 400, "node": {"name": "Python", "color": "#3572A5"}}]}}]}}}}
    langs = parse_langs(raw_l)
    assert abs(sum(l["pct"] for l in langs) - 100) < 0.5
    svg_l = render_langs(langs)
    minidom.parseString(svg_l)
    import re
    for svg in (svg_s, svg_l):
        for dval in re.findall(r'<path d="([^"]+)"', svg):
            assert dval.lstrip().startswith("M"), dval[:20]
    print(f"selftest OK (rank={lvl} {pct:.1f}%)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--selftest":
        _selftest()
        sys.exit(0)
    kind = args[args.index("--kind") + 1] if "--kind" in args else "stats"
    raw = json.load(sys.stdin)
    if kind == "stats":
        sys.stdout.write(render_stats(parse_stats(raw)))
    elif kind == "langs":
        sys.stdout.write(render_langs(parse_langs(raw)))
    else:
        sys.exit(f"unknown --kind {kind}")
