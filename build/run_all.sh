#!/bin/bash
# Rebuild everything after new lists arrive. Run from the repo root.
# The CDMP parse (parse_wards / parse_flood) only needs re-running if the PDF changes.
set -e
PY=.venv/bin/python
python3 build/tractors_csv.py > /dev/null
python3 build/pumps_csv.py > /dev/null
(cd build && ../$PY build_layers.py)
mkdir -p web/kml && (cd build && ../$PY export_kml.py ../web/kml)
SITE=~/Desktop/projects/maps-site/monsoon
cp web/data/* $SITE/data/ && cp web/kml/*.kml $SITE/kml/
echo "copied to $SITE — bump app.js?v= if app.js changed, then: rsync -az $SITE/ parag@raw:projects/maps-site/monsoon/"
