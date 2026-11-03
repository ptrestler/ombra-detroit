"""Where everything lives. Every script resolves paths through here, so the
pipeline runs the same from any working directory."""
import os
ROOT  = os.path.dirname(os.path.abspath(__file__))
DATA  = os.path.join(ROOT, "data")
import city
# the map's vector data: data/osm/ or data/overture/, same files either way.
# fetch_osm.py always writes data/osm/ (RAWOSM), whichever the build reads.
RAWOSM= os.path.join(DATA, "osm")
OSMD  = os.path.join(DATA, "overture" if city.SOURCE == "overture" else "osm")
DEMD  = os.path.join(DATA, "dem")
BUILDD= os.path.join(ROOT, "build")
WEBD  = os.path.join(ROOT, "web")
DISTD = os.path.join(ROOT, "dist")
for _d in (OSMD, os.path.join(OSMD,"tiles"), RAWOSM, os.path.join(RAWOSM,"tiles"), DEMD, BUILDD, DISTD):
    os.makedirs(_d, exist_ok=True)
osm   = lambda n: os.path.join(OSMD, n)
dem   = lambda n: os.path.join(DEMD, n)
build = lambda n: os.path.join(BUILDD, n)
web   = lambda n: os.path.join(WEBD, n)
dist  = lambda n: os.path.join(DISTD, n)
