# Rebuild everything from the source files. `make` = fetch, extract, place, export.
PY ?= python3
ED ?= 2026

all: sources extract layers kml

sources:                 ## PDFs + SWD network (release assets), TNGIS layers
	pipeline/fetch_sources.sh
	[ -f raw/tngis/gcc_roads.geojson.gz ] || $(PY) pipeline/fetch_tngis.py

osm:                     ## optional: re-cut OpenStreetMap (raw/osm is committed)
	pipeline/fetch_osm.sh

extract:                 ## every table of the CDMP -> data/cdmp/$(ED)/
	$(PY) pipeline/cdmp_extract.py raw/cdmp/cdmp_$(ED).pdf --out data/cdmp/$(ED)

pumps:                   ## pump-list screenshots -> CSV (needs tesseract + opencv)
	$(PY) pipeline/ocr_tables.py raw/pump_lists/*
	$(PY) pipeline/tractor_list.py
	$(PY) pipeline/diesel_list.py
	$(PY) pipeline/ocr_phone_check.py

layers:                  ## place everything on the map -> data/layers/
	$(PY) pipeline/build_layers.py --cdmp data/cdmp/$(ED)

kml:                     ## Google My Maps files -> data/kml/
	$(PY) pipeline/export_kml.py

deploy:                  ## copy web app + data to the maps-site checkout and push it to the server
	web/deploy.sh

.PHONY: all sources osm extract pumps layers kml deploy
