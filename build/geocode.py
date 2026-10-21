"""Place free-text CDMP / pump locations inside their GCC ward.

geocode(text, ward=None, zone=None, kind='any') -> dict(lon, lat, precision, matched, line)
  precision: 'street'  - an OSM street of that name inside (or within 400 m of) the ward
             'place'   - an OSM named place / POI / park inside the ward
             'ward'    - nothing matched: a point inside the ward (shown as approximate)
             'zone'    - no ward given: zone centroid
  line: for street matches, the street's geometry clipped to the ward buffer (for drawing)
"""
import json, gzip, re, pickle, os
from collections import defaultdict
from rapidfuzz import fuzz
from shapely.geometry import shape, Point, mapping
from shapely.ops import unary_union, linemerge
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ALIAS = [(r'\bt ?h road\b|\btvt high road\b', 'thiruvottiyur high road'), (r'\bomr\b', 'rajiv gandhi salai'),
         (r'\becr( road)?\b', 'east coast road'), (r'\bgst road\b', 'grand southern trunk road'),
         (r'\bgnt road\b', 'grand northern trunk road'), (r'\bmrh road\b', 'madhavaram red hills road'),
         (r'\bmkb nagar\b', 'mkb nagar'), (r'\bkk nagar\b', 'k k nagar'), (r'\b100 (feet|ft) road\b', '100 feet road'),
         (r'\bpoonamallee high road\b|\bph road\b', 'poonamallee high road'), (r'\bnsk salai\b', 'nsk salai')]
ABBR = [(r'\bst\b', 'street'), (r'\brd\b', 'road'), (r'\bjn\b|\bjunc\b|\bjunction\b|\bjnc\b', 'junction'),
        (r'\bave\b|\bavenue\b', 'avenue'), (r'\bnagr\b|\bnaagr\b|\bnager\b', 'nagar'),
        (r'\bkovil\b|\bkoyil\b|\bkoil\b', 'koil'), (r'\bsalai\b', 'salai'), (r'\bmain\s+rd\b', 'main road'),
        (r'\bext\b|\bextn\b', 'extension'), (r'\bgdn\b', 'garden'), (r'\bcross\s+st\b', 'cross street'),
        (r'\b(\d+)\s*(st|nd|rd|th)\b', r'\1'), (r'\bfirst\b', '1'), (r'\bsecond\b', '2'), (r'\bthird\b', '3'),
        (r'\bfourth\b', '4'), (r'\bfifth\b', '5'), (r'\bsixth\b', '6'), (r'\bi\b(?=\s+(street|main|cross|avenue))', '1'),
        (r'\bthiru\b', 'thiru'), (r'\bdr\b', ''), (r'\bnear\b.*$', ''), (r'\bopp\b.*$', ''),
        (r'\bsreet\b|\bstreeet\b|\bstaeet\b|\bstareet\b', 'street'), (r'\bcorss\b', 'cross')]
STOP = {'the', 'of', 'and', 'in', 'at', 'area', 'chennai', 'ward', 'division', 'zone'}


def norm(s):
    s = (s or '').lower().replace('&', ' and ')
    s = re.sub(r'(?<=\b[a-z])\.(?=[a-z]\b)', '', s)       # T.H -> th
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    for a, b in ALIAS + ABBR:
        s = re.sub(a, b, s)
    toks = [t for t in s.split() if t not in STOP]
    return ' '.join(toks)


def variants(text):
    """Cleaner / smaller versions of a CDMP location to retry: drop '(...)', 'opp. ...', pin codes;
    then each part of a list ('A, B & C'); then 'X Nagar 8th Street' -> 'X Nagar'."""
    t = text or ''
    out = [t]
    c = re.sub(r'\(.*?\)|\b(opp|opp\.|opposite|near|nr|behind|infront of|in front of)\b.*$|chennai\s*-?\s*\d*|\b6000\d\d\b', ' ', t, flags=re.I)
    c = ' '.join(c.split()).strip(' ,.-')
    out.append(c)
    parts = [p.strip(' ,.-') for p in re.split(r',|&|/|\band\b|\bfrom\b|\bto\b|\bupto\b|\bjn of\b|\bjunction of\b| - ', c, flags=re.I)]
    parts = [p for p in parts if len(p) > 3]
    out += parts
    for p in [c] + parts:
        h = re.sub(r'\b\d+\s*(st|nd|rd|th)?\s*(street|cross street|cross|main road|avenue|lane|link road)\b.*$', '', p, flags=re.I).strip(' ,.-')
        if h and h != p and len(h) > 5: out.append(h)
        h2 = re.sub(r'\s+(street|st|road|rd|main road|salai)$', '', p, flags=re.I).strip()
        if h2 != p and len(h2) > 5: out.append(h2)
    return out


