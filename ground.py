"""Terrain for the shade model: which smoothing of the elevation tiles to use.

Two checks, depending on what the city gives us.

Relief, where the city has reference heights (city.RELIEF_POINTS/PAIRS): the
height difference between known points, scored for each smoothing, best one
wins. That is how Rome was done -- its tiles are a surface model with the
centro storico baked in, and three bare-earth corrections all made relief worse.

Bare earth, always: the tiles are sampled under the tallest tagged buildings
and compared with the ground ~100 m around them. In the US the tiles come from
USGS 3DEP, which is bare earth, so a 150 m tower should leave no bump at all; if
it did, the model would stand every building on a copy of itself. The number is
recorded and tests/validate.py holds it down.

Detroit has no reference pairs: it is a river terrace, ~175 m at the water and
~190 m in Midtown, 3 km away. Hills do not shadow anything here, and smoothing a
bare-earth grid only blurs the freeway trenches, which are real. So with no
relief to score, the raw grid stands.
"""
import json
import numpy as np
from scipy import ndimage as ndi
import city
from paths import build
from geo import to_xy

t = np.load(build("terr.npy")).astype(np.float64)
m = json.load(open(build("terr.json")))
TX0, TY0, TRES, TNY = m["TX0"], m["TY0"], m["RES"], m["NY"]

def sample(g, lat, lon):
    x, y = to_xy(lon, lat)
    c = int((x - TX0) / TRES); r = int(TNY - 1 - (y - TY0) / TRES)
    return float(g[np.clip(r, 0, g.shape[0]-1), np.clip(c, 0, g.shape[1]-1)])

P = getattr(city, "RELIEF_POINTS", None) or {}
PAIRS = getattr(city, "RELIEF_PAIRS", None) or []

def relief_rmse(g):
    e = np.array([sample(g,*P[a]) - sample(g,*P[b]) - r for a, b, r in PAIRS])
    return float(np.sqrt(np.mean(e**2))), float(e.mean())

out = {}
if PAIRS:
    flat = float(np.sqrt(np.mean(np.array([r for _,_,r in PAIRS], float)**2)))
    print(f"flat ground (no terrain at all)   relief RMSE {flat:5.1f} m")
    best = None
    for sig_m in (0, 20, 30, 50, 80):
        g = t if sig_m == 0 else ndi.gaussian_filter(t, sig_m / TRES)
        rmse, bias = relief_rmse(g)
        print(f"DEM terrain, {sig_m:2d} m smoothing       relief RMSE {rmse:5.1f} m  (bias {bias:+.1f})")
        if best is None or rmse < best[0]:
            best = (rmse, sig_m)
    rmse, sig_m = best
    out.update(relief_rmse_m=round(rmse, 1), flat_rmse_m=round(flat, 1))
    print(f"chosen: {sig_m} m smoothing, relief RMSE {rmse:.1f} m ({flat/rmse:.1f}x better than flat)")
else:
    sig_m = 0
    print("no relief references for this city: raw grid, no smoothing")
g = t if sig_m == 0 else ndi.gaussian_filter(t, sig_m / TRES)

# --- bare earth? the ground under the tallest tagged buildings ------------
from buildings import load
from city import S, W, N, E
tall = sorted((b for b in load() if b["src"] == "tag" and W <= b["c"][0] <= E and S <= b["c"][1] <= N),
              key=lambda b: -b["h"])[:25]
bumps = []
ring = ndi.uniform_filter(t, 21) * 21**2 - ndi.uniform_filter(t, 11) * 11**2   # 50-100 m annulus
ring /= (21**2 - 11**2)
for b in tall:
    bumps.append(sample(t, b["c"][1], b["c"][0]) - sample(ring, b["c"][1], b["c"][0]))
if bumps:
    bump = float(np.mean(bumps))
    print(f"under the {len(tall)} tallest tagged buildings (median {np.median([b['h'] for b in tall]):.0f} m): "
          f"ground reads {bump:+.1f} m against 50-100 m around them "
          f"(worst {max(bumps, key=abs):+.1f})")
    out.update(tower_bump_m=round(bump, 2), tower_n=len(tall),
               tower_median_h=round(float(np.median([b["h"] for b in tall])), 1))

lo, hi = np.percentile(t, [5, 95])
out.update(smoothing_m=sig_m, relief_p5_p95_m=round(float(hi - lo), 1))
print(f"relief across the grid, p5-p95: {hi-lo:.1f} m")
np.save(build("ground.npy"), g.astype(np.float32))
json.dump(out, open(build("ground_meta.json"), "w"))
print("-> build/ground.npy")
