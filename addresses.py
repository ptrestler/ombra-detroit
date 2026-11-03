"""Street addresses, so a walk can start at "1001 Woodward" rather than at
Woodward, which runs ten miles.

The source is OpenStreetMap's addr:housenumber/addr:street, from Overpass, in
data/osm/extra_addr.json, whichever city.SOURCE the rest of the map comes from:
Overture's address theme covers Windsor and the Oakland County suburbs and has
not one address in the City of Detroit (checked against release 2026-10-21.0).

What the page gets, per address: the street (an index into a list of names),
the lowest and highest number it covers, a position, and the label it was
mapped with. OSM writes one building's numbers several ways - "2462-2472",
"439;441", "2544,2546", "3627-B" - and all of them come down to a range.

The page answers a number nobody mapped by interpolating between the nearest
mapped numbers on the same side of the same street, and says it is an estimate.
measure_addresses.py scores that against the mapped ones; MAX_GAP is where the
estimate stops being worth showing, and it comes from there.
"""
import json, os, re

# Only estimate between two mapped numbers at most this far apart.
# measure_addresses.py, leave-one-out on the mapped numbers: with gaps <= 200
# the estimate is a median 12 m off, p90 40 m; with no limit, p90 65 m.
MAX_GAP = 200

_PART = re.compile(r"^\s*(\d+)\s*(?:-?\s*[A-Za-z])?\s*(?:-\s*(\d+)\s*[A-Za-z]?)?\s*$")

def parse_number(s):
    """(lo, hi) for an addr:housenumber, or None if it is not a number we read.
    "1001" -> (1001, 1001); "2462-2472", "439;441", "2544,2546" -> the span;
    "3627-B" -> (3627, 3627). A range only counts when it ascends: "12-3" is a
    unit, not a span."""
    if s is None: return None
    nums = []
    for part in re.split(r"[;,]", str(s)):
        if not part.strip(): continue
        m = _PART.match(part)
        if not m: return None
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) and int(m.group(2)) > a else a
        nums += [a, b]
    return (min(nums), max(nums)) if nums else None

def load(path):
    """Every address in the file: (street, lo, hi, lon, lat, label). Duplicates
    of one (street, number, place) - a building and its entrance node - once."""
    if not os.path.exists(path): return []
    out, seen = [], set()
    for e in json.load(open(path))["elements"]:
        t = e.get("tags", {}) or {}
        st = (t.get("addr:street") or "").strip()
        rng = parse_number(t.get("addr:housenumber"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        if not st or not rng or lon is None: continue
        k = (st, rng, round(lon, 4), round(lat, 4))
        if k in seen: continue
        seen.add(k)
        out.append((st, rng[0], rng[1], lon, lat, t["addr:housenumber"].strip()))
    return out
