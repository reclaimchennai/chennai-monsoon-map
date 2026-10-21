#!/usr/bin/env python3
"""CDMP datasets + GCC pump lists -> map layers for the web app and KML.

    python pipeline/build_layers.py --cdmp data/cdmp/2026

Inputs : data/cdmp/<edition>/datasets/*.csv   (pipeline/cdmp_extract.py)
         data/pump_lists/tractor_pumps.csv, diesel_pumps.csv   (pipeline/pump_lists.py)
         raw/tngis/*, raw/osm/*                 (gazetteer)
         raw/swd/network.json                   (storm water drains, swd.reclaimchennai.city)
Outputs: data/layers/*.geojson, data/layers/wards_info.json, data/layers/unplaced.json,
         data/review/placements.csv   one row per item: printed text, ward, what it was matched to, source
"""
import argparse, csv, json, math, os, re
from collections import defaultdict

import shapely
from shapely.geometry import mapping

from gazetteer import Gazetteer, norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f'{ROOT}/data/layers'
ZN = ['Thiruvottiyur', 'Manali', 'Madhavaram', 'Tondiarpet', 'Royapuram', 'Thiru-Vi-Ka Nagar', 'Ambattur', 'Anna Nagar', 'Teynampet',
      'Kodambakkam', 'Valasaravakkam', 'Alandur', 'Adyar', 'Perungudi', 'Sholinganallur']
STREETS = ('street', 'locality', 'poi', 'park', 'playground', 'school', 'hall')
FACILITY = ('school', 'hall', 'poi', 'hospital', 'park', 'playground', 'locality')
OPEN = ('playground', 'park', 'poi', 'school', 'locality')

G = None
review, unplaced = [], []


def rows(path):
    return list(csv.DictReader(open(path))) if os.path.exists(path) else []


def ward_int(v):
    try:
        w = int(float(v))
        return w if 1 <= w <= 200 else None
    except (TypeError, ValueError):
        return None


def phone(d, label=''):
    """digits as printed -> {n: tel: target, d: display, label, bad}"""
    d = re.sub(r'\D', '', str(d or ''))
    if len(d) == 10 and d[0] in '6789':
        return {'n': '+91' + d, 'd': d[:5] + ' ' + d[5:], 'label': label}
    if d.startswith('0') and 10 <= len(d) <= 12:
        std = 3 if d.startswith('044') else 5 if len(d) == 11 and not d.startswith('04') else 4
        if d.startswith('044'):
            std = 3
        return {'n': '+91' + d[1:], 'd': d[:std] + ' ' + d[std:], 'label': label}
    return {'n': None, 'd': d, 'label': label, 'bad': True} if d else None


def phones(s, label=''):
    out = []
    for p in re.split(r'[;/,]', str(s or '')):
        q = phone(p, label)
        if q and q['d'] not in [x['d'] for x in out]:
            out.append(q)
    return out


def place(layer, text, ward, zone, kinds, props, alt=()):
    """Match one item; record it for review. Returns a GeoJSON feature or None (-> unplaced list)."""
    r = None
    for t in [text, *alt]:
        if t:
            r = G.match(t, ward, zone, kinds=kinds)
            if r:
                break
    review.append({'layer': layer, 'text': text, 'ward': ward, 'zone': zone, 'matched': r['matched'] if r else '', 'kind': r['kind'] if r else '',
                   'precision': r['precision'] if r else 'unplaced', 'source': r['source'] if r else '', 'score': r['score'] if r else '',
                   'via': (r or {}).get('via') or ''})
    props = {**props, 'ward': ward, 'zone': zone}
    if not r:
        unplaced.append({'layer': layer, **props, 'prec': 'unplaced'})
        return None
    props.update(prec=r['precision'], match=r['matched'], src=r['source'])
    f = {'type': 'Feature', 'properties': props, 'geometry': {'type': 'Point', 'coordinates': [r['lon'], r['lat']]}}
    f['_geom'] = r.get('geom')
    return f


