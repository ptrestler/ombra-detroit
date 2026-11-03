"""The map's data from Overture Maps, written in the shape fetch_osm.py writes.

Overture is OpenStreetMap at its core -- the streets, the outlines, the water,
the parks, the trees, the fountains are all OSM, and the base themes even carry
the original tags -- plus heights from other sources: Esri Community Maps,
USGS lidar and Microsoft's ML buildings. It is on S3, which is reachable when
the Overpass mirrors are not, and pyarrow pushes the bbox down to the parquet
row-group statistics, so a whole fetch is a minute rather than an hour.

Everything is converted to Overpass JSON (ways with tags and inline geometry)
under data/overture/, file for file what data/osm/ holds, so nothing
downstream knows which source it is reading. city.SOURCE picks one.

What Overture does not carry, and so this build does not have:
  * opening_hours -- churches with readable hours ship empty
  * street width tags (Overture's width_rules are almost never set)
  * wikipedia/wikidata on places -- confidence stands in for it

Licences: the OSM-derived parts are ODbL; Esri Community Maps heights are
CC BY 4.0 with OSM waivers; Microsoft ML Buildings ODbL; USGS lidar public
domain. Attribution is in the page's methodology panel.

    python fetch_overture.py            # needs pyarrow and shapely; not the build
"""
import json, os, sys, time
import pyarrow.compute as pc, pyarrow.dataset as ds, pyarrow.fs as pafs
from shapely import wkb
from shapely.geometry import box, MultiPolygon, Polygon, LineString, MultiLineString, Point
import city
from paths import DATA

RELEASE = "2026-10-21.0"
ROOT = f"overturemaps-us-west-2/release/{RELEASE}"
OUT = os.path.join(DATA, "overture")
os.makedirs(os.path.join(OUT, "tiles"), exist_ok=True)
S, W, N, E = city.S, city.W, city.N, city.E
CLIP = box(W - 0.01, S - 0.01, E + 0.01, N + 0.01)   # a lake is bigger than a map

fs = pafs.S3FileSystem(anonymous=True, region="us-west-2",
                       proxy_options=os.environ.get("HTTPS_PROXY") or None)

def read(theme, typ, cols=None):
    t = time.time()
    f = ((pc.field("bbox", "xmin") <= E) & (pc.field("bbox", "xmax") >= W) &
         (pc.field("bbox", "ymin") <= N) & (pc.field("bbox", "ymax") >= S))
    d = ds.dataset(f"{ROOT}/theme={theme}/type={typ}", filesystem=fs, format="parquet")
    rows = d.to_table(columns=cols, filter=f, fragment_readahead=16).to_pylist()
    print(f"   {theme}/{typ}: {len(rows):,} in {time.time()-t:.0f}s", flush=True)
    return rows

def name(r):
    n = r.get("names") or {}
    return (n.get("primary") or "").strip()

def stags(r):
    """The OSM tags Overture kept, as a dict."""
    return {k: v for k, v in (r.get("source_tags") or [])}

def ll(coords):
    return [{"lat": round(y, 7), "lon": round(x, 7)} for x, y in coords]

_id = [0]
def nid():
    _id[0] += 1; return _id[0]

def areas(geom, tags, clip=True):
    """Polygon(s) as Overpass ways (one outer ring) or a multipolygon relation."""
    if clip and not geom.within(CLIP):
        geom = geom.intersection(CLIP)
    polys = [geom] if isinstance(geom, Polygon) else (
        list(geom.geoms) if isinstance(geom, MultiPolygon) else
        [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)])
    polys = [p for p in polys if not p.is_empty and len(p.exterior.coords) >= 4]
    if not polys: return None
    if len(polys) == 1:
        return {"type": "way", "id": nid(), "tags": tags, "geometry": ll(polys[0].exterior.coords)}
    return {"type": "relation", "id": nid(), "tags": tags,
            "members": [{"type": "way", "role": "outer", "geometry": ll(p.exterior.coords)} for p in polys]}

def centre(geom):
    c = geom.representative_point() if not isinstance(geom, Point) else geom
    return {"lat": round(c.y, 7), "lon": round(c.x, 7)}

