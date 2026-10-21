"""Place names from the CDMP and the pump lists on the map, inside their GCC ward.

One gazetteer is built from:
  TNGIS (Government of Tamil Nadu GIS)
    gcc_roads            every GCC street, with GCC's own name and its ward  -> kind 'street'
                         plus its locality / area names                     -> kind 'locality'
    schools              every school by name (CPS/CMS/CHS/CHSS... too)     -> 'school'
    gcc_community_hall   GCC community halls                                -> 'hall'
    gcc_others           GCC parks and playgrounds (polygons)               -> 'park' / 'playground'
    gcc_parks            GCC parks (points)                                 -> 'park'
    gcc_ward_office      ward (division) offices                            -> 'office'
    police_poi           named landmarks (schools, temples, offices, banks)  -> 'poi'
    health_facilities    hospitals / UPHCs                                  -> 'hospital'
  OpenStreetMap (© OSM contributors, ODbL)
    named streets -> 'street', named places -> 'locality', named POIs -> 'poi', parks -> 'park'

match(text, ward, kinds) looks only inside the ward (plus 250 m), tries the kinds in the
order given, and accepts a candidate only if it shares a distinctive word with the text
and agrees on any street number ('4th Cross Street' never matches '2nd Cross Street',
and an all-generic text like 'Chennai Primary School' matches nothing). If nothing passes,
the item gets NO coordinates. It is listed under its ward, not dropped at a made-up spot.
"""
import gzip, json, os, re
from collections import defaultdict

from rapidfuzz import fuzz
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ALIAS = [(r'\bt ?h road\b|\btvt high road\b|\btiruvottiyur high road\b', 'thiruvottiyur high road'), (r'\bomr\b', 'rajiv gandhi salai'),
         (r'\becr( road)?\b', 'east coast road'), (r'\bgst road\b', 'grand southern trunk road'), (r'\bgnt road\b', 'grand northern trunk road'),
         (r'\bmrh road\b', 'madhavaram red hills road'), (r'\bph road\b', 'poonamallee high road'), (r'\b100 (feet|ft) road\b', '100 feet road'),
         (r'\bcps\b', 'chennai primary school'), (r'\bcms\b', 'chennai middle school'), (r'\bchss\b', 'chennai higher secondary school'),
         (r'\bchs\b', 'chennai high school'), (r'\bghss\b', 'government higher secondary school'), (r'\bghs\b', 'government high school'),
         (r'\bgovt\b|\bgovernment\b', 'government'), (r'\bhr\.? ?sec\.?\b|\bhigher sec\b', 'higher secondary'), (r'\bsch\b|\bschl\b', 'school'),
         (r'\bpups\b', 'panchayat union primary school'), (r'\bmun\b|\bmpl\b', 'municipal'), (r'\bcorp\b|\bcorporation\b', 'corporation'),
         (r'\bkalyana ?mandapam\b|\bmarriage hall\b|\bthirumana mandapam\b', 'marriage hall'), (r'\bc\.? ?hall\b', 'community hall')]