def spread(feats):
    """Several items at one spot (5 tractors at a ward office): fan them out ~12 m apart."""
    groups = defaultdict(list)
    for f in feats:
        c = f['geometry']['coordinates']; groups[(round(c[0], 5), round(c[1], 5))].append(f)
    for (x, y), fs in groups.items():
        if len(fs) < 2:
            continue
        r = 0.00011 * (1 + len(fs) / 8)
        for i, f in enumerate(fs):
            a = 2 * math.pi * i / len(fs)
            f['geometry']['coordinates'] = [round(x + r * math.cos(a) / math.cos(math.radians(y)), 6), round(y + r * math.sin(a), 6)]


def save(name, feats):
    for f in feats:
        f.pop('_geom', None)
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(f'{OUT}/{name}.geojson', 'w'), separators=(',', ':'), ensure_ascii=False)
    pc = defaultdict(int)
    for f in feats:
        pc[f['properties'].get('prec')] += 1
    nu = sum(1 for u in unplaced if u['layer'] == name)
    print(f'{name:14s} placed {len(feats):5d} ({", ".join(f"{k} {v}" for k, v in sorted(pc.items(), key=str))})  unplaced {nu}')


OFFICE = re.compile(r'(division|divistion|zonal|zone)\s+office|^transit$', re.I)


