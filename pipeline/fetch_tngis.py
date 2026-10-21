#!/usr/bin/env python3
"""Download the TNGIS layers used to place CDMP locations, clipped to Greater Chennai.

    python pipeline/fetch_tngis.py                 # all layers -> raw/tngis/*.geojson.gz
    python pipeline/fetch_tngis.py --only gcc_parks

Source: the public GeoServer WFS behind https://tngis.tn.gov.in (no login).
Each layer is paged with a stable sortBy so a download is complete and repeatable.
"""
import argparse, gzip, json, os, sys, time, urllib.parse, urllib.request

WFS = 'https://tngis.tn.gov.in/tngismaps/wfs'
BBOX = (80.12, 12.80, 80.36, 13.26)          # lon/lat: GCC plus a margin
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# name -> (typeName, properties to keep, why)
LAYERS = {
    'gcc_ward_boundary': ('generic_viewer:gcc_ward_boundary', ['ward', 'zone', 'zone_label', 'region'], 'the 200 wards (current delimitation)'),
    'gcc_zone_boundary': ('generic_viewer:gcc_zone_boundary', None, '15 zones'),
    'gcc_ward_office': ('generic_viewer:gcc_ward_office', ['ward_no', 'zone_no', 'street_name', 'area_name'], 'ward (division) offices'),
    'gcc_zone_office': ('generic_viewer:gcc_zone_office', ['ward_no', 'zone_no', 'street_name', 'area_name'], 'zone offices'),
    'gcc_office_buildings': ('Pm_Gati_Sakthi:gcc_office_buildings', ['ward_no', 'zone_no', 'streetname', 'cat'], 'GCC ward/zone office buildings'),
    'gcc_parks': ('generic_viewer:gcc_parks', ['ward_no', 'zone_no', 'street_name', 'area_name', 'locality_name'], 'GCC parks (points)'),
    'gcc_others': ('Pm_Gati_Sakthi:gcc_others', ['ward_no', 'zone_no', 'streetname', 'category'], 'GCC parks, playgrounds, schools, UPHCs (polygons)'),
    'gcc_schools': ('generic_viewer:gcc_schools', ['ward_no', 'zone_no', 'street_name', 'area_name'], 'GCC schools (points)'),
    'gcc_community_hall': ('Pm_Gati_Sakthi:gcc_community_hall', ['ward_no', 'zone_no', 'address', 'road_name', 'category'], 'GCC community halls'),
    'schools': ('generic_viewer:schools', ['name', 'managing_department', 'category', 'block', 'habitation'], 'every school, named (School Education Dept)'),
    'police_poi': ('generic_viewer:police_point_of_interest', ['name', 'poi_type', 'place_1'], 'named landmarks from police GIS'),
    'health_facilities': ('generic_viewer:all_health_facilities', ['facility_name', 'facility_type', 'address'], 'hospitals, UPHCs'),
    'police_stations': ('generic_viewer:police_stations', ['name'], 'police stations'),
    'evacuation_shelters': ('generic_viewer:multipurpose_evacuation_shelter', ['location', 'buildings', 'address'], 'TNSDMA multipurpose shelters'),
    'gcc_roads': ('generic_viewer:gcc_road_of_width', ['road_name', 'locality', 'area_name', 'ward_no', 'zone_no'], 'every GCC street as a polygon, with its GCC name and ward'),
}


def get(params):
    url = WFS + '?' + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.load(r)
        except Exception as e:
            print(f'    retry {attempt + 1}: {e}', file=sys.stderr); time.sleep(5 * (attempt + 1))
    raise SystemExit(f'failed: {url}')


def round_coords(c, nd=6):
    return [round(c[0], nd), round(c[1], nd)] if isinstance(c[0], (int, float)) else [round_coords(x, nd) for x in c]


def fetch(name, type_name, keep):
    feats, start, page = [], 0, 5000
    while True:
        d = get({'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature', 'typeNames': type_name, 'outputFormat': 'application/json',
                 'srsName': 'EPSG:4326', 'bbox': f'{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]},urn:ogc:def:crs:EPSG::4326',
                 'count': page, 'startIndex': start, 'sortBy': 'object_id' if name not in ('gcc_ward_boundary',) else 'ward'})
        fs = d.get('features', [])
        for f in fs:
            if f.get('geometry'):
                f['geometry']['coordinates'] = round_coords(f['geometry']['coordinates'])
            p = f.get('properties') or {}
            f['properties'] = {k: p.get(k) for k in keep} if keep else p
            f.pop('bbox', None); f.pop('geometry_name', None)
        feats += fs
        print(f'  {name}: {len(feats)}', file=sys.stderr)
        if len(fs) < page:
            break
        start += page
    os.makedirs(f'{ROOT}/raw/tngis', exist_ok=True)
    with gzip.open(f'{ROOT}/raw/tngis/{name}.geojson.gz', 'wt') as f:
        json.dump({'type': 'FeatureCollection', 'source': f'TNGIS WFS {type_name}', 'bbox': BBOX, 'features': feats}, f, separators=(',', ':'))
    return len(feats)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', nargs='*')
    a = ap.parse_args()
    for name, (tn, keep, why) in LAYERS.items():
        if a.only and name not in a.only:
            continue
        print(f'{name}: {fetch(name, tn, keep)} features  ({why})')
