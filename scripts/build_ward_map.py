"""Build data/geo/ward_map.json: ward outlines for the Ward map page (run once, needs internet).

    python scripts/build_ward_map.py            # downloads the boundaries, writes the JSON
    python scripts/build_ward_map.py --src DIR  # use already-downloaded geoBoundaries files

Source: geoBoundaries gbOpen, Bangladesh ADM4 and ADM3 (Bangladesh Bureau of Statistics and
OCHA ROAP, 2015 boundaries), licence CC BY 3.0 IGO. The app itself never downloads anything:
it only reads the JSON this script writes, so the map works offline.

How dataset wards are placed (the dataset has no locations, so this is illustrative):
- Dhaka: the census boundaries use the old Dhaka City Corporation numbering, wards 1 to 92.
  Wards 1 to 36 became Dhaka North and 37 to 92 Dhaka South, so DNCC_Ward_N is drawn on old
  ward N and DSCC_Ward_N on old ward 36 + N.
- Chattogram: CCC_Ward_N is drawn on ward N of the 41 Chattogram wards.
- Gazipur and Narayanganj: the boundaries have no city-corporation wards, so the city is drawn
  as its upazila outline (Gazipur Sadar, Narayanganj Sadar) with its 5 wards as dots inside.
Every other real ward of Dhaka and Chattogram is drawn in grey for context.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "geo" / "ward_map.json"
URL = ("https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/main/releaseData/gbOpen/BGD/"
       "{lvl}/geoBoundaries-BGD-{lvl}_simplified.geojson")
SOURCE = ("geoBoundaries gbOpen BGD ADM3/ADM4 (Bangladesh Bureau of Statistics, OCHA ROAP, 2015), "
          "CC BY 3.0 IGO")

DHAKA_BOX = (90.30, 90.52, 23.65, 23.91)        # lon_min, lon_max, lat_min, lat_max
CTG_BOX = (91.72, 91.92, 22.20, 22.52)
N_DNCC, N_DSCC, N_CCC, N_DOTS = 20, 20, 10, 5
TOL = 0.0002                                     # simplification tolerance in degrees (~20 m)
VIEW_W = 1000                                    # SVG width of each panel; height follows the shape


# --------------------------------------------------------------------------- geometry helpers
def rings(geom: dict) -> list[list[list[float]]]:
    """Outer rings of a Polygon or MultiPolygon."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [poly[0] for poly in geom["coordinates"]]


def inside(pt, ring) -> bool:
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def centroid(ring) -> tuple[float, float]:
    """Area centroid of a ring (falls back to the vertex mean for degenerate rings)."""
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    if abs(a) < 1e-12:
        return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
    return cx / (3 * a), cy / (3 * a)


def area(ring) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def simplify(points, tol=TOL):
    """Douglas-Peucker."""
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-12
    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = abs(dy * points[i][0] - dx * points[i][1] + x2 * y1 - y2 * x1) / norm
        if d > dmax:
            dmax, idx = d, i
    if dmax <= tol:
        return [points[0], points[-1]]
    return simplify(points[: idx + 1], tol)[:-1] + simplify(points[idx:], tol)


def simplify_ring(ring, tol=TOL):
    """Douglas-Peucker on a closed ring: split it at the vertex farthest from the first one."""
    far = max(range(len(ring)), key=lambda i: math.dist(ring[0], ring[i]))
    return simplify(ring[: far + 1], tol)[:-1] + simplify(ring[far:] + [ring[0]], tol)[:-1]


def in_box(pt, box) -> bool:
    return box[0] < pt[0] < box[1] and box[2] < pt[1] < box[3]


# --------------------------------------------------------------------------- selection
def numbered_wards(adm4: list[dict], box) -> dict[int, list]:
    """Ward number -> list of rings, for 'Ward No-NN' polygons whose centre is inside box."""
    out: dict[int, list] = {}
    for f in adm4:
        m = re.match(r"Ward No-(\d+)", f["properties"]["shapeName"])
        if not m:
            continue
        rs = rings(f["geometry"])
        if in_box(centroid(max(rs, key=area)), box):
            out.setdefault(int(m.group(1)), []).extend(rs)
    return out


def outline(adm3: list[dict], name: str) -> list:
    hit = [f for f in adm3 if f["properties"]["shapeName"] == name]
    if not hit:
        raise SystemExit(f"upazila {name!r} not found in ADM3")
    return rings(hit[0]["geometry"])