ABBR = [(r'\bst\b|\bsreet\b|\bstreeet\b|\bstaeet\b|\bstareet\b', 'street'), (r'\brd\b', 'road'), (r'\bjn\b|\bjunc\b|\bjnc\b', 'junction'),
        (r'\bave\b', 'avenue'), (r'\bnagr\b|\bnaagr\b|\bnager\b|\bngr\b', 'nagar'), (r'\bkovil\b|\bkoyil\b', 'koil'),
        (r'\bext\b|\bextn\b', 'extension'), (r'\blaxmi\b|\blakshmy\b|\blakshmee\b', 'lakshmi'), (r'\bkulam\b|\bkuttai\b|\bkulum\b|\btank\b', 'pond'), (r'\beri\b', 'lake'), (r'\bfeet\b|\bft\b', 'feet'), (r'\bgdn\b', 'garden'), (r'\bcorss\b', 'cross'),
        (r'\b(\d+)\s*(st|nd|rd|th)\b', r'\1'),
        (r'\bviii\b(?= (cross|street|main|avenue|lane|block))', '8'), (r'\bvii\b(?= (cross|street|main|avenue|lane|block))', '7'),
        (r'\bvi\b(?= (cross|street|main|avenue|lane|block))', '6'), (r'\biv\b(?= (cross|street|main|avenue|lane|block))', '4'),
        (r'\biii\b(?= (cross|street|main|avenue|lane|block))', '3'), (r'\bii\b(?= (cross|street|main|avenue|lane|block))', '2'),
        (r'\bix\b(?= (cross|street|main|avenue|lane|block))', '9'), (r'\bv\b(?= (cross|street|main|avenue|lane|block))', '5'),
        (r'\bx\b(?= (cross|street|main|avenue|lane|block))', '10'), (r'\bi\b(?= (cross|street|main|avenue|lane|block))', '1'), (r'\bfirst\b', '1'), (r'\bsecond\b', '2'), (r'\bthird\b', '3'), (r'\bfourth\b', '4'),
        (r'\bfifth\b', '5'), (r'\bsixth\b', '6'), (r'\bseventh\b', '7'), (r'\beighth\b', '8'), (r'\bdr\b', ''), (r'\bthiru\b', ''), (r'\btmt\b', '')]
STOP = {'the', 'of', 'and', 'in', 'at', 'chennai', 'no', 'opp', 'near'}
GENERIC = set('street road main cross avenue lane salai nagar colony school primary middle high higher secondary government corporation '
              'municipal panchayat union chennai park playground ground community hall centre center office division zonal junction subway '
              'bridge koil link new old north south east west layout garden gardens area pond lake canal bus stand flat flats apartment '
              'marriage hall temple church mosque masjid hospital uphc extension block phase stage sector street.'.split())


def norm(s):
    s = s or ''
    s = re.sub(r'(?<=[A-Z]{2})(?=[a-z]{3})', ' ', s)    # 'VGNlaxmi' -> 'VGN laxmi'
    s = re.sub(r'(?<=\d)(?=[A-Za-z]{3,})', ' ', s)      # '70feet' -> '70 feet'
    s = s.lower().replace('&', ' and ')
    s = re.sub(r'\(n\d+\)', ' ', s)                     # GCC locality suffix '(N104)'
    s = re.sub(r'(?<=\b[a-z])\.(?=[a-z]\b)', '', s)     # T.H -> th
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    for a, b in ALIAS + ABBR:
        s = re.sub(a, b, s)
    return ' '.join(t for t in s.split() if t not in STOP)


def _sig(s):
    toks = s.split()
    return {t for t in toks if t not in GENERIC and not t.isdigit() and len(t) > 1}, {t for t in toks if t.isdigit()}


def compatible(q, n):
    """Guard against fuzzy false friends: share a distinctive word, and agree on street numbers."""
    dq, nq = _sig(q); dn, nn = _sig(n)
    if not dn or not dq:
        return q == n and bool(q)
    if not any(fuzz.ratio(a, b) >= 85 for a in dq for b in dn):
        return False
    if nn and nq and nn != nq:
        return False
    if nn and not nq and len(nn) == 1 and any(w in n for w in ('cross', 'street', 'avenue', 'main road')):
        return False                                    # '2nd Main Road' is not 'Main Road'
    if nq and not nn and any(w in q for w in ('cross', 'street', 'avenue', 'lane', 'block')):
        return False                                    # '14th Street' is not 'Cross Street'
    return True


def variants(text):
    """Cleaner / smaller versions of a printed location to retry, most specific first."""
    t = (text or '').strip()
    out = [t]
    c = re.sub(r'\(.*?\)|\b(opp\.?|opposite|near|nr\.?|behind|in ?front of|infront of|adjacent to)\b.*$|chennai\s*-?\s*\d*|\b6000\d\d\b', ' ', t, flags=re.I)
    c = ' '.join(c.split()).strip(' ,.-')
    out.append(c)
    parts = [p.strip(' ,.-') for p in re.split(r',|&|/|\band\b|\bfrom\b|\bupto\b|\bjn\.? of\b|\bjunction of\b| - |\bto\b', c, flags=re.I)]
    out += [p for p in parts if len(p) > 3]
    for p in [c] + parts:
        h = re.sub(r'\b\d+\s*(st|nd|rd|th)?\s*(street|cross street|cross|main road|avenue|lane|link road)\b.*$', '', p, flags=re.I).strip(' ,.-')
        if h and h != p and len(h) > 5:
            out.append(h)
    seen = []
    for v in out:
        if v and v not in seen:
            seen.append(v)
    return seen


