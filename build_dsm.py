import json, math, numpy as np, os
from paths import osm, dem, build, web, dist
from PIL import Image, ImageDraw
from geo import to_xy
from heights import INTERP_RMSE_M, estimate_untagged
from buildings import load as load_buildings, rings   # rings: the wooded areas below

RES=2.0
from city import S, W, N, E
x0,y0 = to_xy(W,S); x1,y1 = to_xy(E,N)
NX=int(math.ceil((x1-x0)/RES)); NY=int(math.ceil((y1-y0)/RES))
def px(x,y): return ((x-x0)/RES,(y1-y)/RES)

blds = load_buildings()
known=[b for b in blds if b["src"] in ("tag","levels")]
unk  =[b for b in blds if b["src"]=="default"]
print("buildings",len(blds),"known",len(known),"untagged",len(unk))
ncad=0                      # no cadastre for this city; kept in grid.json for the page
if known and unk:
    # Untagged buildings are estimated from the tagged ones by the rule in
    # heights.py, which is the same function measure_heights.py scores.
    est = estimate_untagged(known, unk)
    for b, h in zip(unk, est): b["h"] = float(h)
    hh=np.array([b["h"] for b in unk])
    print(f"  estimated {len(unk)}: median {np.median(hh):5.1f}  p10 {np.percentile(hh,10):5.1f}  p90 {np.percentile(hh,90):5.1f}")

# How much of the map rests on the estimates? Set OMBRA_JITTER=<seed> and every
# estimated height moves by its own measured error, so the frames this produces
# can be diffed against the real ones. The claim in the UI's methodology panel
# comes from that diff, and this is the only way to re-derive it. A build with
# no such variable set is untouched.
seed = os.environ.get("OMBRA_JITTER")
if seed:
    rng = np.random.default_rng(int(seed))
    for b in blds:
        if b["src"] == "default": sd = INTERP_RMSE_M
        else:                       continue         # a tag is not an estimate
        b["h"] = float(max(2.0, b["h"] + rng.normal(0.0, sd)))
    print(f"  JITTERED with seed {seed}: this build is a sensitivity probe, not a map")

# Building parts: the pieces towers are drawn in, each with its own height.
# Only the ones that carry a height are any use. A part that starts above the
# ground (min_height: a skybridge, an overhang) still casts shade, so it goes in
# the surface, but it is not "inside a building" for someone standing under it.
from heights import parse_len
parts=[p for p in load_buildings(parts=True) if p["src"]!="default"]
lift=[p for p in parts if (parse_len(p["tags"].get("min_height")) or 0) >= 3.0]
print("building parts with a height",len(parts),"  of them raised off the ground",len(lift))

def raster(items):
    # tallest last, so each cell keeps the highest thing drawn over it: an
    # outline and the tower parts inside it compose as a maximum
    img=Image.new("I;16",(NX,NY),0); d=ImageDraw.Draw(img)
    for b in sorted(items, key=lambda b: b["h"]):
        for r in b["rings"]:
            xs,ys=to_xy([p[0] for p in r],[p[1] for p in r])
            pts=[px(a,c) for a,c in zip(xs,ys)]
            if len(pts)>=3: d.polygon(pts, fill=int(min(b["h"],400)*10))
    return np.array(img,dtype=np.uint16)
_lifted={id(p) for p in lift}
ground_parts=[p for p in parts if id(p) not in _lifted]
bmask=raster(blds+ground_parts)
bsurf=np.maximum(bmask, raster(lift)) if lift else bmask

# ---- canopy layer -------------------------------------------------------
cim=Image.new("I;16",(NX,NY),0); cd=ImageDraw.Draw(cim)
CAN_H=9.0; WOOD_H=11.0
ntree=0; nrow=0; nwood=0
for el in json.load(open(osm("extra_trees.json")))["elements"]:
    if el["type"]=="node":
        x,y=to_xy(el["lon"],el["lat"]); a,b=px(float(x),float(y)); r=4.0/RES
        cd.ellipse([a-r,b-r,a+r,b+r], fill=int(CAN_H*10)); ntree+=1
    elif el["type"]=="way" and el.get("geometry"):
        g=el["geometry"]; xs,ys=to_xy([p["lon"] for p in g],[p["lat"] for p in g])
        pts=[px(a,b) for a,b in zip(xs,ys)]
        if len(pts)>=2:
            cd.line(pts, fill=int(CAN_H*10), width=max(1,int(7.0/RES)), joint="curve")
            for a,b in pts:
                r=3.5/RES; cd.ellipse([a-r,b-r,a+r,b+r], fill=int(CAN_H*10))
            nrow+=1
green=json.load(open(osm("extra_green.json")))["elements"]
for el in green:
    t=el.get("tags",{}) or {}
    if t.get("natural")=="wood" or t.get("landuse")=="forest":
        for r in rings(el):
            xs,ys=to_xy([p[0] for p in r],[p[1] for p in r])
            pts=[px(a,b) for a,b in zip(xs,ys)]
            if len(pts)>=3: cd.polygon(pts, fill=int(WOOD_H*10)); nwood+=1
print("canopy: trees",ntree,"rows",nrow,"wood",nwood)
canopy=np.array(cim,dtype=np.uint16)
dsm=np.maximum(bsurf,canopy)
np.save(build("dsm.npy"),dsm); np.save(build("canopy.npy"),canopy); np.save(build("bmask.npy"),bmask)
json.dump({"x0":float(x0),"y0":float(y0),"x1":float(x1),"y1":float(y1),"NX":NX,"NY":NY,"RES":RES,
           "S":S,"W":W,"N":N,"E":E,"nbld":len(blds),"nknown":len(known),"ncadastre":ncad,
           "ntree":ntree,"nrow":nrow,"nwood":nwood,"nparts":len(parts)},open(build("grid.json"),"w"))
print("dsm max",dsm.max()/10,"coverage",round(float((dsm>0).mean()),3))
