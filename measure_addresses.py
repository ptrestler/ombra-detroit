"""How far off is an address the page estimates rather than knows?

Leave-one-out on the mapped addresses: each plain number is placed by
interpolating between its nearest mapped neighbours on the same side (same
parity) of the same street, as the page does, and the distance to where it
really is gives the error. Reported by how far apart the neighbours' numbers
are, which is what addresses.MAX_GAP limits. Reads data/, not build/.

    python measure_addresses.py
"""
import collections, numpy as np
from paths import RAWOSM
import os
from geo import to_xy
from addresses import load, MAX_GAP

A = load(os.path.join(RAWOSM, "extra_addr.json"))
print(f"{len(A):,} addresses on {len({a[0] for a in A}):,} streets "
      f"({sum(1 for a in A if a[1] != a[2]):,} cover a range of numbers)")

by = collections.defaultdict(list)
for st, lo, hi, lon, lat, _ in A:
    if lo != hi: continue
    x, y = to_xy(lon, lat)
    by[(st, lo % 2)].append((lo, float(x), float(y)))
err, gap = [], []
for v in by.values():
    v = sorted(set(v))
    for i in range(1, len(v) - 1):
        (n0, x0, y0), (n, x, y), (n1, x1, y1) = v[i-1], v[i], v[i+1]
        if n1 == n0: continue
        f = (n - n0) / (n1 - n0)
        err.append(np.hypot(x0 + f*(x1-x0) - x, y0 + f*(y1-y0) - y)); gap.append(n1 - n0)
err, gap = np.array(err), np.array(gap)
print(f"\ninterpolated, leave-one-out, n={len(err):,}")
for lim in (20, 50, 100, MAX_GAP, 500, 10**9):
    m = gap <= lim
    lbl = "any gap" if lim == 10**9 else f"gap <= {lim}"
    print(f"  {lbl:<12} n={m.sum():>5,}   median {np.median(err[m]):4.0f} m   p90 {np.percentile(err[m], 90):4.0f} m")
print(f"\nshipped: addresses.MAX_GAP = {MAX_GAP}")