def dots_inside(rs: list, n: int) -> list[tuple[float, float]]:
    """n well-spread points inside the largest ring (a coarse grid, then farthest-point picking)."""
    ring = max(rs, key=area)
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    grid = []
    steps = 40
    for i in range(1, steps):
        for j in range(1, steps):
            pt = (min(xs) + (max(xs) - min(xs)) * i / steps, min(ys) + (max(ys) - min(ys)) * j / steps)
            if inside(pt, ring):
                grid.append(pt)
    # Lloyd's algorithm over the grid: n points that each sit in the middle of an equal share.
    chosen = sorted(grid)[:: max(1, len(grid) // n)][:n]
    for _ in range(30):
        groups = [[] for _ in chosen]
        for p in grid:
            groups[min(range(n), key=lambda k: math.dist(p, chosen[k]))].append(p)
        chosen = [(sum(q[0] for q in g) / len(g), sum(q[1] for q in g) / len(g)) if g else c
                  for g, c in zip(groups, chosen)]
    return sorted(chosen, key=lambda p: (-round(p[1], 3), p[0]))     # north to south, then west to east


# --------------------------------------------------------------------------- projection to SVG
class Panel:
    """Equirectangular projection (x scaled by cos(latitude)) fitted into a VIEW_W-wide box."""

    def __init__(self, all_rings: list, pad: float = 12):
        pts = [p for r in all_rings for p in r]
        self.lon0, self.lat1 = min(p[0] for p in pts), max(p[1] for p in pts)
        self.k = math.cos(math.radians(sum(p[1] for p in pts) / len(pts)))
        w = (max(p[0] for p in pts) - self.lon0) * self.k
        h = self.lat1 - min(p[1] for p in pts)
        self.s = (VIEW_W - 2 * pad) / w
        self.pad = pad
        self.height = round(h * self.s + 2 * pad)

    def xy(self, p) -> tuple[float, float]:
        return (round(self.pad + (p[0] - self.lon0) * self.k * self.s, 1),
                round(self.pad + (self.lat1 - p[1]) * self.s, 1))

    def path(self, rs: list) -> str:
        parts = []
        for r in rs:
            pts = [self.xy(p) for p in simplify_ring(r)]
            if len(pts) >= 3:
                parts.append("M" + "L".join(f"{x:g},{y:g}" for x, y in pts) + "Z")
        return "".join(parts)


def build(src: Path | None) -> dict:
    def load(lvl: str) -> list[dict]:
        if src:
            return json.loads((src / f"geoBoundaries-BGD-{lvl}_simplified.geojson").read_text())["features"]
        print(f"downloading {lvl} ...", flush=True)
        with urllib.request.urlopen(URL.format(lvl=lvl), timeout=120) as r:
            return json.loads(r.read())["features"]

    adm4, adm3 = load("ADM4"), load("ADM3")
    dhaka, ctg = numbered_wards(adm4, DHAKA_BOX), numbered_wards(adm4, CTG_BOX)
    dhaka = {n: r for n, r in dhaka.items() if 1 <= n <= 92}
    ctg = {n: r for n, r in ctg.items() if 1 <= n <= 41}
    missing = ([f"Dhaka {n}" for n in range(1, 37 + N_DSCC) if n not in dhaka]
               + [f"Chattogram {n}" for n in range(1, N_CCC + 1) if n not in ctg])
    if missing:
        raise SystemExit(f"boundaries missing for: {', '.join(missing)}")

    panels = []

    def ward_panel(key, title, wards: dict[int, list], mapping: dict[str, int]):
        pan = Panel([r for rs in wards.values() for r in rs])
        used = set(mapping.values())
        context = pan.path([r for n, rs in sorted(wards.items()) if n not in used for r in rs])
        shapes = []
        for ward_id, n in mapping.items():
            rs = wards[n]
            cx, cy = pan.xy(centroid(max(rs, key=area)))
            shapes.append({"ward_id": ward_id, "real_ward": n, "d": pan.path(rs), "label": [cx, cy]})
        panels.append({"key": key, "title": title, "width": VIEW_W, "height": pan.height,
                       "context": context, "wards": shapes, "dots": []})

    dhaka_map = {f"DNCC_Ward_{i:02d}": i for i in range(1, N_DNCC + 1)}
    dhaka_map |= {f"DSCC_Ward_{i:02d}": 36 + i for i in range(1, N_DSCC + 1)}
    ward_panel("dhaka", "Dhaka North and South", dhaka, dhaka_map)
    ward_panel("ctg", "Chattogram", ctg, {f"CCC_Ward_{i:02d}": i for i in range(1, N_CCC + 1)})

    for key, title, upazila, prefix in (("gcc", "Gazipur", "Gazipur Sadar", "GCC"),
                                        ("ncc", "Narayanganj", "Narayanganj Sadar", "NCC")):
        rs = outline(adm3, upazila)
        pan = Panel(rs)
        dots = [{"ward_id": f"{prefix}_Ward_{i:02d}", "xy": list(pan.xy(p))}
                for i, p in enumerate(dots_inside(rs, N_DOTS), 1)]
        panels.append({"key": key, "title": title, "width": VIEW_W, "height": pan.height,
                       "context": pan.path(rs), "wards": [], "dots": dots, "outline_of": upazila})

    return {"source": SOURCE, "note": "Illustrative placement; see scripts/build_ward_map.py.", "panels": panels}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", type=Path, help="folder with the downloaded geoBoundaries files")
    args = ap.parse_args(argv)
    data = build(args.src)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    n = sum(len(p["wards"]) + len(p["dots"]) for p in data["panels"])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(data['panels'])} panels, {n} dataset wards, "
          f"{OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
