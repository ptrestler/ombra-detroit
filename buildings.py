"""The OSM building outlines, loaded once and shared.

build_dsm.py rasterises them; measure_heights.py scores the height sources
against them. They have to agree about what a building is -- an outline that one
of them drops and the other keeps would quietly move every number in the report
away from the thing it claims to describe -- so the loader lives here rather
than in either.
"""
import glob, json
import numpy as np
from paths import osm
from geo import to_xy
from heights import building_height


def rings(el):
    """Outer rings of a way or multipolygon, as lists of (lon, lat)."""
    if el["type"] == "way":
        g = el.get("geometry")
        if g and len(g) >= 3: yield [(p["lon"], p["lat"]) for p in g]
    else:
        for m in el.get("members", []):
            if m.get("type") == "way" and m.get("role") in ("outer", ""):
                g = m.get("geometry")
                if g and len(g) >= 3: yield [(p["lon"], p["lat"]) for p in g]


def load(parts=False):
    """Every building in the tiles: height, where it came from, outline, centroid.

    Duplicated ways across tile boundaries are dropped by (type, id). With
    parts=True, the building:part elements instead -- the pieces a tower is
    drawn in. They are not buildings (they would double-count in every report)
    and only the raster uses them.
    """
    out, seen = [], set()
    for fn in sorted(glob.glob(osm("tiles/prt_*.json" if parts else "tiles/bld_*.json"))):
        for el in json.load(open(fn))["elements"]:
            k = (el["type"], el["id"])
            if k in seen: continue
            seen.add(k)
            t = el.get("tags", {}) or {}
            if not parts and "building" not in t: continue
            h, src = building_height(t)
            rr = list(rings(el))
            if not rr: continue
            pts = [p for r in rr for p in r]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            # footprint area of the outer rings, m^2 (local projection)
            area = 0.0
            for r in rr:
                xs, ys = to_xy([p[0] for p in r], [p[1] for p in r])
                area += abs(float(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))) / 2
            out.append(dict(h=h, src=src, rings=rr, c=(cx, cy), tags=t, area=area))
    return out
