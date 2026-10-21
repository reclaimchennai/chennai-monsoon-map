"""Assemble every source into map layers for the monsoon dashboard.

Inputs : data/tractor_pumps.csv, data/diesel_pumps.csv, data/inundation_rows.json,
         build/zones/zone_NN.json (CDMP zone appendices), data/ward_contacts.json, raw/swd/network.json
Outputs: web/data/*.geojson + web/data/wards_info.json + build/unmapped.csv
"""
import csv, json, re, os, math, glob
from collections import defaultdict
from geocode import Geocoder, norm, compatible

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f'{ROOT}/web/data'
os.makedirs(OUT, exist_ok=True)
G = Geocoder()
unmapped = []
ZN = ['Thiruvottiyur', 'Manali', 'Madhavaram', 'Tondiarpet', 'Royapuram', 'Thiru-Vi-Ka Nagar', 'Ambattur',
      'Anna Nagar', 'Teynampet', 'Kodambakkam', 'Valasaravakkam', 'Alandur', 'Adyar', 'Perungudi', 'Sholinganallur']
ZR = [(1, 14), (15, 22), (23, 33), (34, 48), (49, 63), (64, 78), (79, 93), (94, 108), (109, 126),
      (127, 142), (143, 155), (156, 167), (168, 180), (181, 191), (192, 200)]
zone_of = lambda w: next((i + 1 for i, (a, b) in enumerate(ZR) if a <= w <= b), None)


def phone(s, label=''):
    """'9445190301' / '044-25382357' / '04177-246594' -> {n: dialable digits, d: display, label, bad}"""
    s = str(s or '').strip()
    d = re.sub(r'\D', '', s)
    if len(d) == 10 and d[0] in '6789':
        return {'n': '+91' + d, 'd': d[:5] + ' ' + d[5:], 'label': label}
    if d.startswith('0') and 10 <= len(d) <= 11:
        std = re.match(r'0\d{2,4}', s.replace(' ', '')).group(0) if re.match(r'0\d{2,4}', s.replace(' ', '')) else d[:3]
        return {'n': '+91' + d[1:], 'd': std + ' ' + d[len(std):], 'label': label}
    if len(d) == 8 and d[0] == '2':
        return {'n': '+9144' + d, 'd': '044 ' + d, 'label': label}
    return {'n': None, 'd': s, 'label': label, 'bad': True} if s and s != '-' else None


def phones(lst, label=''):
    out = []
    for p in lst or []:
        q = phone(p if isinstance(p, str) else p.get('n'), label if isinstance(p, str) else (p.get('label') or label))
        if q: out.append(q)
    return out


def fc(feats):
    return {'type': 'FeatureCollection', 'features': feats}


def save(name, feats):
    json.dump(fc(feats), open(f'{OUT}/{name}.geojson', 'w'), separators=(',', ':'), ensure_ascii=False)
    prec = defaultdict(int)
    for f in feats: prec[f['properties'].get('prec')] += 1
    print(f'{name:14s} {len(feats):5d}  ' + ' '.join(f'{k}:{v}' for k, v in sorted(prec.items(), key=str)))


def point(g, props):
    return {'type': 'Feature', 'properties': props, 'geometry': {'type': 'Point', 'coordinates': [g['lon'], g['lat']]}}


def locate(text, ward=None, zone=None, kind='any', layer='', alt=()):
    w = ward if isinstance(ward, int) and 1 <= ward <= 200 else None
    z = zone or (zone_of(w) if w else None)
    g = G.geocode(text, w, z, kind) if text else None
    for a in alt:                                   # fall back to other texts (first street of a list...)
        if g and g['precision'] in ('street', 'place'): break
        if not a: continue
        g2 = G.geocode(a, w, z, kind)
        if g2 and g2['precision'] in ('street', 'place'): g = g2
    if g and g['precision'] in ('street', 'place') and g.get('matched') and not compatible(norm(text), norm(g['matched'].replace(' (area)', ''))):
        g['precision'] = 'area'                     # matched only the locality / a fallback text
    if g is None or g['precision'] not in ('street', 'place', 'area'):
        unmapped.append({'layer': layer, 'text': text, 'ward': ward, 'zone': z, 'fallback': g['precision'] if g else None})
    return g