def rep(el):
    """A point that stands for an element: its own, its centre, or its outline's."""
    if el["type"] == "node": return el["lon"], el["lat"]
    if el.get("center"): return el["center"]["lon"], el["center"]["lat"]
    g = el.get("geometry") or el["members"][0]["geometry"]
    return sum(p["lon"] for p in g) / len(g), sum(p["lat"] for p in g) / len(g)

def dump(fn, elements, clip=True):
    """Write a file, keeping only what lies in the city (see area.py)."""
    n0 = len(elements)
    if clip and elements:
        lon, lat = zip(*(rep(e) for e in elements))
        keep = area.inside(lon, lat)
        elements = [e for e, k in zip(elements, keep) if k]
    json.dump({"source": f"Overture Maps {RELEASE}", "elements": elements},
              open(os.path.join(OUT, fn), "w"))
    out = f" ({n0 - len(elements):,} outside {city.CITY} dropped)" if n0 != len(elements) else ""
    print(f"   -> {fn}: {len(elements):,} elements{out}", flush=True)

# --- the city itself: everything else is clipped to it (area.py) -------------
import area
from shapely.geometry import mapping
B = [r for r in read("divisions", "division_area", ["names", "subtype", "country", "geometry"])
     if r.get("subtype") == "locality" and r.get("country") == city.COUNTRY and name(r) == city.CITY]
if B:
    g = wkb.loads(B[0]["geometry"]).buffer(area.BUFFER_DEG).simplify(0.0001)
    polys = [g] if isinstance(g, Polygon) else list(g.geoms)
    rr = [list(p.exterior.coords) for p in polys] + [list(h.coords) for p in polys for h in p.interiors]
    json.dump({"source": f"Overture Maps {RELEASE}, locality {city.CITY} ({city.COUNTRY}), "
                         f"buffered {area.BUFFER_DEG} deg", "rings": [[[round(x, 6), round(y, 6)] for x, y in r] for r in rr]},
              open(area.PATH, "w"))
    print(f"   boundary: {city.CITY}, {len(rr)} ring(s) -> {os.path.relpath(area.PATH)}")
else:
    print(f"   no locality named {city.CITY} in {city.COUNTRY}: nothing clipped")
    if os.path.exists(area.PATH): os.remove(area.PATH)

def height_source(r):
    for s in r.get("sources") or []:
        if s.get("property") == "/properties/height": return s.get("dataset")
    return "OpenStreetMap" if r.get("height") is not None else None

# --- buildings and parts ----------------------------------------------------
bl = []
for r in read("buildings", "building", ["id", "names", "height", "num_floors", "class",
                                        "subtype", "sources", "geometry", "min_height"]):
    t = {"building": r.get("class") or "yes"}
    if r.get("height") is not None:
        t["height"] = f"{r['height']:.2f}"; t["height:source"] = height_source(r)
    if r.get("num_floors"): t["building:levels"] = str(r["num_floors"])
    if r.get("min_height"): t["min_height"] = f"{r['min_height']:.2f}"
    if name(r): t["name"] = name(r)
    el = areas(wkb.loads(r["geometry"]), t, clip=False)
    if el: bl.append(el)
dump("tiles/bld_all.json", bl)

pt = []
for r in read("buildings", "building_part", ["id", "height", "min_height", "num_floors",
                                             "sources", "geometry"]):
    t = {"building:part": "yes"}
    if r.get("height") is not None:
        t["height"] = f"{r['height']:.2f}"; t["height:source"] = height_source(r)
    if r.get("num_floors"): t["building:levels"] = str(r["num_floors"])
    if r.get("min_height"): t["min_height"] = f"{r['min_height']:.2f}"
    el = areas(wkb.loads(r["geometry"]), t, clip=False)
    if el: pt.append(el)
dump("tiles/prt_all.json", pt)

# --- streets ------------------------------------------------------------------
# The same classes fetch_osm.py asks Overpass for. Segments are split at
# connectors, so consecutive ones share an exact endpoint and graph.py joins them.
KEEP = {"primary", "secondary", "tertiary", "residential", "unclassified", "living_street",
        "pedestrian", "footway", "steps", "path", "service", "track"}
