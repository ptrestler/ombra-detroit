"""Named destinations for the From/To search: OSM landmarks, deduplicated against
the street names already in the payload, plus a curated shortlist shown when the
search box is empty. Writes build/places_pack.json."""
import collections, json, unicodedata
from paths import osm, build

def centre(el):
    if el["type"] == "node": return el.get("lon"), el.get("lat")
    c = el.get("center")
    return (c["lon"], c["lat"]) if c else (None, None)

# (label, test, base score). Order matters: first match wins.
CAT = [
 ("Station", lambda t: t.get("railway") in ("station","halt")
             or t.get("public_transport")=="station" or t.get("amenity")=="bus_station", 6),
 ("Area",    lambda t: t.get("place") in ("suburb","quarter","neighbourhood","city_block"), 6),
 ("Plaza",   lambda t: t.get("place")=="square"
             or (t.get("highway")=="pedestrian" and t.get("area")=="yes"), 4),
 ("Stadium", lambda t: t.get("leisure")=="stadium", 4),
 ("Museum",  lambda t: t.get("tourism") in ("museum","gallery"), 3),
 ("Park",    lambda t: t.get("leisure")=="park", 3),
 ("Bridge",  lambda t: bool(t.get("bridge")) and bool(t.get("highway")), 3),
 ("Sight",   lambda t: t.get("tourism") in ("attraction","viewpoint")
             or t.get("historic") in ("monument","archaeological_site","castle","city_gate",
                                      "ruins","aqueduct","building")
             or t.get("man_made")=="obelisk", 3),
 ("Church",  lambda t: t.get("amenity")=="place_of_worship" or t.get("historic")=="church", 1),
 ("Fountain",lambda t: t.get("amenity")=="fountain", 1),
 ("Theatre", lambda t: t.get("amenity") in ("theatre","university","arts_centre","library"), 3),
 ("Artwork", lambda t: t.get("tourism")=="artwork" or t.get("historic")=="memorial", 0),
]
def classify(t):
    for name, fn, base in CAT:
        if fn(t): return name, base
    return None, 0

def norm(s):
    s = s.replace("’","'").replace("‘","'")
    s = unicodedata.normalize("NFD", s.lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())

rows = {}
for el in json.load(open(osm("extra_poi.json")))["elements"]:
    t = el.get("tags", {}) or {}
    nm = (t.get("name") or "").strip()
    if not nm or len(nm) > 46: continue
    lon, lat = centre(el)
    if lon is None: continue
    cat, score = classify(t)
    if not cat: continue
    # a wikipedia/wikidata tag is the best available proxy for "worth listing"
    if t.get("wikipedia"): score += 3
    if t.get("wikidata"):  score += 2
    if t.get("wikipedia") and cat in ("Church","Fountain","Artwork"): score += 1
    if t.get("tourism") == "attraction": score += 1
    if nm not in rows or score > rows[nm]["s"]:
        rows[nm] = dict(n=nm, c=cat, s=score, lon=lon, lat=lat)

places = [r for r in rows.values() if r["s"] >= 3]
# the street index already covers these and resolves them better (real geometry)
street_names = sorted({s["n"] for s in json.load(open(build("segments.json"))) if s["n"]})
NS = {norm(n) for n in street_names}
places = [p for p in places if norm(p["n"]) not in NS]
places.sort(key=lambda r: (-r["s"], r["n"]))
print("places:", len(places), dict(collections.Counter(p["c"] for p in places)))

PI = {}
for i, p in enumerate(places): PI.setdefault(norm(p["n"]), i)
SI = {norm(n): n for n in street_names}
def resolve(label, key):
    n = norm(key)
    if n in PI: return [label, 0, PI[n]]
    if n in SI: return [label, 1, SI[n]]
    for k, i in PI.items():
        if k.startswith(n): return [label, 0, i]
    for k, v in SI.items():
        if k.startswith(n): return [label, 1, v]
    for k, i in PI.items():
        if n in k: return [label, 0, i]
    return None