GENERIC = set('street road main cross avenue lane salai nagar colony school primary middle high higher secondary hr sec '
              'govt government corporation chennai cps chs cms park extension block phase junction subway bridge koil '
              'link new old north south east west 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 30 '
              'community hall centre center ground playground layout garden gardens area pond lake canal bus stand '
              'office division zonal near opposite jn hospital temple church mosque masjid flat flats apartment'.split())


def _sig(s):
    toks = s.split()
    return {t for t in toks if t not in GENERIC and not t.isdigit() and len(t) > 1}, {t for t in toks if t.isdigit()}


def compatible(q, n):
    """Guard against fuzzy false friends: share a distinctive word, and agree on street numbers."""
    dq, nq = _sig(q); dn, nn = _sig(n)
    if not dn:
        return False                      # '4th Cross Street', '2nd Main Road' - could be anywhere
    if not dq and q != n:
        return False                      # all-generic query ('Chennai Higher Secondary School') matches nothing
    if dq and not any(fuzz.ratio(a, b) >= 80 for a in dq for b in dn):
        return False
    if nn and nn != nq:
        return False
    if nq and nn and nq != nn:
        return False
    return True


def _load_geojson(path):
    op = gzip.open if path.endswith('.gz') else open
    with op(path, 'rt') as f:
        return json.load(f)['features']