st = []; nofoot = 0
for r in read("transportation", "segment", ["id", "names", "subtype", "class", "subclass",
                                            "road_flags", "level_rules", "access_restrictions",
                                            "geometry"]):
    if r.get("subtype") != "road" or r.get("class") not in KEEP: continue
    g = wkb.loads(r["geometry"])
    lines = [g] if isinstance(g, LineString) else list(getattr(g, "geoms", []))
    flags = {v for f in (r.get("road_flags") or []) if not f.get("between") for v in f["values"]}
    if "is_under_construction" in flags or "is_abandoned" in flags: continue
    # closed to walking along its whole length (the Detroit-Windsor Tunnel,
    # freeway service drives): not a street anyone can be routed down
    if any(x.get("access_type") == "denied" and not x.get("between") and
           "foot" in ((x.get("when") or {}).get("mode") or []) for x in (r.get("access_restrictions") or [])):
        nofoot += 1; continue
    t = {"highway": r["class"]}
    if name(r): t["name"] = name(r)
    sc = r.get("subclass")
    if sc in ("parking_aisle", "driveway", "alley"): t["service"] = sc
    if sc in ("sidewalk", "crosswalk"): t["footway"] = sc
    if "is_tunnel" in flags: t["tunnel"] = "yes"
    if "is_covered" in flags: t["covered"] = "yes"
    if "is_bridge" in flags: t["bridge"] = "yes"
    lv = [x.get("value") for x in (r.get("level_rules") or []) if not x.get("between")]
    if lv and lv[0] is not None and lv[0] < 0: t["layer"] = str(lv[0])
    for ln in lines:
        if len(ln.coords) >= 2:
            st.append({"type": "way", "id": nid(), "tags": t, "geometry": ll(ln.coords)})
# Pedestrian plazas: Overture keeps them in land_use, as areas. fetch_osm.py
# takes them as highway=pedestrian + area=yes ways, which streets.py walks round
# the edge of -- and severing them was the worst thing the Rome network did.
LU = read("base", "land_use", ["id", "names", "subtype", "class", "source_tags", "wikidata", "geometry"])
nplaza = 0
for r in LU:
    if r.get("subtype") != "pedestrian": continue
    g = wkb.loads(r["geometry"])
    polys = [g] if isinstance(g, Polygon) else list(getattr(g, "geoms", []))
    t = {"highway": "pedestrian", "area": "yes"}
    if name(r): t["name"] = name(r)
    for p in polys:
        if isinstance(p, Polygon):
            st.append({"type": "way", "id": nid(), "tags": t, "geometry": ll(p.exterior.coords)}); nplaza += 1
print(f"   plazas as perimeters: {nplaza}   closed to foot, dropped: {nofoot}")
dump("tiles/str_all.json", st)

# --- water, green, trees, fountains --------------------------------------------
wa = []
for r in read("base", "water", ["id", "names", "subtype", "class", "geometry"]):
    g = wkb.loads(r["geometry"])
    if r.get("class") in ("fairway",) or not isinstance(g, (Polygon, MultiPolygon)): continue
    t = {"natural": "water", "water": r.get("class") or ""}
    if name(r): t["name"] = name(r)
    el = areas(g, t)
    if el: wa.append(el)
dump("extra_water.json", wa, clip=False)      # the river is drawn whole

LAND = read("base", "land", ["id", "names", "subtype", "class", "geometry"])
gr = []
for r in LU:
    c, s = r.get("class"), r.get("subtype")
    tag = ({"leisure": "park"} if c == "park" or s == "park" else
           {"leisure": "garden"} if c == "garden" else
           {"landuse": "cemetery"} if c in ("cemetery", "grave_yard") else None)
    if not tag: continue
    if name(r): tag["name"] = name(r)
    el = areas(wkb.loads(r["geometry"]), tag)
    if el: gr.append(el)
for r in LAND:
    if r.get("class") in ("wood", "forest") or r.get("subtype") == "forest":
        el = areas(wkb.loads(r["geometry"]), {"natural": "wood"})
        if el: gr.append(el)
dump("extra_green.json", gr)

tr = []
for r in LAND:
    g = wkb.loads(r["geometry"])
    if r.get("class") == "tree" and isinstance(g, Point):
        tr.append({"type": "node", "id": nid(), "lat": g.y, "lon": g.x, "tags": {"natural": "tree"}})
    elif r.get("class") == "tree_row":
        for ln in ([g] if isinstance(g, LineString) else list(getattr(g, "geoms", []))):
            tr.append({"type": "way", "id": nid(), "tags": {"natural": "tree_row"}, "geometry": ll(ln.coords)})