# shown when the search box is empty; resolved against real data so the
# coordinates are never hand-typed
SHORTLIST = [
 ("Campus Martius", "Campus Martius Park"), ("Hart Plaza", "Hart Plaza"),
 ("Renaissance Center", "Renaissance Center"), ("Detroit Riverwalk", "Detroit RiverWalk"),
 ("Grand Circus Park", "Grand Circus Park"), ("Comerica Park", "Comerica Park"),
 ("Ford Field", "Ford Field"), ("Little Caesars Arena", "Little Caesars Arena"),
 ("Detroit Opera House", "Detroit Opera House"),
 ("Greektown", "Greektown"), ("Eastern Market", "Eastern Market"),
 ("Detroit Institute of Arts", "Detroit Institute of Arts"),
 ("Wayne State University", "Wayne State University"),
 ("Michigan Central", "Michigan Central"), ("Roosevelt Park", "Roosevelt Park"),
 ("Guardian Building", "Guardian Building"), ("Capitol Park", "Capitol Park"),
 ("Beacon Park", "Beacon Park"), ("Cadillac Square", "Cadillac Square"),
 ("Spirit of Detroit", "The Spirit of Detroit"), ("Dequindre Cut", "Dequindre Cut"),
 ("Huntington Place", "Huntington Place"), ("Corktown", "Corktown"),
 ("Midtown", "Midtown"), ("Lafayette Park", "Lafayette Park"),
 ("Charles H. Wright Museum", "The Wright Museum"),
 ("Woodward Avenue", "Woodward Avenue"),
]
top, missing = [], []
for label, key in SHORTLIST:
    r = resolve(label, key)
    (top if r else missing).append(r or label)
if missing: print("  shortlist entries with no match:", missing)
print("shortlist:", len(top))

# Map labels: names, never coordinates. Each resolves like the shortlist, to a
# place's own position or the middle of a named street's segments, and goes to
# the page in local metres. Tier 1 shows zoomed out, 3 only close in.
LABELS = [
 ("Midtown", "Midtown", 1), ("Corktown", "Corktown", 1),
 ("Eastern Market", "Eastern Market", 1), ("Greektown", "Greektown", 2),
 ("Lafayette Park", "Lafayette Park", 2), ("Brush Park", "Brush Park", 2),
 ("Woodbridge", "Woodbridge", 2),
 ("Cass Park", "Cass Park", 3), ("Campus Martius", "Campus Martius Park", 1),
 ("Hart Plaza", "Hart Plaza", 2), ("Grand Circus Park", "Grand Circus Park", 2),
 ("Renaissance Center", "Renaissance Center", 1), ("Comerica Park", "Comerica Park", 2),
 ("Ford Field", "Ford Field", 2), ("Little Caesars Arena", "Little Caesars Arena", 2),
 ("Wayne State", "Wayne State University", 2), ("DIA", "Detroit Institute of Arts", 2),
 ("Michigan Central", "Michigan Central", 1), ("Roosevelt Park", "Roosevelt Park", 3),
 ("Capitol Park", "Capitol Park", 3), ("Cadillac Square", "Cadillac Square", 3),
 ("Dequindre Cut", "Dequindre Cut", 3), ("Hudson's", "Hudson's Detroit", 2),
]
from geo import to_xy
SEGS = json.load(open(build("segments.json")))
def street_mid(name):
    pts = [p for s in SEGS if s["n"] == name for p in s["g"]]
    if not pts: return None
    # the vertex nearest the street's mean, so a curved street keeps its label on it
    mx = sum(p[0] for p in pts) / len(pts); my = sum(p[1] for p in pts) / len(pts)
    return min(pts, key=lambda p: (p[0]-mx)**2 + (p[1]-my)**2)
labels, nolab = [], []
for label, key, tier in LABELS:
    r = resolve(label, key)
    ll = None
    if r and r[1] == 0: ll = (places[r[2]]["lon"], places[r[2]]["lat"])
    elif r: ll = street_mid(r[2])
    if ll is None: nolab.append(label); continue
    x, y = to_xy(ll[0], ll[1])
    labels.append([label, round(float(x), 1), round(float(y), 1), tier])
if nolab: print("  map labels with no match:", nolab)
print("map labels:", len(labels))
json.dump({"places": places, "top": top, "labels": labels},
          open(build("places_pack.json"), "w"), ensure_ascii=False)
