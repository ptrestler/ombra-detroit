"""The city itself, as opposed to the box round it.

A bbox is a rectangle; a city is not. Detroit's box runs south to the river at
the Ambassador Bridge, and a rectangle that does that takes in downtown Windsor
on the far bank - four and a half thousand nodes of Canadian street network
that no walk can reach, shade computed for nobody, and a connectivity figure
that drops from 97 % to 89 % for a reason that has nothing to do with Detroit.

So the map is clipped to the city's boundary: Overture's locality area for
city.BOUNDARY, buffered by BUFFER_DEG so the riverfront's piers and the paths
along the very edge of the land are not shaved off. fetch_overture.py writes
it to data/overture/area.json and drops what falls outside; pack.py drops
addresses outside it, because those come from OSM, whichever SOURCE the rest
of the map comes from. Water is kept whole: the river is drawn, the far shore
is ground.

Point-in-polygon here is plain numpy, so the build needs no shapely.
"""
import json, os
import numpy as np
from paths import DATA

PATH = os.path.join(DATA, "overture", "area.json")
BUFFER_DEG = 0.0012          # ~100 m; Windsor is ~700 m away across the river

def rings():
    """The boundary's rings, already buffered, as lists of (lon, lat); None if
    no boundary has been fetched, in which case nothing is clipped."""
    if not os.path.exists(PATH): return None
    return json.load(open(PATH))["rings"]

def inside(lon, lat, rr=None):
    """Boolean array: which points lie inside the (buffered) boundary. Even-odd
    over every ring, so a hole in the city (an enclave) stays a hole."""
    rr = rings() if rr is None else rr
    lon = np.atleast_1d(np.asarray(lon, float)); lat = np.atleast_1d(np.asarray(lat, float))
    if not rr: return np.ones(lon.shape, bool)
    res = np.zeros(lon.shape, bool)
    for ring in rr:
        r = np.asarray(ring, float); x, y = r[:, 0], r[:, 1]
        j = len(x) - 1
        for i in range(len(x)):
            res ^= ((y[i] > lat) != (y[j] > lat)) & (
                lon < (x[j] - x[i]) * (lat - y[i]) / (y[j] - y[i] + 1e-15) + x[i])
            j = i
    return res