def spread(feats):
    """Several items at one spot (e.g. 5 tractors at a division office): fan them out ~12 m apart."""
    groups = defaultdict(list)
    for f in feats:
        c = f['geometry']['coordinates']; groups[(round(c[0], 5), round(c[1], 5))].append(f)
    for (x, y), fs in groups.items():
        if len(fs) < 2: continue
        r = 0.00011 * (1 + len(fs) / 8)
        for i, f in enumerate(fs):
            a = 2 * math.pi * i / len(fs)
            f['geometry']['coordinates'] = [round(x + r * math.cos(a) / math.cos(math.radians(y)), 6), round(y + r * math.sin(a), 6)]


OFFICE = re.compile(r'(division|divistion|zonal)\s+office|^transit$', re.I)

# ---------------------------------------------------------------- tractor pumps
feats = []
for r in csv.DictReader(open(f'{ROOT}/data/tractor_pumps.csv')):
    div, loc = int(r['div']), r['location'].strip()
    if OFFICE.search(loc):
        g = G.geocode('', div, int(r['zone'])); g['precision'] = 'office'
    else:
        g = locate(loc, div, int(r['zone']), layer='tractor')
    feats.append(point(g, {'id': f"T{r['sno']}", 'sno': int(r['sno']), 'tractor': r['tractor'], 'driver': r['driver'].title(),
                           'phones': phones(r['phones'].split(' / ')), 'loc': loc.title() if loc.isupper() else loc,
                           'zone': int(r['zone']), 'ward': div, 'prec': g['precision'], 'match': g.get('matched'),
                           'note': r['note'] or None}))
spread(feats); save('tractors', feats)

# ---------------------------------------------------------------- diesel / RP pumps
feats = []
for r in csv.DictReader(open(f'{ROOT}/data/diesel_pumps.csv')):
    div = int(r['div']); loc = r['location']
    first = re.split(r'\s+(?:to|-)\s+|,', loc)[0]
    g = locate(loc, div, int(r['zone']), layer='pump', alt=(first,))
    feats.append(point(g, {'id': f"P{r['sno']}", 'sno': int(r['sno']), 'pump': r['pump_no'] or None, 'kind': r['kind'],
                           'hp': r['hp'] or None, 'loc': loc.title() if loc.isupper() else loc, 'zone': int(r['zone']),
                           'ward': div, 'placed': r['placed'], 'prec': g['precision'], 'match': g.get('matched'),
                           'note': r['note'] or None}))
spread(feats); save('pumps', feats)

# ---------------------------------------------------------------- zone appendix tables
Z = {}
for f in sorted(glob.glob(f'{ROOT}/build/zones/zone_*.json')):
    d = json.load(open(f)); Z[d['zone']] = d


def ward_int(w):
    if isinstance(w, int): return w
    m = re.match(r'^\s*(\d{1,3})\b', str(w or ''))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- flood-prone streets (merged)
CLS_RANK = {'very_high': 4, 'high': 3, 'medium': 2, 'low': 1, None: 0}
spots = {}


def spot(zone, ward, name):
    key = (ward, norm(name))
    if key not in spots:
        spots[key] = {'name': name, 'zone': zone, 'ward': ward, 'years': set(), 'cls': None, 'rain': set(),
                      'depth': None, 'drain': None, 'pump': None, 'disposal': None, 'reason': None, 'src': set(), 'pages': set()}
    return spots[key]


for r in json.load(open(f'{ROOT}/data/inundation_rows.json')):
    w = ward_int(r['ward'])
    s = spot(r['zone'], w, r['location'])
    if r['year']: s['years'].add(r['year'])
    if CLS_RANK[r['class']] > CLS_RANK[s['cls']]: s['cls'] = r['class']
    s['src'].add('inundation'); s['pages'].add(r['page'])
for z, d in Z.items():
    for r in d['inundation_streets']:
        if not r.get('street'): continue
        s = spot(z, ward_int(r['ward']), r['street'])
        s['rain'].add('heavy'); s['src'].add('heavy_rain'); s['pages'].add(r.get('page'))
        for k, kk in [('max_depth', 'depth'), ('days_to_drain', 'drain'), ('disposal_point', 'disposal'), ('reason', 'reason')]:
            if r.get(k) and not s[kk]: s[kk] = r[k]
        if r.get('pump'): s['pump'] = r['pump'] + (f" at {r['pump_location']}" if r.get('pump_location') else '')
    for r in d['water_stagnation']:
        if not r.get('street'): continue
        s = spot(z, ward_int(r['ward']), r['street'])
        s['rain'].add(r.get('rain') or 'recorded'); s['src'].add('stagnation'); s['pages'].add(r.get('page'))
