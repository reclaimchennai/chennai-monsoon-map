#!/bin/bash
# Copy the web app and its data into the maps-site checkout, then rsync it to the server.
# SITE / REMOTE can be overridden; maps.reclaimchennai.city serves maps-site/ as static files.
set -e
cd "$(dirname "$0")/.."
SITE=${SITE:-$HOME/Desktop/projects/maps-site/monsoon}
REMOTE=${REMOTE:-parag@raw:projects/maps-site/monsoon/}
mkdir -p $SITE/data $SITE/kml
cp web/index.html web/app.js $SITE/
cp data/layers/*.geojson data/layers/*.json $SITE/data/
cp data/kml/*.kml $SITE/kml/
[ "$1" = "--no-push" ] || rsync -az --timeout=120 $SITE/ $REMOTE
echo "deployed to $SITE ${1:+(not pushed)}"
