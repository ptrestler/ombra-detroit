import re
# Floors -> metres, fitted on the 1,248 Detroit buildings that carry both a
# measured (non-ML) height and a floor count: height = 3.70 x floors + 1.38
# (make heights). Rome's was 3.6 x floors + 1.2.
LEVEL_M, LEVEL_BASE_M = 3.70, 1.38
# Microsoft's ML heights read low wherever there is a floor count to check them
# against: below the floors estimate on 42 of the 48 Detroit buildings that have
# both, median -4.2 m [-6.5, -2.6], and by 10.9 m on 18 of 20 with 4+ floors
# (Millender Center, 33 floors, 20.6 m; One Campus Martius, 16 floors, 26 m).
# The floors estimate is unbiased, so on those buildings it wins.
# make heights prints the comparison.
ML_SOURCE = "Microsoft ML Buildings"
def parse_len(v):
    if v is None: return None
    v = str(v).strip().lower().replace(",", ".")
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*(m|meter|meters|metre|metres)?$", v)
    if m: return float(m.group(1))
    m = re.match(r"^(\d+(?:\.\d+)?)\s*'(?:\s*(\d+(?:\.\d+)?)\s*\")?$", v)
    if m: return (float(m.group(1))*12 + float(m.group(2) or 0))*0.0254
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*ft$", v)
    if m: return float(m.group(1))*0.3048
    return None
DEFAULTS = {"church":24,"cathedral":30,"chapel":12,"basilica":30,"garage":4,"garages":4,
            "shed":3,"hut":3,"roof":4,"carport":3,"kiosk":3,"ruins":8,"greenhouse":4,
            "civic":20,"public":20,"palace":24,"hotel":20,"apartments":19,"residential":18,
            "commercial":18,"retail":14,"school":14,"university":18,"office":20,
            "industrial":10,"warehouse":10,"train_station":15,"terrace":16,"house":9,
            "detached":9,"bungalow":5,"service":4,"toilets":3,"wall":3}
def levels(tags):
    """The floor count, or None."""
    lv = tags.get("building:levels") or tags.get("levels")
    try:
        n = float(str(lv).split(";")[0].split(",")[0]) if lv is not None else None
    except ValueError:
        return None
    return n if n is not None and 0 < n <= 120 else None

def building_height(tags):
    """Returns (height_m, source) where source in {tag, levels, default}."""
    h = parse_len(tags.get("height"))
    ml_with_floors = tags.get("height:source") == ML_SOURCE and levels(tags)
    if h and 1.5 <= h <= 400 and not ml_with_floors: return h, "tag"
    h = parse_len(tags.get("building:height"))
    if h and 1.5 <= h <= 400: return h, "tag"
    n = levels(tags)
    if n:
        extra = parse_len(tags.get("roof:height")) or 0
        return n*LEVEL_M + LEVEL_BASE_M + min(extra, 12), "levels"
    bt = str(tags.get("building","yes")).lower()
    if bt in DEFAULTS: return DEFAULTS[bt], "default"
    return 17.0, "default"

# ---- heights for the buildings OSM does not tag ----------------------------
# OSM tags are the only height measurement this build uses (Rome also had the
# Italian cadastre, via EUBUCCO, which covers Europe only).
# Every untagged building is estimated from its tagged neighbours, and this is
# the one function that does it, so measure_heights.py scores the rule the
# build actually runs. Numbers below come from `make heights` -- re-run it after
# changing anything here and paste what it says.
#
# INTERP_RMSE_M is not used to compute a height: it is how wrong an estimate is,
# measured, and build_dsm.py's OMBRA_JITTER probe moves every estimate by it to
# see how much of the map depends on the estimates. A stale value makes the
# sensitivity claim in the UI a fiction.
INTERP_K       = 15
INTERP_RADIUS  = 500.0
INTERP_MIN_M   = 3.0      # Rome's 7 m lifted every Detroit garage; see below
INTERP_MAX_M   = 34.0
# Detroit, Overture heights, the box widened to Mexicantown and New Center
# (make heights): the 651 untagged are small (75th percentile 74 m^2: garages,
# sheds), so the estimate is scored leave-one-out on the 2,581 tagged buildings
# of that size. Rome's 7 m floor scores RMSE 4.66 m, bias +1.71: it lifts every
# garage. A 3 m floor scores 4.43, bias +0.97 - better by 0.23 m, bootstrap
# [-0.26, -0.19] - and 6.48 m on every tagged building. Unclipped 4.55; a flat
# 5 m 4.65.
INTERP_RMSE_M  = 4.43


def estimate_untagged(known, unk, k=INTERP_K, radius=INTERP_RADIUS,
                      lo=INTERP_MIN_M, hi=INTERP_MAX_M, exclude_self=False):
    """Height for each building in `unk`, from the buildings in `known`.

    Inverse-distance weighted mean of the k nearest tagged buildings within
    `radius` m, clipped to [lo, hi]; the median tag where none is in reach.
    exclude_self drops the nearest neighbour, for leave-one-out scoring of
    `known` against itself.
    """
    import numpy as np
    from scipy.spatial import cKDTree
    from geo import to_xy
    KX, KY = to_xy([b["c"][0] for b in known], [b["c"][1] for b in known])
    KH = np.array([b["h"] for b in known])
    UX, UY = to_xy([b["c"][0] for b in unk], [b["c"][1] for b in unk])
    kk = k + 1 if exclude_self else k
    d, i = cKDTree(np.c_[KX, KY]).query(np.c_[UX, UY], k=kk, distance_upper_bound=radius)
    if exclude_self: d, i = d[:, 1:], i[:, 1:]
    ok = np.isfinite(d)
    w = np.where(ok, 1.0 / np.maximum(np.where(ok, d, 1.0), 1.0), 0.0)
    hk = KH[np.minimum(i, len(KH) - 1)]
    sw = w.sum(1)
    est = np.where(sw > 0, (w * hk).sum(1) / np.maximum(sw, 1e-12), float(np.median(KH)))
    return np.clip(est, lo, hi)
