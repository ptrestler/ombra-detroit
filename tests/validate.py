#!/usr/bin/env python3
"""Model checks. These guard the physics and the data, not the UI.
Run with `make test` or `python3 tests/validate.py`."""
import json, os, sys, calendar
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import build
from solar import solar_pos
from geo import to_xy
import city

# These checks read build/. On a fresh clone it is empty, so fail with the same
# message smoke.mjs gives rather than an opaque FileNotFoundError.
NEEDED = ["frames_meta.json", "ground_meta.json", "frames.npy", "segments.json", "graph.npz"]
_missing = [f for f in NEEDED if not os.path.exists(build(f))]
if _missing:
    print("build it first: make", file=sys.stderr)
    print("  missing from build/: " + ", ".join(_missing), file=sys.stderr)
    sys.exit(1)

LAT, LON = city.LAT0, city.LON0
fails = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    if not ok: fails.append(name)

print("\nsolar position")
# max elevation at solar noon must equal 90 - latitude +/- declination
for mo, day, dec, label in [(6,21,23.44,"summer solstice"), (12,21,-23.44,"winter solstice")]:
    tz = city.tz_for(2026, mo, day)
    best = max(solar_pos(2026,mo,day,h,m,LAT,LON,tz)[0]
               for h in range(9,17) for m in (0,15,30,45))
    expect = 90 - LAT + dec
    check(f"{label} peak elevation", abs(best-expect) < 0.6, f"{best:.1f} vs {expect:.1f}")

def crossing(mo, d, tz, rising):
    lo, hi = (0,13) if rising else (13,24)
    for _ in range(40):
        m = (lo+hi)/2
        e,_ = solar_pos(2026, mo, d, int(m), (m-int(m))*60, LAT, LON, tz)
        if (e < -0.833) == rising: lo = m
        else: hi = m
    m = (lo+hi)/2
    return f"{int(m):02d}:{int(round((m-int(m))*60)):02d}"
# published Detroit times, local clock: the solstices agree across
# sunrise-sunset.org and its peers; 20 March is sunrisesunsettime.org's
for mo,d,tz,rise,setq,label in [(6,21,-4,"05:56","21:13","Jun 21"),
                                (12,21,-5,"07:58","17:03","Dec 21"),
                                (3,20,-4,"07:36","19:45","Mar 20")]:
    got = (crossing(mo,d,tz,True), crossing(mo,d,tz,False))
    def mins(t): h,m = t.split(":"); return int(h)*60+int(m)
    ok = abs(mins(got[0])-mins(rise)) <= 4 and abs(mins(got[1])-mins(setq)) <= 4
    check(f"{label} sunrise/sunset", ok, f"{got[0]}/{got[1]} vs {rise}/{setq}")

print("\ndaylight saving (US: second Sunday of March to first Sunday of November)")
check("2026 DST window", city.dst_window(2026) == ((3, 8), (11, 1)),
      f"{city.dst_window(2026)}")
check("2027 DST window", city.dst_window(2027) == ((3, 14), (11, 7)),
      f"{city.dst_window(2027)}")
meta = json.load(open(build("frames_meta.json")))
tz = {(f["mo"], f["d"]): f["tz"] for f in meta}
check("March 1 is EST (-5)", tz[(3,1)] == -5, f"tz={tz[(3,1)]}")
check("March 15 is EDT (-4), a week after the change", tz[(3,15)] == -4, f"tz={tz[(3,15)]}")
check("November 1 is EST (-5): 2026 changes back that morning", tz[(11,1)] == -5, f"tz={tz[(11,1)]}")
check("October 15 is EDT (-4)", tz[(10,15)] == -4, f"tz={tz[(10,15)]}")

print("\nterrain")
gm = json.load(open(build("ground_meta.json")))
if "relief_rmse_m" in gm:
    check("relief beats the flat-earth model", gm["relief_rmse_m"] < gm["flat_rmse_m"] / 3,
          f"{gm['relief_rmse_m']} m vs {gm['flat_rmse_m']} m flat")
