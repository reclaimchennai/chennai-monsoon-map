"""Base geography: GCC 200 wards (zone I-XV) and named OSM streets around Chennai.
-> data/wards.geojson, build/streets.pkl"""
import json, pickle
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
ZR = [(1, 14), (15, 22), (23, 33), (34, 48), (49, 63), (64, 78), (79, 93), (94, 108), (109, 126),
      (127, 142), (143, 155), (156, 167), (168, 180), (181, 191), (192, 200)]
ZN = ['Thiruvottiyur', 'Manali', 'Madhavaram', 'Tondiarpet', 'Royapuram', 'Thiru-Vi-Ka Nagar', 'Ambattur',
      'Anna Nagar', 'Teynampet', 'Kodambakkam', 'Valasaravakkam', 'Alandur', 'Adyar', 'Perungudi', 'Sholinganallur']
zone_of = lambda w: next(i + 1 for i, (a, b) in enumerate(ZR) if a <= w <= b)
src = json.load(open('/Users/admin/Desktop/projects/chennai-eo/zones/src/gcc_wards_latest.geojson'))
feats = []
for f in src['features']:
    w = int(f['properties']['Name'].strip())
    g = shape(f['geometry']).buffer(0)
    g2 = shape(f['geometry'])
    if g2.has_z:
        from shapely import force_2d; g = force_2d(g).buffer(0)
    z = zone_of(w)
    feats.append({'type': 'Feature', 'properties': {'ward': w, 'zone': z, 'zone_name': ZN[z - 1]},
                  'geometry': mapping(g.simplify(0.00003))})
feats.sort(key=lambda f: f['properties']['ward'])
json.dump({'type': 'FeatureCollection', 'features': feats}, open('data/wards.geojson', 'w'), separators=(',', ':'))
print('wards', len(feats))
# streets
streets = []
with open('/Users/admin/Desktop/projects/transitday/raw/cma_roads.geojsons') as fh:
    for line in fh:
        line = line.strip().lstrip('\x1e')
        if not line: continue
        f = json.loads(line); p = f['properties']
        if not p.get('name'): continue
        c = f['geometry']['coordinates']
        if not (80.12 < c[0][0] < 80.36 and 12.80 < c[0][1] < 13.26): continue
        streets.append((p['name'], p.get('highway'), shape(f['geometry'])))
pickle.dump(streets, open('build/streets.pkl', 'wb'))
print('named street segments', len(streets), 'unique names', len({s[0] for s in streets}))