feats = []
for (w, _), s in spots.items():
    g = locate(s['name'], w, s['zone'], layer='flood')
    if g is None: continue
    yrs = sorted(s['years'])
    props = {'name': s['name'], 'zone': s['zone'], 'ward': w, 'years': yrs, 'cls': s['cls'],
             'rain': sorted(s['rain']), 'depth': s['depth'], 'drain': s['drain'], 'pump': s['pump'],
             'disposal': s['disposal'], 'reason': s['reason'], 'prec': g['precision'], 'match': g.get('matched'),
             'pages': sorted(p for p in s['pages'] if p),
             # severity 0-5 for styling: depth class, else 'heavy rain' table = 2, mild-rain stagnation = 1
             'sev': CLS_RANK[s['cls']] + (1 if len(yrs) >= 3 else 0) if s['cls'] else (2 if 'heavy' in s['rain'] else 1)}
    feats.append(point(g, props))
    if g.get('line'):
        feats.append({'type': 'Feature', 'properties': {**props, 'line': 1}, 'geometry': g['line']})
save('flood_spots', feats)

# ---------------------------------------------------------------- relief centres
feats = []
for z, d in Z.items():
    for r in d['relief_centres']:
        w = ward_int(r['ward'])
        g = locate(r['name'], w, z, kind='facility', layer='relief', alt=((r.get('streets_to_shift') or '').split(',')[0],))
        if g is None: continue
        contacts = [{'role': c.get('designation'), 'phones': phones(c.get('phones'))} for c in r.get('contacts') or []]
        feats.append(point(g, {'name': r['name'], 'zone': z, 'ward': w, 'cap': r.get('capacity'),
                               'shift': r.get('streets_to_shift'), 'cook': r.get('cooking'), 'water': r.get('drinking_water'),
                               'toilet': r.get('toilets'), 'contacts': contacts, 'prec': g['precision'], 'match': g.get('matched'),
                               'page': r.get('page')}))
spread(feats); save('relief', feats)

# ---------------------------------------------------------------- evacuation / water-entered-houses streets
feats = []
for z, d in Z.items():
    for r in d['evacuation_streets']:
        w = ward_int(r['ward']); txt = r.get('streets') or r.get('area') or ''
        g = locate(txt, w, z, layer='evac', alt=(txt.split(',')[0], r.get('area')))
        if g is None: continue
        feats.append(point(g, {'name': txt, 'area': r.get('area'), 'zone': z, 'ward': w, 'kind': 'evacuate',
                               'persons': r.get('persons'), 'year': r.get('year'), 'centre': r.get('relief_centre'),
                               'prec': g['precision'], 'match': g.get('matched'), 'page': r.get('page')}))
    for r in d['water_entered_houses']:
        w = ward_int(r['ward']); txt = r.get('street') or ''
        g = locate(txt, w, z, layer='houses', alt=(txt.split(',')[0],))
        if g is None: continue
        feats.append(point(g, {'name': txt, 'zone': z, 'ward': w, 'kind': 'houses', 'prec': g['precision'],
                               'match': g.get('matched'), 'page': r.get('page')}))
spread(feats); save('evacuation', feats)

# ---------------------------------------------------------------- subways (zone tables + city list §8.5)
CITY_SUBWAYS = ['Ganesapuram subway', 'Reserve Bank Subway', 'Stanley Nagar Subway', 'Stanley Nagar Subway 2',
                'Perambur Subway', 'Gengu Reddy Road Subway', 'Villivakkam Subway', 'Nungambakkam Subway',
                'Harrington Road Subway', 'Dheeran Sivalingam Subway', 'Madley Subway', 'Aranganathan Subway',
                'Saidapet Bazaar Road Subway', 'Jones Road Subway', 'Monegar Choultry Road Subway',
                'Rangarajapuram Subway', 'St. Thomas Mount Subway', 'Thillai Ganga Nagar Subway',
                'Palavanthangal Subway', 'Meenambakkam Subway', 'Vyasarpadi Subway', 'Kathivakkam High Road Subway']
feats, seen = [], []
for z, d in Z.items():
    for r in d['subways']:
        w = ward_int(r['ward'])
        g = locate(r['name'], w, z, kind='facility', layer='subway')
        if g is None: continue
        feats.append(point(g, {'name': r['name'], 'zone': z, 'ward': w, 'len': r.get('length_m'),
                               'disposal': r.get('disposal_point'), 'pumps': r.get('pumps'), 'prec': g['precision'],
                               'match': g.get('matched'), 'page': r.get('page')}))
