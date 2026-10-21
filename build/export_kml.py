"""Web layers -> one KML per layer for Google My Maps (import limit: 2,000 features per layer, 10 layers per map).
Phone numbers go both into the description (tap-to-call in Google Maps) and ExtendedData (My Maps table columns)."""
import json, os, sys
from xml.sax.saxutils import escape as x

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = f'{ROOT}/web/data'
OUT = sys.argv[1] if len(sys.argv) > 1 else f'{ROOT}/web/kml'
os.makedirs(OUT, exist_ok=True)
ZN = ['Thiruvottiyur', 'Manali', 'Madhavaram', 'Tondiarpet', 'Royapuram', 'Thiru-Vi-Ka Nagar', 'Ambattur', 'Anna Nagar',
      'Teynampet', 'Kodambakkam', 'Valasaravakkam', 'Alandur', 'Adyar', 'Perungudi', 'Sholinganallur']
APPROX = {'ward': 'Approximate: only the ward is known', 'office': 'At the division office (marker at ward)', 'zone': 'Approximate (zone)',
          'area': 'Placed at the locality'}


def kcolor(hexc, a='ff'):
    h = hexc.lstrip('#'); return a + h[4:6] + h[2:4] + h[0:2]


def coords(c):
    return ' '.join(f'{p[0]:.6f},{p[1]:.6f}' for p in c)


def geom(g):
    t = g['type']
    if t == 'Point':
        return f"<Point><coordinates>{g['coordinates'][0]:.6f},{g['coordinates'][1]:.6f}</coordinates></Point>"
    if t == 'LineString':
        return f"<LineString><tessellate>1</tessellate><coordinates>{coords(g['coordinates'])}</coordinates></LineString>"
    if t == 'MultiLineString':
        return '<MultiGeometry>' + ''.join(geom({'type': 'LineString', 'coordinates': c}) for c in g['coordinates']) + '</MultiGeometry>'
    if t == 'Polygon':
        rings = g['coordinates']
        s = f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(rings[0])}</coordinates></LinearRing></outerBoundaryIs>"
        s += ''.join(f"<innerBoundaryIs><LinearRing><coordinates>{coords(r)}</coordinates></LinearRing></innerBoundaryIs>" for r in rings[1:])
        return s + '</Polygon>'
    if t == 'MultiPolygon':
        return '<MultiGeometry>' + ''.join(geom({'type': 'Polygon', 'coordinates': c}) for c in g['coordinates']) + '</MultiGeometry>'
    if t == 'GeometryCollection':
        return '<MultiGeometry>' + ''.join(geom(gg) for gg in g['geometries']) + '</MultiGeometry>'
    raise ValueError(t)


def nums(phs):
    return [p['d'] for p in phs or [] if p.get('n')]


def write(name, title, color, feats, icon='placemark_circle'):
    """feats: list of (name, description_lines, fields dict, geometry)"""
    assert len(feats) <= 2000, (name, len(feats))
    out = [f'<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>{x(title)}</name>',
           f'<description>Chennai Monsoon Map, @reclaimchennai: maps.reclaimchennai.city/monsoon</description>',
           f'<Style id="s"><IconStyle><color>{kcolor(color)}</color><scale>1.1</scale><Icon><href>https://maps.google.com/mapfiles/kml/shapes/{icon}.png</href></Icon></IconStyle>'
           f'<LineStyle><color>{kcolor(color)}</color><width>4</width></LineStyle><PolyStyle><color>{kcolor(color, "33")}</color></PolyStyle></Style>']
    for n, desc, fields, g in feats:
        ed = ''.join(f'<Data name="{x(k)}"><value>{x(str(v))}</value></Data>' for k, v in fields.items() if v not in (None, '', []))
        out.append(f'<Placemark><name>{x(n[:120])}</name><description><![CDATA[{"<br>".join(desc)}]]></description><styleUrl>#s</styleUrl>'
                   f'<ExtendedData>{ed}</ExtendedData>{geom(g)}</Placemark>')
    out.append('</Document></kml>')
    open(f'{OUT}/{name}.kml', 'w').write('\n'.join(out))
    print(f'{name:22s} {len(feats):5d}  {os.path.getsize(f"{OUT}/{name}.kml") / 1e6:.2f} MB')


L = lambda n: json.load(open(f'{SRC}/{n}.geojson'))['features']
tel = lambda p: f'<a href="tel:{p["n"]}">{x(p["d"])}</a>' if p.get('n') else f'{x(p["d"])} (as printed)'
zl = lambda z: f'Zone {z} {ZN[z - 1]}' if z else ''

# tractors
F = []
for f in L('tractors'):
    p = f['properties']
    F.append((f"{p['tractor']} · {p['driver']}", [f"<b>Tractor pump</b> — driver {x(p['driver'])}", 'Call: ' + ', '.join(tel(q) for q in p['phones']),
              f"Location: {x(p['loc'])}", f"Division {p['ward']} · {zl(p['zone'])}", APPROX.get(p['prec'], '')],
              {'Driver': p['driver'], 'Mobile': ' / '.join(nums(p['phones'])), 'Tractor': p['tractor'], 'Location': p['loc'],
               'Division': p['ward'], 'Zone': p['zone'], 'Placement': APPROX.get(p['prec'], 'Street / place')}, f['geometry']))
write('tractor_pumps', 'Tractor pumps (call the driver)', '#e8590c', F)

