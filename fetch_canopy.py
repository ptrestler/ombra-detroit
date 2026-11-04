"""Tree canopy height for the map, from Meta and WRI's global canopy height map.

The map otherwise knows only the trees someone mapped one by one - 4,814 of them
in Detroit - so a leafy residential street with no mapped trees reads as open
sun. This is a 1 m canopy height model (Tolan et al. 2024, "Very high
resolution canopy height maps from RGB imagery", CC BY 4.0), published as AWS
Open Data: s3://dataforgood-fb-data/forests/v1/alsgedi_global_v6_float/chm/,
one Web Mercator GeoTIFF per zoom-9 quadkey, a byte per pixel in metres.

ESA WorldCover (Overture's land_cover) was tried first and is useless for
this: at Overture's generalisation it calls 89.5 % of the box "urban" and its
"forest" is parks and vacant lots, median patch 24,500 m^2. No street tree.

The tile is read over HTTP for the bbox only and resampled onto the model's own
2 m grid (build_dsm.py's x0/y1/RES, so the two line up cell for cell), taking
the highest of the 1.2 m pixels that fall in each 2 m cell, so a narrow crown
is not averaged away. Written to data/canopy/chm2m.png (uint8 metres) with its
grid in chm2m.json; build_dsm.py decides how to use it.

    python fetch_canopy.py        # needs rasterio; the build does not

About 30 s: the bbox is ~70 MB of a 560 MB tile, read by range requests.
"""
import json, math, os
import numpy as np
from PIL import Image
from paths import DATA
from geo import to_xy, to_ll
from city import S, W, N, E

OUT = os.path.join(DATA, "canopy"); os.makedirs(OUT, exist_ok=True)
BASE = "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float/chm/"
RES = 2.0                                   # build_dsm.py's grid

def quadkey(lon, lat, z=9):
    n = 2 ** z; x = int((lon + 180) / 360 * n); lr = math.radians(lat)
    y = int((1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n)
    return "".join(str(((x >> i) & 1) + 2 * ((y >> i) & 1)) for i in range(z - 1, -1, -1))

qks = {quadkey(lo, la) for lo in (W, E) for la in (S, N)}
assert len(qks) == 1, f"the box spans several canopy tiles {qks}: read and stitch them"
QK = qks.pop()

def merc(lon, lat):
    r = 6378137.0
    return np.radians(lon) * r, r * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))

import rasterio
from rasterio.windows import from_bounds
# GDAL does not read HTTPS_PROXY by itself; behind a proxy that re-signs TLS,
# point CURL_CA_BUNDLE at its CA as well
if os.environ.get("HTTPS_PROXY"): os.environ.setdefault("GDAL_HTTP_PROXY", os.environ["HTTPS_PROXY"])
with rasterio.open("/vsicurl/" + BASE + QK + ".tif") as src:
    mx0, my0 = merc(W - 0.002, S - 0.002); mx1, my1 = merc(E + 0.002, N + 0.002)
    win = from_bounds(mx0, my0, mx1, my1, src.transform).round_offsets().round_lengths()
    chm = src.read(1, window=win)
    T = src.window_transform(win)
print(f"tile {QK}: read {chm.shape[1]} x {chm.shape[0]} px at {T.a:.2f} m")

# the 2 m grid, exactly as build_dsm.py builds it
x0, y0 = to_xy(W, S); x1, y1 = to_xy(E, N)
NX = int(math.ceil((x1 - x0) / RES)); NY = int(math.ceil((y1 - y0) / RES))
out = np.zeros((NY, NX), np.uint8)
# each 2 m cell takes the max of the source pixels in it: sample a 3x3 within the cell
for oy in (0.17, 0.5, 0.83):
    for ox in (0.17, 0.5, 0.83):
        gx = x0 + (np.arange(NX) + ox) * RES
        gy = y1 - (np.arange(NY) + oy) * RES
        lon, lat = to_ll(gx, gy)            # separable: lon from x, lat from y
        mx, my = merc(lon, lat)
        c = np.broadcast_to(((mx - T.c) / T.a).astype(np.int64)[None, :], out.shape)
        r = np.broadcast_to(((my - T.f) / T.e).astype(np.int64)[:, None], out.shape)
        ok = (c >= 0) & (c < chm.shape[1]) & (r >= 0) & (r < chm.shape[0])
        v = np.zeros_like(out); v[ok] = chm[r[ok], c[ok]]
        np.maximum(out, v, out=out)
Image.fromarray(out).save(os.path.join(OUT, "chm2m.png"), optimize=True)
json.dump({"source": f"Meta/WRI global canopy height v1, tile {QK} (CC BY 4.0)",
           "x0": x0, "y1": y1, "RES": RES, "NX": NX, "NY": NY,
           "bbox": [S, W, N, E]}, open(os.path.join(OUT, "chm2m.json"), "w"), indent=1)
print(f"-> data/canopy/chm2m.png {NX} x {NY}, {(out >= 3).mean()*100:.1f} % of cells >= 3 m, "
      f"{os.path.getsize(os.path.join(OUT, 'chm2m.png'))/1e6:.1f} MB")