class Geocoder:
    def __init__(self):
        self.wards = {}
        for f in json.load(open(f'{ROOT}/data/wards.geojson'))['features']:
            self.wards[f['properties']['ward']] = shape(f['geometry'])
        self.zones = defaultdict(list)
        for f in json.load(open(f'{ROOT}/data/wards.geojson'))['features']:
            self.zones[f['properties']['zone']].append(self.wards[f['properties']['ward']])
        self.zones = {z: unary_union(g) for z, g in self.zones.items()}
        # streets: name -> geometry pieces
        streets = []
        for f in _load_geojson(f'{ROOT}/raw/osm/lines.geojson.gz'):
            streets.append((f['properties']['name'], shape(f['geometry'])))
        self.st_geom = [g for _, g in streets]
        self.st_name = [n for n, _ in streets]
        self.st_norm = [norm(n) for n in self.st_name]
        self.st_tree = STRtree(self.st_geom)
        # places / POIs
        pl = []
        for f in _load_geojson(f'{ROOT}/raw/osm/points.geojson.gz'):
            p = f['properties']; tags = p.get('other_tags') or ''
            if f['geometry'] is None: continue
            pl.append((p['name'], shape(f['geometry']), tags))
        mp = f'{ROOT}/raw/osm/polys.geojson.gz'
        if os.path.exists(mp):
            for f in _load_geojson(mp):
                if f['geometry'] is None: continue
                pl.append((f['properties']['name'], shape(f['geometry']).representative_point(), ''))
        self.pl_geom = [g for _, g, _ in pl]
        self.pl_name = [n for n, _, _ in pl]
        self.pl_norm = [norm(n) for n in self.pl_name]
        self.pl_tree = STRtree(self.pl_geom)

    def area(self, ward=None, zone=None, buf=0.0036):
        if ward in self.wards:
            return self.wards[ward], self.wards[ward].buffer(buf)
        if zone in self.zones:
            return self.zones[zone], self.zones[zone].buffer(buf)
        if not hasattr(self, '_city'):
            self._city = unary_union(list(self.zones.values()))
        return None, self._city.buffer(buf)      # whole GCC: match only, never a fallback point

    def _best(self, q, idx, names, region, core, want_street):
        best = (0, None)
        for i in idx:
            n = names[i]
            if not n or not compatible(q, n):
                continue
            if n == q:
                s = 100
            else:
                s = fuzz.token_set_ratio(q, n)
                # token_set_ratio rewards subsets: "nagar" matching "x nagar 2 street"; penalise length gaps
                lq, ln = len(q.split()), len(n.split())
                if min(lq, ln) <= 1 and max(lq, ln) > 1:
                    s -= 25
                s = 0.7 * s + 0.3 * fuzz.ratio(q, n)
            if s > best[0]:
                best = (s, i)
        return best

    def geocode(self, text, ward=None, zone=None, kind='any'):
        tried = []
        for v in variants(text):
            if v in tried: continue
            tried.append(v)
            g = self._geocode1(v, ward, zone, kind)
            if g is None or g['precision'] in ('street', 'place'):
                if g is not None and v != text: g['via'] = v
                return g
        return self._geocode1(text, ward, zone, kind)

    def _geocode1(self, text, ward=None, zone=None, kind='any'):
        if isinstance(ward, str) and ward.strip().isdigit():
            ward = int(ward)
        core, region = self.area(ward if isinstance(ward, int) else None, zone)
        q = norm(text)
        out = None
        if region is not None and q:
            # street match
            idx = [int(i) for i in self.st_tree.query(region, predicate='intersects')]
            s, i = self._best(q, idx, self.st_norm, region, core, True)
            # place match
            pidx = [int(i) for i in self.pl_tree.query(region, predicate='intersects')]
            ps, pi = self._best(q, pidx, self.pl_norm, region, core, False)
            if kind == 'facility' and pi is not None and ps >= 72 and ps >= s - 5:
                out = dict(precision='place', matched=self.pl_name[pi], score=round(ps), geom=self.pl_geom[pi])
            elif i is not None and s >= 84 and s >= ps:
                name = self.st_name[i]
                parts = [self.st_geom[j] for j in idx if self.st_name[j] == name]
                line = unary_union(parts).intersection(region) if parts else None
                if line is not None and line.geom_type == 'MultiLineString':
                    line = linemerge(line)
                pt = line.interpolate(0.5, normalized=True) if line is not None and line.length > 0 and line.geom_type in ('LineString',) else (line.representative_point() if line is not None and not line.is_empty else self.st_geom[i].representative_point())
                out = dict(precision='street', matched=name, score=round(s), geom=pt, line=line)
            elif pi is not None and ps >= 84:
                out = dict(precision='place', matched=self.pl_name[pi], score=round(ps), geom=self.pl_geom[pi])
            elif q and ' ' in q:
                # neighbourhood names: streets that START with the same words ("kargil nagar 2 street")
                head = q.split(' street')[0].split(' road')[0]
                cand = [j for j in idx if self.st_norm[j].startswith(head + ' ') and len(head) > 6]
                if cand:
                    g = unary_union([self.st_geom[j] for j in cand]).intersection(region)
                    if not g.is_empty:
                        out = dict(precision='street', matched=self.st_name[cand[0]] + ' (area)', score=80,
                                   geom=g.centroid if g.centroid.within(region) else g.representative_point())
        if out is None:
            if core is not None:
                out = dict(precision='ward' if isinstance(ward, int) else 'zone', matched=None, score=0,
                           geom=core.representative_point())
            else:
                return None
        g = out.pop('geom')
        out['lon'], out['lat'] = round(g.x, 6), round(g.y, 6)
        if out.get('line') is not None:
            ln = out['line'].simplify(0.00002)
            out['line'] = mapping(ln) if not ln.is_empty else None
        return out


if __name__ == '__main__':
    import sys
    G = Geocoder()
    for t, w in [('Kargil Nagar', 7), ('Radhakrishna Nagar', 7), ('T.H Road', 14), ('Ganesapuram Subway', 45),
                 ('Habibullah Road', 113), ('Porur Jn', 151), ('Velachery Main Road', 177), ('Sindhu salai', 156)]:
        print(t, w, G.geocode(t, w))
