"""Where the height numbers in heights.py and CLAUDE.md come from.

OSM height tags are the only measurement this build has, so everything else is
an estimate made from them. This prints how much of the map is tagged, how the
two kinds of tag agree, and how wrong each way of estimating an untagged height
is, scored leave-one-out against the tags -- a building is never estimated from
itself. The shipped rule is scored by calling heights.estimate_untagged, so the
headline row describes the code that runs.

    python measure_heights.py            # needs data/, not build/

Run it after changing anything about heights, and paste the numbers rather
than adjusting them.
"""
import collections, re
import numpy as np
from buildings import load
from heights import (estimate_untagged, parse_len, DEFAULTS, LEVEL_M,
                     INTERP_MIN_M, INTERP_MAX_M, INTERP_RMSE_M)
from city import S, W, N, E

RNG = np.random.default_rng(11)      # bootstrap only; nothing shipped depends on it
BOOT = 2000

blds = [b for b in load() if W <= b["c"][0] <= E and S <= b["c"][1] <= N]
src = collections.Counter(b["src"] for b in blds)
n = len(blds)
print(f"{n:,} buildings in the bbox")
for k, lbl in (("tag", "height tag"), ("levels", "floor count only"), ("default", "neither")):
    print(f"  {lbl:<18} {src[k]:>7,}  {100*src[k]/n:5.1f} %")

def kind(b): return str(b["tags"].get("building", "yes")).lower()
print("\nBY TYPE   (the ten commonest; tagged = height or floors)")
by = collections.defaultdict(lambda: [0, 0])
for b in blds:
    by[kind(b)][0] += 1; by[kind(b)][1] += b["src"] != "default"
for t, (c, k) in sorted(by.items(), key=lambda kv: -kv[1][0])[:10]:
    print(f"  {t:<16} {c:>6,}   tagged {100*k/c:5.1f} %")

# --- floors -> metres, where a building carries both -------------------------
both = []
for b in blds:
    t = b["tags"]
    h = parse_len(t.get("height")) or parse_len(t.get("building:height"))
    lv = t.get("building:levels")
    try: lv = float(str(lv).split(";")[0])
    except (TypeError, ValueError): lv = None
    if h and lv and 1.5 <= h <= 400 and 0 < lv <= 120: both.append((lv, h))
if len(both) >= 10:
    L, H = np.array(both).T
    a, c = np.polyfit(L, H, 1)
    shipped = L * LEVEL_M + 1.2
    print(f"\nFLOORS AGAINST HEIGHT, on the {len(both):,} buildings that carry both")
    print(f"  fitted     height = {a:.2f} m x floors {c:+.2f} m   "
          f"RMSE {np.sqrt(np.mean((L*a+c-H)**2)):5.2f}")
    print(f"  shipped    height = {LEVEL_M:.2f} m x floors +1.20 m   "
          f"RMSE {np.sqrt(np.mean((shipped-H)**2)):5.2f}  bias {np.mean(shipped-H):+.2f}")

# --- estimating the untagged, leave-one-out against the tags -----------------
known = [b for b in blds if b["src"] != "default"]
unk = [b for b in blds if b["src"] == "default"]
KH = np.array([b["h"] for b in known])

def score(pred, label):
    e = pred - KH
    print(f"  {label:<40} RMSE {np.sqrt(np.mean(e**2)):5.2f}  MAE {np.mean(np.abs(e)):5.2f}  "
          f"bias {e.mean():+5.2f}")
    return e

print(f"\nESTIMATES, scored leave-one-out on the {len(known):,} tagged buildings")
ship = score(estimate_untagged(known, known, exclude_self=True),
             f"IDW k=15 <=500 m, clip {INTERP_MIN_M:.0f}-{INTERP_MAX_M:.0f} m (shipped)")
score(estimate_untagged(known, known, exclude_self=True, lo=0, hi=1e9), "IDW, unclipped")
for kk in (5, 30):
    score(estimate_untagged(known, known, k=kk, exclude_self=True), f"IDW k={kk}, clipped")
for lo, hi in ((3, 34), (3, 60), (5, 25)):
    score(estimate_untagged(known, known, exclude_self=True, lo=lo, hi=hi), f"IDW, clip {lo}-{hi} m")
score(np.array([DEFAULTS.get(kind(b), 17.0) for b in known], float), "per-type default (heights.DEFAULTS)")
score(np.full(len(known), float(np.median(KH))), "the median tag, everywhere")

k = RNG.integers(0, len(ship), (BOOT, len(ship)))
r = np.sqrt(np.mean(ship[k] ** 2, axis=1))
lo, hi = np.percentile(r, [2.5, 97.5])
print(f"\n  shipped RMSE {np.sqrt(np.mean(ship**2)):.2f} m, bootstrap [{lo:.2f}, {hi:.2f}]"
      f"   heights.INTERP_RMSE_M = {INTERP_RMSE_M:.2f}")

# The tagged buildings are not a random sample of the untagged ones: say how
# different the two populations are, because the score above is only as good
# as that resemblance.
def mix(sel):
    c = collections.Counter(kind(b) for b in sel); t = sum(c.values()) or 1
    return {k: c[k] / t for k in ("house", "yes", "commercial", "apartments", "garage", "industrial")}
mk, mu = mix(known), mix(unk)
print("\n  type mix, tagged vs untagged: " +
      "  ".join(f"{k} {100*mk[k]:.0f}/{100*mu[k]:.0f} %" for k in mk))
print(f"  footprint median, tagged vs untagged: "
      f"{np.median([b['area'] for b in known]):.0f} / {np.median([b['area'] for b in unk]):.0f} m^2")

# The untagged are not a sample of the tagged: score again on the tagged ones
# that look like them (small footprints), which is what an estimate is for.
AREA = np.array([b["area"] for b in known])
small = AREA <= max(60.0, float(np.percentile([b["area"] for b in unk], 75)) if unk else 60.0)
print(f"\nON THE {int(small.sum()):,} TAGGED BUILDINGS WITH FOOTPRINTS LIKE THE UNTAGGED (<= {AREA[small].max():.0f} m^2)")
def score_on(pred, label, m=small):
    e = pred[m] - KH[m]
    print(f"  {label:<40} RMSE {np.sqrt(np.mean(e**2)):5.2f}  MAE {np.mean(np.abs(e)):5.2f}  bias {e.mean():+5.2f}")
score_on(estimate_untagged(known, known, exclude_self=True), "IDW, shipped clip")
score_on(estimate_untagged(known, known, exclude_self=True, lo=0, hi=1e9), "IDW, unclipped")
score_on(estimate_untagged(known, known, exclude_self=True, lo=7, hi=34), "IDW, clip 7-34 m (Rome's floor)")
score_on(np.array([DEFAULTS.get(kind(b), 17.0) for b in known], float), "per-type default")
for v in (3.0, 4.0, 5.0):
    score_on(np.full(len(known), v), f"a flat {v:.0f} m")
print(f"  their median tag {np.median(KH[small]):.1f} m")

# where the tagged heights come from (Overture records it; raw OSM does not)
def hsrc(b): return b["tags"].get("height:source") or ("OSM levels" if b["src"] == "levels" else "OSM tag")
hs = collections.Counter(hsrc(b) for b in known)
if any(b["tags"].get("height:source") for b in known):
    print("\nHEIGHT SOURCES")
    for k, c in hs.most_common():
        sel = np.array([hsrc(b) == k for b in known])
        print(f"  {k:<24} {c:>6,}   median {np.median(KH[sel]) if sel.any() else 0:5.1f} m")