F = []
for f in L('pumps'):
    p = f['properties']
    F.append((f"{p['pump'] or p['kind'] + ' pump'} · {p['loc']}", [f"<b>{'RP' if p['kind'] == 'RP' else 'Diesel'} pump</b> {x(p['pump'] or '')} {x(p['hp'] or '')}",
              f"Location: {x(p['loc'])}", f"Placed: {p['placed']}", f"Division {p['ward']} · {zl(p['zone'])}", APPROX.get(p['prec'], '')],
              {'Pump': p['pump'], 'Location': p['loc'], 'Placed': p['placed'], 'HP': p['hp'], 'Division': p['ward'], 'Zone': p['zone']}, f['geometry']))
write('diesel_pumps', 'Diesel & RP pumps', '#6741d9', F)

# flood-prone: one feature per spot, the street line where we have it
spots = {}
for f in L('flood_spots'):
    p = f['properties']; k = (p['ward'], p['name'])
    if p.get('line') or k not in spots: spots[k] = f
FLOOD, STAG = [], []
CLS = {'very_high': 'above 5 ft', 'high': '3–5 ft', 'medium': '2–3 ft', 'low': 'under 2 ft'}
for f in spots.values():
    p = f['properties']
    yrs = ', '.join(map(str, p['years']))
    F = FLOOD if (p['years'] or 'heavy' in p['rain']) else STAG
    F.append((p['name'], [f"<b>Flood-prone street</b>", f"Flooded: {yrs}" if yrs else 'Water stagnates in ' + ', '.join(p['rain']),
              f"Depth class: {CLS[p['cls']]}" if p.get('cls') else '', f"Pump: {x(p['pump'])}" if p.get('pump') else '',
              f"Ward {p['ward']} · {zl(p['zone'])}", APPROX.get(p['prec'], ''), 'Source: GCC City Disaster Management Plan 2024'],
              {'Ward': p['ward'], 'Zone': p['zone'], 'Years': yrs, 'Depth': CLS.get(p.get('cls')), 'Rain': ', '.join(p['rain']), 'Pump': p.get('pump')}, f['geometry']))
write('flood_prone_streets', 'Streets that flooded 2015–2023 (GCC CDMP 2024)', '#d6336c', FLOOD)
write('water_stagnation_streets', 'Streets where rainwater stagnates (GCC CDMP 2024)', '#f59f00', STAG)

F = []
for f in L('relief'):
    p = f['properties']
    lines = [f"<b>Relief centre</b>{' for ' + str(p['cap']) + ' people' if p.get('cap') else ''}"]
    if p.get('shift'): lines.append('For people from: ' + x(p['shift']))
    for c in p.get('contacts') or []:
        if c.get('phones'): lines.append(f"{x(c['role'] or 'Officer')}: " + ', '.join(tel(q) for q in c['phones']))
    lines += [f"Ward {p['ward']} · {zl(p['zone'])}", APPROX.get(p['prec'], '')]
    F.append((p['name'], lines, {'Capacity': p.get('cap'), 'Ward': p['ward'], 'Zone': p['zone'],
              'Contacts': ' | '.join(f"{c['role']}: {' / '.join(nums(c['phones']))}" for c in p.get('contacts') or [] if nums(c.get('phones')))}, f['geometry']))
write('relief_centres', 'Relief centres', '#2f9e44', F)

for name, title, color, kind in [('subways', 'Subways', '#1c7ed6', 'subways'), ('evacuation_streets', 'Evacuation-prone streets', '#ae3ec9', 'evacuation'),
                                 ('assembly_points', 'Assembly points & parks', '#0ca678', 'assembly'), ('ndrf_boats', 'NDRF teams & rescue boats', '#f08c00', 'ndrf')]:
    F = []
    for f in L(kind):
        p = f['properties']
        d = [f"<b>{title}</b>"] + [f"{k}: {x(str(p[k]))}" for k in ('loc', 'details', 'persons', 'year', 'centre', 'len', 'pumps', 'disposal') if p.get(k)]
        d += [f"Ward {p['ward']} · {zl(p['zone'])}" if p.get('ward') else '', APPROX.get(p['prec'], '')]
        F.append((p.get('name') or p.get('loc') or title, d, {'Ward': p.get('ward'), 'Zone': p.get('zone')}, f['geometry']))
    write(name, title, color, F)

# wards with contacts
info = json.load(open(f'{SRC}/wards_info.json'))
F = []
for f in L('wards'):
    w = f['properties']['ward']; wi = info['wards'][str(w)]
    lines = [f"<b>Ward {w}</b> · {zl(wi['zone'])}", 'Councillor: ' + ', '.join(tel(q) for q in wi['councillor'])]
    for c in wi['contacts']:
        if c['phones']: lines.append(f"{x(c['dept'])} ({x(c['role'])}): " + ', '.join(tel(q) for q in c['phones']))
    lines.append('GCC helpline: <a href="tel:1913">1913</a>')
    fields = {'Zone': wi['zone'], 'Councillor': ' / '.join(nums(wi['councillor']))}
    for c in wi['contacts']:
        if nums(c['phones']) and c['dept'] not in fields: fields[c['dept']] = ' / '.join(nums(c['phones']))
    F.append((f'Ward {w}', lines, fields, f['geometry']))
write('ward_contacts', 'GCC ward contacts', '#495057', F)