for n in CITY_SUBWAYS:
    g = G.geocode(n, None, None, 'facility')
    if not g or g['precision'] not in ('street', 'place'):
        unmapped.append({'layer': 'subway-city', 'text': n}); continue
    if any(abs(f['geometry']['coordinates'][0] - g['lon']) < 0.003 and abs(f['geometry']['coordinates'][1] - g['lat']) < 0.003 for f in feats):
        continue
    feats.append(point(g, {'name': n, 'zone': None, 'ward': None, 'prec': g['precision'], 'match': g.get('matched'), 'page': 150}))
save('subways', feats)

# ---------------------------------------------------------------- assembly points / parks, NDRF & boats, tree falls
for key, layer, kind in [('parks_assembly', 'assembly', 'facility'), ('ndrf_boats', 'ndrf', 'any'), ('tree_fall', 'trees', 'any')]:
    feats = []
    for z, d in Z.items():
        for r in d[key]:
            w = ward_int(r.get('ward'))
            txt = r.get('name') or r.get('location') or r.get('street') or ''
            g = locate(txt, w, z, kind=kind, layer=layer, alt=(r.get('location'), (r.get('street') or '').split(',')[0]))
            if g is None: continue
            p = {'name': txt, 'zone': z, 'ward': w, 'prec': g['precision'], 'match': g.get('matched')}
            if key == 'parks_assembly': p['loc'] = r.get('location')
            if key == 'ndrf_boats': p.update(kind=r.get('kind'), details=r.get('details'), loc=r.get('location'))
            feats.append(point(g, p))
    spread(feats); save(layer, feats)

# ---------------------------------------------------------------- storm water drains (reclaimchennai SWD extraction)
net = json.load(open(f'{ROOT}/raw/swd/network.json'))
feats = []
for c in net['conduits']:
    if c.get('x'): continue          # keep only drains traced off the GCC sheets, not inferred links
    feats.append({'type': 'Feature', 'properties': {'w': c.get('wd'), 'ty': c.get('ty')},
                  'geometry': {'type': 'LineString', 'coordinates': [[round(x, 5), round(y, 5)] for x, y in c['g']]}})
outs = [{'type': 'Feature', 'properties': {'id': n['id']}, 'geometry': {'type': 'Point', 'coordinates': [round(n['lon'], 5), round(n['lat'], 5)]}}
        for n in net['nodes'] if n.get('out')]
save('swd', feats + outs)

# ---------------------------------------------------------------- ward label points
from shapely.geometry import shape as _shape
labels = []
for f in json.load(open(f'{ROOT}/data/wards.geojson'))['features']:
    g = _shape(f['geometry'])
    try:
        from shapely.ops import polylabel
        p = polylabel(max(g.geoms, key=lambda x: x.area) if g.geom_type == 'MultiPolygon' else g, 0.0002)
    except Exception:
        p = g.representative_point()
    labels.append({'type': 'Feature', 'properties': f['properties'], 'geometry': {'type': 'Point', 'coordinates': [round(p.x, 5), round(p.y, 5)]}})
json.dump(fc(labels), open(f'{OUT}/ward_labels.geojson', 'w'), separators=(',', ':'))
import shutil; shutil.copy(f'{ROOT}/data/wards.geojson', f'{OUT}/wards.geojson')

# ---------------------------------------------------------------- ward info (contacts) for the ward panel
wc = json.load(open(f'{ROOT}/data/ward_contacts.json'))
info = {'wards': {}, 'zones': {}}
for w in range(1, 201):
    v = wc.get(str(w))
    z = zone_of(w)
    rec = {'zone': z, 'councillor': phones(v['councillor'], 'Councillor') if v else phones(['9445467%03d' % w], 'Councillor'),
           'councillor_name': v.get('councillor_name') if v else None, 'page': v['page'] if v else None,
           'contacts': [{'dept': c['dept'], 'role': c['designation'], 'phones': phones(c['phones'])} for c in (v['contacts'] if v else [])]}
    info['wards'][w] = rec
for z, d in Z.items():
    info['zones'][z] = {'name': ZN[z - 1], 'officials': [{'role': o.get('designation'), 'name': o.get('name'), 'wards': o.get('wards'),
                                                          'cat': o.get('category'), 'phones': phones(o.get('phones'))} for o in d['officials']]}
json.dump(info, open(f'{OUT}/wards_info.json', 'w'), separators=(',', ':'), ensure_ascii=False)

with open(f'{ROOT}/build/unmapped.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, ['layer', 'text', 'ward', 'zone', 'fallback']); w.writeheader(); w.writerows(unmapped)
print('placed only approximately (ward/zone point):', len(unmapped))