def combine(gs):
    """Merge pieces of one street. TNGIS serves 4-decimal coordinates, so tiny pieces can be invalid;
    fall back to a plain collection rather than a topological union."""
    import shapely
    gs = [g for g in gs if g is not None and not g.is_empty]
    try:
        return unary_union(gs)
    except Exception:
        try:
            return unary_union([g.buffer(0.00001) for g in gs])
        except Exception:
            return shapely.GeometryCollection(gs)


def _load(name):
    p = f'{ROOT}/raw/tngis/{name}.geojson.gz'
    if not os.path.exists(p):
        return []
    with gzip.open(p, 'rt') as f:
        return [x for x in json.load(f)['features'] if x.get('geometry')]


def _load_osm(name):
    p = f'{ROOT}/raw/osm/{name}.geojson.gz'
    if not os.path.exists(p):
        return []
    with gzip.open(p, 'rt') as f:
        return [x for x in json.load(f)['features'] if x.get('geometry')]


def _ward(v):
    try:
        return int(str(v).strip().lstrip('0') or 0) or None
    except ValueError:
        return None


def _tag(tags, key):
    m = re.search(rf'"{key}"=>"([^"]*)"', tags or '')
    return m.group(1) if m else None


class Gazetteer:
    def __init__(self):
        self.wards, self.zone = {}, {}
        for f in _load('gcc_ward_boundary'):
            w = _ward(f['properties']['ward'])
            self.wards[w] = shape(f['geometry']).buffer(0)
            self.zone[w] = _ward(f['properties']['zone'])
        self.zones = defaultdict(list)
        for w, g in self.wards.items():
            self.zones[self.zone[w]].append(g)
        self.zones = {z: unary_union(gs) for z, gs in self.zones.items()}
        self.city = unary_union(list(self.wards.values()))
        E = []

        def add(name, kind, geom, src, ward=None, extra=None):
            n = norm(name)
            if n and geom is not None and not geom.is_empty:
                E.append({'name': name.strip(), 'norm': n, 'kind': kind, 'geom': geom, 'src': src, 'ward': ward, **(extra or {})})

        # GCC streets (polygons) grouped by ward + name, and the localities they belong to
        roads, locs = defaultdict(list), defaultdict(list)
        for f in _load('gcc_roads'):
            p = f['properties']; w = _ward(p.get('ward_no')); g = shape(f['geometry'])
            if p.get('road_name'):
                roads[(w, p['road_name'].strip())].append(g)
            for k in ('locality', 'area_name'):
                if p.get(k):
                    locs[(w, re.sub(r'\(N\d+\)', '', p[k]).strip())].append(g)
        for (w, n), gs in roads.items():
            add(n, 'street', combine(gs), 'TNGIS gcc_road_of_width', w)
        for (w, n), gs in locs.items():
            add(n, 'locality', __import__('shapely').GeometryCollection(gs).convex_hull, 'TNGIS gcc_road_of_width (locality)', w)
        for f in _load('schools'):
            add(f['properties'].get('name') or '', 'school', shape(f['geometry']), 'TNGIS schools')
        for f in _load('gcc_community_hall'):
            p = f['properties']
            add(p.get('address') or 'Community hall ' + (p.get('road_name') or ''), 'hall', shape(f['geometry']).centroid, 'TNGIS gcc_community_hall', _ward(p.get('ward_no')),
                {'street': p.get('road_name')})
        for f in _load('gcc_others'):
            p = f['properties']; cat = (p.get('category') or '').upper()
            f['geometry'] = f['geometry']
            kind = {'PARK': 'park', 'PLAYGROUND': 'playground'}.get(cat, 'school' if 'SCHOOL' in cat else 'hospital' if 'H' in cat[:3] or 'PHC' in cat else 'poi')
            label = {'park': 'Park', 'playground': 'Playground', 'school': 'School', 'hospital': cat.title()}.get(kind, cat.title())
            add(f"{label} on {p.get('streetname') or ''}", kind, shape(f['geometry']).centroid, 'TNGIS gcc_others', _ward(p.get('ward_no')),
                {'street': p.get('streetname')})
        for f in _load('gcc_parks'):
            p = f['properties']
            add(f"Park on {p.get('street_name') or ''}", 'park', shape(f['geometry']), 'TNGIS gcc_parks', _ward(p.get('ward_no')), {'street': p.get('street_name')})
        self.offices = {}
        for f in _load('gcc_ward_office'):
            p = f['properties']; w = _ward(p.get('ward_no'))
            add(f"Ward {w} office, {p.get('street_name') or ''}", 'office', shape(f['geometry']), 'TNGIS gcc_ward_office', w)
            self.offices.setdefault(w, (shape(f['geometry']), p.get('street_name')))
        for f in _load('gcc_office_buildings'):
            p = f['properties']; w = _ward(p.get('ward_no'))
            if (p.get('cat') or '').upper() == 'WARD OFFICE':
                self.offices.setdefault(w, (shape(f['geometry']).centroid, p.get('streetname')))
        self.zone_offices = {}
        for f in _load('gcc_zone_office'):
            p = f['properties']
            self.zone_offices.setdefault(_ward(p.get('zone_no')), (shape(f['geometry']), p.get('street_name')))
        for f in _load('police_poi'):
            p = f['properties']
            add(p.get('name') or '', 'school' if 'Education' in (p.get('poi_type') or '') else 'poi', shape(f['geometry']), 'TNGIS police_point_of_interest')
        for f in _load('health_facilities'):
            p = f['properties']
            add(p.get('facility_name') or '', 'hospital', shape(f['geometry']), 'TNGIS all_health_facilities')
        # OpenStreetMap
        for f in _load_osm('lines'):
            add(f['properties'].get('name') or '', 'street', shape(f['geometry']), 'OpenStreetMap')
        for f in _load_osm('points') + _load_osm('polys'):
            p = f['properties']; tags = p.get('other_tags') or ''
            place = p.get('place') or _tag(tags, 'place')
            amen = p.get('amenity') or _tag(tags, 'amenity'); leis = p.get('leisure') or _tag(tags, 'leisure')
            kind = ('locality' if place else 'park' if leis in ('park', 'garden') else 'playground' if leis in ('pitch', 'playground', 'stadium', 'sports_centre')
                    else 'school' if amen in ('school', 'college') else 'hall' if amen in ('community_centre', 'events_venue', 'marketplace') else 'hospital'
                    if amen in ('hospital', 'clinic') else 'poi')
            g = shape(f['geometry'])
            add(p.get('name') or '', kind, g if g.geom_type == 'Point' else g.representative_point(), 'OpenStreetMap')
        self.E = E
        self.tree = STRtree([e['geom'] for e in E])
        print(f'gazetteer: {len(E)} names', {k: sum(1 for e in E if e["kind"] == k) for k in sorted({e["kind"] for e in E})})

    # -------------------------------------------------------------------------------------------
    def region(self, ward=None, zone=None, buf=0.0025):
        if ward in self.wards:
            return self.wards[ward], self.wards[ward].buffer(buf)
        if zone in self.zones:
            return self.zones[zone], self.zones[zone].buffer(buf)
        return None, self.city.buffer(buf)

    def candidates(self, region, kinds):
        idx = self.tree.query(region, predicate='intersects')
        return [self.E[int(i)] for i in idx if self.E[int(i)]['kind'] in kinds]

    def score(self, q, e):
        n = e['norm']
        if not compatible(q, n):
            return 0
        if n == q:
            return 100
        s = 0.65 * fuzz.token_set_ratio(q, n) + 0.35 * fuzz.ratio(q, n)
        return s

    def match(self, text, ward=None, zone=None, kinds=('street', 'locality', 'poi', 'park', 'playground', 'school', 'hall'), min_score=80):
        """Best gazetteer entry for a printed location, or None. Kinds are tried in order."""
        core, region = self.region(ward, zone)
        cands = self.candidates(region, set(kinds))
        for v in variants(text):
            q = norm(v)
            if not q:
                continue
            for kind in kinds:
                best = None
                for e in cands:
                    if e['kind'] != kind:
                        continue
                    s = self.score(q, e)
                    # same-ward attribute (GCC layers) breaks ties in favour of the ward it is printed under
                    if s and e['ward'] and ward and e['ward'] == ward:
                        s += 3
                    need = min_score - 5 if kind in ('school', 'hall', 'park', 'playground', 'hospital') else min_score
                    if s >= need and (best is None or s > best[0]):
                        best = (s, e)
                if best:
                    s, e = best
                    g = e['geom']
                    pt = g if g.geom_type == 'Point' else g.representative_point()
                    if core is not None and not pt.within(region):
                        # long streets: use the part inside the ward
                        try:
                            part = g.intersection(region)
                        except Exception:
                            part = g.representative_point().buffer(0)
                        if not part.is_empty:
                            pt = part.representative_point(); g = part
                    exact = v == text or norm(v) == norm(text)
                    if kind == 'street' and ward not in self.wards and zone not in self.zones:
                        exact = False                   # no ward printed: a long road's midpoint is only approximate
                    prec = {'street': 'street', 'locality': 'locality', 'office': 'office'}.get(kind, 'place')
                    if not exact and kind in ('locality', 'street') and ward not in self.wards:
                        prec = 'locality'
                    elif not exact and kind == 'locality':
                        prec = 'locality'
                    elif not exact and prec == 'place' and not compatible(norm(text), e['norm']):
                        prec = 'locality'
                    return {'lon': round(pt.x, 6), 'lat': round(pt.y, 6), 'precision': prec, 'matched': e['name'], 'kind': kind,
                            'source': e['src'], 'score': round(s), 'via': v if v != text else None,
                            'geom': g if kind == 'street' else None}
        return None

    def ward_office(self, ward):
        if ward in self.offices:
            g, street = self.offices[ward]
            return {'lon': round(g.x, 6), 'lat': round(g.y, 6), 'precision': 'office', 'matched': f'Ward {ward} office' + (f', {street}' if street else ''),
                    'kind': 'office', 'source': 'TNGIS gcc_ward_office', 'score': 100, 'via': None, 'geom': None}
        z = self.zone.get(ward)
        if ward in self.wards:      # this ward's office is not in TNGIS: the nearest ward office in the same zone
            c = self.wards[ward].representative_point()
            near = sorted((g.distance(c), w2, g, st) for w2, (g, st) in self.offices.items() if self.zone.get(w2) == z)
            if near and near[0][0] < 0.03:
                _, w2, g, st = near[0]
                return {'lon': round(g.x, 6), 'lat': round(g.y, 6), 'precision': 'office', 'matched': f'Ward {w2} office' + (f', {st}' if st else '') + f' (nearest; no Ward {ward} office in TNGIS)',
                        'kind': 'office', 'source': 'TNGIS gcc_ward_office', 'score': 90, 'via': None, 'geom': None}
        if z in self.zone_offices:
            g, street = self.zone_offices[z]
            return {'lon': round(g.x, 6), 'lat': round(g.y, 6), 'precision': 'office', 'matched': f'Zone {z} office' + (f', {street}' if street else ''),
                    'kind': 'office', 'source': 'TNGIS gcc_zone_office', 'score': 100, 'via': None, 'geom': None}
        return None

    def ward_at(self, lon, lat):
        p = Point(lon, lat)
        return next((w for w, g in self.wards.items() if g.contains(p)), None)