def main():
    global G
    ap = argparse.ArgumentParser()
    ap.add_argument('--cdmp', default=f'{ROOT}/data/cdmp/2026')
    a = ap.parse_args()
    D = lambda n: rows(f'{a.cdmp}/datasets/{n}.csv')
    os.makedirs(OUT, exist_ok=True); os.makedirs(f'{ROOT}/data/review', exist_ok=True)
    G = Gazetteer()
    zone_of = lambda w: G.zone.get(w)
    meta = {'cdmp': os.path.basename(a.cdmp.rstrip('/'))}

    # ------------------------------------------------------------- tractor pumps
    feats = []
    for r in rows(f'{ROOT}/data/pump_lists/tractor_pumps.csv'):
        w, loc = int(r['div']), r['location'].strip()
        props = {'id': f"T{r['sno']}", 'sno': int(r['sno']), 'tractor': r['tractor'], 'driver': r['driver'].title(), 'phones': phones(r['phones']),
                 'loc': loc.title() if loc.isupper() else loc, 'note': r['note'] or None}
        if OFFICE.search(loc):
            o = G.ward_office(w)
            review.append({'layer': 'tractors', 'text': loc, 'ward': w, 'zone': int(r['zone']), 'matched': o['matched'] if o else '', 'kind': 'office',
                           'precision': 'office' if o else 'unplaced', 'source': o['source'] if o else '', 'score': '', 'via': ''})
            if o:
                feats.append({'type': 'Feature', 'properties': {**props, 'ward': w, 'zone': int(r['zone']), 'prec': 'office', 'match': o['matched'], 'src': o['source']},
                              'geometry': {'type': 'Point', 'coordinates': [o['lon'], o['lat']]}})
            else:
                unplaced.append({'layer': 'tractors', **props, 'ward': w, 'zone': int(r['zone']), 'prec': 'unplaced'})
            continue
        f = place('tractors', loc, w, int(r['zone']), STREETS, props)
        if f:
            feats.append(f)
    spread(feats); save('tractors', feats)

    # ------------------------------------------------------------- diesel / RP pumps
    feats = []
    for r in rows(f'{ROOT}/data/pump_lists/diesel_pumps.csv'):
        w = int(r['div']); loc = r['location']
        props = {'id': f"P{r['sno']}", 'sno': int(r['sno']), 'pump': r['pump_no'] or None, 'kind': r['kind'], 'hp': r['hp'] or None,
                 'loc': loc.title() if loc.isupper() else loc, 'placed': r['placed'], 'note': r['note'] or None}
        f = place('pumps', loc, w, int(r['zone']), STREETS, props)
        if f:
            feats.append(f)
    spread(feats); save('pumps', feats)

    # ------------------------------------------------------------- flood-prone streets: history + zone tables, merged per ward+street
    RANK = {'very_high': 4, 'high': 3, 'medium': 2, 'low': 1, '': 0, None: 0}
    spots = {}

    def spot(z, w, name):
        k = (w, norm(name))
        if k not in spots:
            spots[k] = {'name': name, 'zone': z, 'ward': w, 'years': set(), 'cls': None, 'rain': set(), 'depth': '', 'drain': '', 'pump': '',
                        'disposal': '', 'reason': '', 'pages': set()}
        return spots[k]
    for r in D('inundation_history'):
        w = ward_int(r['ward']); s = spot(int(r['zone']) if r['zone'] else zone_of(w), w, r['location'])
        if r['year']:
            s['years'].add(int(r['year']))
        if RANK[r['depth_class']] > RANK[s['cls']]:
            s['cls'] = r['depth_class']
        s['pages'].add(int(r['pdf_page']))
    for r in D('inundation_streets'):
        w = ward_int(r['ward']); s = spot(int(r['zone']) if r['zone'] else zone_of(w), w, r['street'])
        s['rain'].add(r['rain'] or 'heavy'); s['pages'].add(int(r['pdf_page']))
        for k, kk in (('max_depth', 'depth'), ('time_to_drain', 'drain'), ('disposal_point', 'disposal'), ('reason', 'reason')):
            if r[k] and not s[kk]:
                s[kk] = r[k]
        if r['pump'] and r['pump'] not in ('-', 'Nil'):
            s['pump'] = r['pump'] + (f" at {r['pump_location']}" if r['pump_location'] and r['pump_location'] != '-' else '')
    for r in D('water_stagnation'):
        w = ward_int(r['ward']); s = spot(int(r['zone']) if r['zone'] else zone_of(w), w, r['street'])
        s['rain'].add(r['rain'] or 'recorded'); s['pages'].add(int(r['pdf_page']))
    feats = []
    for (w, _), s in spots.items():
        yrs = sorted(s['years'])
        props = {'name': s['name'], 'years': yrs, 'cls': s['cls'], 'rain': sorted(s['rain']), 'depth': s['depth'] or None, 'drain': s['drain'] or None,
                 'pump': s['pump'] or None, 'disposal': s['disposal'] or None, 'reason': s['reason'] or None, 'pages': sorted(s['pages']),
                 'sev': (RANK[s['cls']] + (1 if len(yrs) >= 3 else 0)) if s['cls'] else (2 if 'heavy' in s['rain'] else 1)}
        f = place('flood_spots', s['name'], w, s['zone'], ('street', 'locality', 'poi', 'park', 'playground'), props)
        if not f:
            continue
        feats.append(f)
        g = f['_geom']
        if g is not None and f['properties']['prec'] == 'street':
            g = g.simplify(0.00002)
            if not g.is_empty:
                feats.append({'type': 'Feature', 'properties': {**f['properties'], 'line': 1}, 'geometry': mapping(g)})
    save('flood_spots', feats)

    # ------------------------------------------------------------- relief centres
    feats = []
    # the same centre can be listed twice (e.g. a zone's main table and a later 'details of relief centres' table):
    # merge rows of one ward whose names match, keeping every contact
    from rapidfuzz import fuzz
    merged_rows = []
    for r in D('relief_centres'):
        dup = next((m for m in merged_rows if m['ward'] == r['ward'] and fuzz.token_set_ratio(norm(m['name_address']), norm(r['name_address'])) >= 90), None)
        if dup:
            dup['contacts'] = json.dumps(json.loads(dup['contacts'] or '[]') + json.loads(r['contacts'] or '[]'), ensure_ascii=False)
            for k in ('capacity', 'streets_to_shift'):
                dup[k] = dup[k] or r[k]
        else:
            merged_rows.append(dict(r))
    for r in merged_rows:
        w = ward_int(r['ward']); z = int(r['zone']) if r['zone'] else zone_of(w)
        cs = [{'role': c['role'], 'phones': phones(';'.join(c['phones']))} for c in json.loads(r['contacts'] or '[]')]
        props = {'name': r['name_address'], 'cap': int(r['capacity']) if r['capacity'] else None, 'shift': r['streets_to_shift'] or None,
                 'cook': {'True': True, 'False': False}.get(r['cooking']), 'water': {'True': True, 'False': False}.get(r['drinking_water']),
                 'toilet': {'True': True, 'False': False}.get(r['toilets']), 'contacts': cs, 'page': int(r['pdf_page'])}
        f = place('relief', r['name_address'], w, z, FACILITY, props)
        if f:
            feats.append(f)
    spread(feats); save('relief', feats)

    # ------------------------------------------------------------- evacuation / water-entered-houses streets
    feats = []
    for r in D('evacuation_streets'):
        w = ward_int(r['ward']); z = int(r['zone']) if r['zone'] else zone_of(w)
        props = {'name': r['streets'], 'area': r['area'] or None, 'kind': 'evacuate' if r['needs_evacuation'] == 'True' else 'houses',
                 'persons': r['persons'] or None, 'year': r['year'] or None, 'centre': r['relief_centre'] or None, 'page': int(r['pdf_page'])}
        f = place('evacuation', r['streets'], w, z, STREETS, props, alt=(r['area'],))
        if f:
            feats.append(f)
    spread(feats); save('evacuation', feats)

    # ------------------------------------------------------------- subways
    feats = []
    for r in D('subways'):
        w = ward_int(r['ward']); z = int(r['zone']) if r['zone'] else zone_of(w)
        props = {'name': r['name'], 'len': r['length_m'] or None, 'disposal': r['disposal_point'] or None, 'pumps': r['pumps'] or None, 'page': int(r['pdf_page'])}
        f = place('subways', r['name'], w, z, ('street', 'poi', 'locality'), props, alt=(re.sub(r'subway', '', r['name'], flags=re.I),))
        if f:
            feats.append(f)
    save('subways', feats)

    # ------------------------------------------------------------- assembly points (§5.1.4 playgrounds + zone park lists)
    feats, seen = [], set()
    for src, name in (('assembly_points', 'Playground'), ('parks', 'Park')):
        for r in D(src):
            w = ward_int(r['ward']); z = int(r['zone']) if r['zone'] else zone_of(w)
            key = (w, norm(r['name']))
            if key in seen:
                continue
            seen.add(key)
            props = {'name': r['name'], 'loc': r.get('location') or None, 'type': name, 'page': int(r['pdf_page'])}
            f = place('assembly', r['name'], w, z, OPEN, props, alt=(r.get('location'),))
            if f:
                feats.append(f)
    spread(feats); save('assembly', feats)

    # ------------------------------------------------------------- NDRF & boats, tree falls
    for src, layer in (('ndrf', 'ndrf'), ('boats', 'ndrf'), ('tree_fall', 'trees')):
        feats = [] if src != 'boats' else feats
        for r in D(src):
            w = ward_int(r['ward']); z = int(r['zone']) if r['zone'] else zone_of(w)
            props = {'name': r['name'], 'loc': r.get('location') or None, 'page': int(r['pdf_page'])}
            if layer == 'ndrf':
                props.update(kind='ndrf' if src == 'ndrf' else 'boat', phones=phones(r.get('phones')), details=r.get('contact') or None)
            f = place(layer, r['name'], w, z, STREETS, props, alt=(r.get('location'),))
            if f:
                feats.append(f)
        if src != 'ndrf':
            spread(feats); save(layer, feats)

    # ------------------------------------------------------------- storm water drains (traced from GCC sheets; not inferred links)
    net = json.load(open(f'{ROOT}/raw/swd/network.json'))
    feats = [{'type': 'Feature', 'properties': {'w': c.get('wd'), 'ty': c.get('ty')},
              'geometry': {'type': 'LineString', 'coordinates': [[round(x, 5), round(y, 5)] for x, y in c['g']]}} for c in net['conduits'] if not c.get('x')]
    feats += [{'type': 'Feature', 'properties': {'id': n['id']}, 'geometry': {'type': 'Point', 'coordinates': [round(n['lon'], 5), round(n['lat'], 5)]}}
              for n in net['nodes'] if n.get('out')]
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(f'{OUT}/swd.geojson', 'w'), separators=(',', ':'))

    # ------------------------------------------------------------- wards (TNGIS boundary) + labels
    wf, lf = [], []
    for w, g in sorted(G.wards.items()):
        z = G.zone[w]
        wf.append({'type': 'Feature', 'properties': {'ward': w, 'zone': z, 'zone_name': ZN[z - 1]}, 'geometry': mapping(g.simplify(0.00003))})
        p = shapely.ops.polylabel(max(g.geoms, key=lambda x: x.area) if g.geom_type == 'MultiPolygon' else g, 0.0002)
        lf.append({'type': 'Feature', 'properties': {'ward': w, 'zone': z}, 'geometry': {'type': 'Point', 'coordinates': [round(p.x, 5), round(p.y, 5)]}})
    json.dump({'type': 'FeatureCollection', 'features': wf}, open(f'{OUT}/wards.geojson', 'w'), separators=(',', ':'))
    json.dump({'type': 'FeatureCollection', 'features': lf}, open(f'{OUT}/ward_labels.geojson', 'w'), separators=(',', ':'))

    # ------------------------------------------------------------- ward + zone contacts
    info = {'meta': meta, 'wards': {}, 'zones': {}}
    cnc = {ward_int(r['ward']): r for r in D('ward_councillors')}
    by_ward = defaultdict(list)
    for r in D('ward_contacts'):
        w = ward_int(r['ward'])
        if w:
            by_ward[w].append({'dept': r['department'], 'role': r['designation'], 'phones': phones(r['phones']) or phones(r['number_as_printed']),
                               'printed': r['number_as_printed'], 'page': int(r['pdf_page'])})
    for w in range(1, 201):
        c = cnc.get(w) or {}
        off = G.ward_office(w)
        info['wards'][w] = {'zone': G.zone.get(w), 'councillor': phones(c.get('phones')), 'councillor_printed': c.get('as_printed') or None,
                            'councillor_name': c.get('name') or None, 'contacts': by_ward.get(w, []),
                            'page': min([x['page'] for x in by_ward.get(w, [])] or [None], key=lambda v: v or 1e9),
                            'office': {'name': off['matched'], 'lon': off['lon'], 'lat': off['lat']} if off else None}
    zo = defaultdict(list)
    for r in D('officials'):
        if r['kind'] in ('contacts', 'lighting', 'health_facilities') and r['zone']:
            zo[int(r['zone'])].append({'role': r['role'] or r['row_text'][:60], 'wards': r['unit_or_wards'], 'table': r['table'],
                                       'phones': phones(r['phones']), 'page': int(r['pdf_page'])})
    for z in range(1, 16):
        info['zones'][z] = {'name': ZN[z - 1], 'officials': zo.get(z, [])}
    json.dump(info, open(f'{OUT}/wards_info.json', 'w'), separators=(',', ':'), ensure_ascii=False)
    json.dump(unplaced, open(f'{OUT}/unplaced.json', 'w'), separators=(',', ':'), ensure_ascii=False)
    with open(f'{ROOT}/data/review/placements.csv', 'w', newline='') as f:
        wr = csv.DictWriter(f, list(review[0])); wr.writeheader(); wr.writerows(review)
    tot = len(review); pl = sum(1 for r in review if r['precision'] != 'unplaced')
    print(f'placed {pl} of {tot} items ({100 * pl / tot:.0f}%); review: data/review/placements.csv')


if __name__ == '__main__':
    main()
