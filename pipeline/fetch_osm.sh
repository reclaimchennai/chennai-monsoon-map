#!/bin/bash
# Named OpenStreetMap streets, places and polygons over Chennai -> raw/osm/*.geojson.gz
# Needs GDAL (ogr2ogr) built with the OSM driver. Downloads the Geofabrik southern-zone extract (~1 GB).
set -e
cd "$(dirname "$0")/.."
PBF=${PBF:-raw/osm/southern-zone-latest.osm.pbf}
[ -f "$PBF" ] || curl -L -o "$PBF" https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf
BB="80.12 12.80 80.36 13.26"
TMP=$(mktemp -d); export CPL_TMPDIR=$TMP
ogr2ogr -f GeoJSON $TMP/lines.geojson "$PBF" lines -spat $BB -where "name IS NOT NULL AND highway IS NOT NULL" -select name,highway
ogr2ogr -f GeoJSON $TMP/points.geojson "$PBF" points -spat $BB -where "name IS NOT NULL"
ogr2ogr -f GPKG $TMP/mp.gpkg "$PBF" multipolygons -spat $BB -where "name IS NOT NULL" -select name,amenity,leisure,landuse,natural,other_tags
ogr2ogr -f GeoJSON $TMP/polys.geojson $TMP/mp.gpkg -dialect SQLite \
  -sql "SELECT name, amenity, leisure, landuse, natural, ST_PointOnSurface(geom) AS geometry FROM multipolygons"
for f in lines points polys; do gzip -c $TMP/$f.geojson > raw/osm/$f.geojson.gz; done
rm -rf $TMP
ls -la raw/osm
