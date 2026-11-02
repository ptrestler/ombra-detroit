# Ombra Detroit - shade map and shade-aware routing for downtown Detroit.
# The city lives in city.py; everything below is city-agnostic.
# Stages are ordered; each depends on the one above. `make` builds everything.
PY := python3

.PHONY: all fetch rasters shade web artifact test heights clean distclean

all: web

## fetch -- OpenStreetMap and elevation data into data/ (cached; safe to re-run)
fetch:
	$(PY) fetch_osm.py
	$(PY) terrain.py

## rasters -- 2 m building/canopy grid, 10 m terrain grid
rasters: build/dsm.npy build/ground.npy
build/dsm.npy: build_dsm.py heights.py buildings.py geo.py city.py
	$(PY) build_dsm.py
build/ground.npy: build/terr.npy ground.py buildings.py heights.py
	$(PY) ground.py
build/terr.npy: terrain.py geo.py city.py
	$(PY) terrain.py

## shade -- the expensive stage: 768 sun positions x every street segment
shade: build/frames.npy
build/frames.npy: build/dsm.npy build/ground.npy shade.py solar.py streets.py geo.py city.py
	$(PY) shade.py

## web -- routing graph, destination list, payload, the standalone build
web: dist/ombra-detroit.html
build/data.b64: build/frames.npy graph.py places.py pack.py city.py
	$(PY) graph.py
	$(PY) places.py
	$(PY) pack.py
dist/ombra-detroit.html: build/data.b64 web/template.html build_standalone.py city.py
	$(PY) build_standalone.py

## artifact -- template + payload only; the platform supplies the document shell
artifact: build/artifact.html
build/artifact.html: build/data.b64 web/template.html build_artifact.py city.py
	$(PY) build_artifact.py

test:
	$(PY) tests/validate.py
	node tests/smoke.mjs

## heights -- OSM height coverage, and every estimate scored against the tags;
## prints the tables heights.py and CLAUDE.md quote. Reads data/, not build/.
heights:
	$(PY) measure_heights.py

clean:                      ## derived files only; keeps the downloaded data
	rm -rf build dist
distclean: clean            ## also drops the cached downloads (slow to refetch)
	rm -rf data/osm/tiles data/osm/extra_*.json data/dem