dump("extra_trees.json", tr)

na = []
for r in read("base", "infrastructure", ["id", "names", "class", "source_tags", "geometry"]):
    t = stags(r)
    drink = (r.get("class") == "drinking_water" or t.get("amenity") == "drinking_water" or
             t.get("man_made") == "drinking_fountain" or
             (t.get("amenity") == "fountain" and t.get("drinking_water") == "yes"))
    if not drink: continue
    c = centre(wkb.loads(r["geometry"]))
    na.append({"type": "node", "id": nid(), "lat": c["lat"], "lon": c["lon"], "tags": t})
dump("extra_nasoni.json", na)

# --- named places ----------------------------------------------------------------
# Translated into the OSM tags places.py classifies by. Overture's places are
# mostly business listings, so only landmark categories, and only those it is
# confident of; neighbourhoods come from divisions, parks and plazas from land
# use, and the named buildings (the Guardian, the Renaissance Center) from the
# buildings themselves.
def place_tags(tax):
    h = set((tax or {}).get("hierarchy") or []); p = (tax or {}).get("primary")
    if h & {"museum", "art_museum", "history_museum", "science_museum"}: return {"tourism": "museum"}
    if p == "art_gallery": return {"tourism": "gallery"}
    if p in ("stadium_arena", "baseball_stadium", "football_stadium", "hockey_arena",
             "soccer_stadium"): return {"leisure": "stadium"}
    if p == "park": return {"leisure": "park"}
    if p == "public_plaza": return {"place": "square"}
    if p in ("theatre_venue", "opera_and_ballet"): return {"amenity": "theatre"}
    if p == "college_university": return {"amenity": "university"}
    if p == "library": return {"amenity": "library"}
    if p in ("train_station", "bus_station", "light_rail_and_subway_station"): return {"railway": "station"}
    if p in ("monument", "landmark_and_historical_building", "historic_site"): return {"historic": "monument"}
    if "place_of_worship" in (p or ""): return {"amenity": "place_of_worship"}
    return None
po = []
for r in read("places", "place", ["id", "names", "taxonomy", "confidence", "geometry", "operating_status"]):
    if (r.get("confidence") or 0) < 0.9 or r.get("operating_status") in ("permanently_closed",): continue
    t = place_tags(r.get("taxonomy"))
    if not t or not name(r): continue
    t["name"] = name(r)
    po.append({"type": "node", "id": nid(), "tags": t, **centre(wkb.loads(r["geometry"]))})
for r in read("divisions", "division", ["id", "names", "subtype", "wikidata", "geometry"]):
    if r.get("subtype") not in ("neighborhood", "macrohood", "microhood") or not name(r): continue
    t = {"place": "neighbourhood", "name": name(r)}
    if r.get("wikidata"): t["wikidata"] = r["wikidata"]
    po.append({"type": "node", "id": nid(), "tags": t, **centre(wkb.loads(r["geometry"]))})
for r in LU:
    if not name(r): continue
    t = ({"leisure": "park"} if r.get("subtype") == "park" or r.get("class") == "park" else
         {"highway": "pedestrian", "area": "yes"} if r.get("subtype") == "pedestrian" else None)
    if not t: continue
    t["name"] = name(r)
    if r.get("wikidata"): t["wikidata"] = r["wikidata"]
    po.append({"type": "way", "id": nid(), "tags": t, "center": centre(wkb.loads(r["geometry"]))})
for el in bl:
    t = el["tags"]
    # every named building: in Detroit the building is often the destination
    # (the Guardian, Huntington Place, Hudson's), and the place listings miss it
    if t.get("name"):
        g = el["geometry"] if el["type"] == "way" else el["members"][0]["geometry"]
        c = {"lat": sum(p["lat"] for p in g)/len(g), "lon": sum(p["lon"] for p in g)/len(g)}
        tt = {"name": t["name"], "historic": "building"}
        if t["building"] in ("church", "cathedral"): tt = {"name": t["name"], "amenity": "place_of_worship"}
        po.append({"type": "way", "id": nid(), "tags": tt, "center": c})
dump("extra_poi.json", po)
print("Overture data ready in data/overture/")