# bare earth: a tower must not stand on a copy of itself
check("the ground under the tallest towers is bare earth", abs(gm.get("tower_bump_m", 99)) < 2.0,
      f"{gm.get('tower_bump_m')} m under {gm.get('tower_n')} buildings, median {gm.get('tower_median_h')} m tall")

print("\nshade, 15 August (street names are stable OSM data)")
F = np.load(build("frames.npy")); segs = json.load(open(build("segments.json")))
S,W,N,E = city.S, city.W, city.N, city.E
bx0,by0 = to_xy(W,S); bx1,by1 = to_xy(E,N)
keep = []
for i, s in enumerate(segs):
    xs, ys = to_xy([p[0] for p in s["g"]], [p[1] for p in s["g"]])
    if xs.min()>=bx0 and xs.max()<=bx1 and ys.min()>=by0 and ys.max()<=by1: keep.append(i)
segs = [segs[i] for i in keep]; F = F[:, keep]
idx = {}
for j, s in enumerate(segs):
    if s["n"]: idx.setdefault(s["n"], []).append(j)
def shade(name, hour, day=15, mo=8):
    ids = idx.get(name)
    if not ids: return None
    di = (mo-1)*2 + (1 if day == 15 else 0)
    return float(F[di*32 + (hour-6)*2, ids].mean())
# wide open boulevards vs narrow lanes - these are qualitative facts about Rome
for name, hour, lo, hi in [("Via dei Fori Imperiali", 14, 0, 8),
                           ("Viale delle Terme di Caracalla", 14, 10, 45),
                           ("Via dei Coronari", 14, 80, 100),
                           ("Via Margutta", 14, 85, 100),
                           ("Via Giulia", 14, 70, 100)]:
    v = shade(name, hour)
    check(f"{name} at {hour}:00", v is not None and lo <= v <= hi,
          f"{v:.0f}%" if v is not None else "missing")
# terrain-driven: Piazza Trilussa sits under the Janiculum
v = shade("Piazza Trilussa", 18)
check("Piazza Trilussa shaded by the Janiculum at 18:00", v is not None and v > 85,
      f"{v:.0f}%" if v is not None else "missing")

print("\nrouting graph")
G = np.load(build("graph.npz"))
deg = np.bincount(np.r_[G["eU"], G["eV"]])
live = deg > 0
check("mean node degree looks like a street network", 2.3 <= 2*len(G["eU"])/live.sum() <= 3.0,
      f"{2*len(G['eU'])/live.sum():.2f}")
check("dead ends under 10%", (deg[live] == 1).mean() < 0.10,
      f"{(deg[live]==1).mean()*100:.1f}%")

print("\nopening hours")
from hours import parse as ph
check("plain week reads", ph("Mo-Sa 08:30-19:15; Su 09:00-17:45") ==
      [(4095, 0b0111111, [510, 1155]), (4095, 0b1000000, [540, 1065])])
g = ph("Oct-Jun Mo-Fr 07:30-12:30,16:30-19:30; Jul-Sep Mo-Fr 08:00-12:00")
check("month ranges wrap the year", g and g[0][0] == 0b111000111111 and g[1][0] == 0b000111000000)
check("public holidays are dropped, not guessed",
      ph("Mo-Fr 08:00-20:00; Sa,Su,PH 10:30-13:00,14:00-19:30")[1][1] == 0b1100000)
check("a closed day stays closed", ph("Mo-Su 09:00-18:00; Mo off")[1][2] == [])
check("what it cannot read, it refuses",
      all(ph(x) is None for x in ["closed", "Mar Su[-1]-Oct Su[-1] -1 day 08:00-19:00",
                                   "sunrise-sunset", "Mo-Fr 08:00-12:00 \"by appointment\"", ""]))

print(f"\n{'all checks passed' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
