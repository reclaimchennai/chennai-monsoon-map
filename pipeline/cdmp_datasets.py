"""Normalised datasets from the classified CDMP tables (called by cdmp_extract.py).

Every zone chapter of the plan was typed by a different office, so the same table
comes with different column wording ("Streets where inundation seen" /
"Name of the Street" / "Location"). Columns are therefore found by header
keywords, never by position, and every output row keeps `pdf_page` and
`table_id` so it can be traced back to the PDF.
"""
import csv, json, os, re
from collections import defaultdict

from cdmp_extract import one_line, phones_in, SNO, ROMAN, WARD_HEAD


# ----------------------------------------------------------------------------------- helpers
def top_level_alternatives(p):
    """'a|b(c|d)|e' -> ['a', 'b(c|d)', 'e'] (only splits outside groups)."""
    out, depth, cur = [], 0, ''
    for ch in p:
        depth += ch == '(' and 1 or ch == ')' and -1 or 0
        if ch == '|' and depth == 0:
            out.append(cur); cur = ''
        else:
            cur += ch
    return out + [cur]


def col(t, *patterns, exclude=None):
    """Index of the column matching the earliest pattern ('a|b|c' alternatives are tried in order,
    so 'name & address' wins over a 'Ward Name' column for the pattern 'name ?& ?addr|name')."""
    alts = [a for p in patterns for a in top_level_alternatives(p)]
    for p in alts:
        for j, c in enumerate(t['columns']):
            if re.search(p, c, re.I) and not (exclude and re.search(exclude, c, re.I)):
                return j
    return None


def cell(r, j):
    return one_line(r[j]) if j is not None and j < len(r) and r[j] is not None else ''


def records(t):
    """Group table rows into records. A row with a serial number starts a record; rows without one
    (merged cells in the PDF) continue the record above. Returns [(first_row, [rows], page)]."""
    sj = col(t, r'^(s|sl)\.? ?no', r'^s\.?no', r'serial')
    if sj is None and t['rows'] and t['columns'] and all(not r or r[0] is None or SNO.match(one_line(r[0]) or 'x') for r in t['rows'][:5]):
        sj = 0
    out = []
    for r, pg in zip(t['rows'], t['row_pages']):
        if not any((c or '').strip() for c in r):
            continue
        sn = cell(r, sj) if sj is not None else 'x'
        if sj is None or sn or not out:
            out.append([r, [r], pg])
        else:
            out[-1][1].append(r)
    return out


def merged(rows, j):
    """A column's text over all rows of a record (cells split across rows in the PDF)."""
    vals = [one_line(r[j]) for r in rows if j is not None and j < len(r) and r[j]]
    return ' '.join(v for i, v in enumerate(vals) if v not in vals[:i])


def ward_of(s):
    """'4' / '4 Ernavoor' / 'Ward 5, Manickkam Nagar' / '101/Anna Nagar' / '176176' -> int or None."""
    s = one_line(s)
    m = re.search(r'(?:ward|div(?:ision)?\.?)\s*(?:no\.?)?\s*[-:]?\s*(\d{1,3})\b', s, re.I) or re.match(r'^\s*(\d{1,3})(?!\d)', s)
    if m:
        w = int(m.group(1))
        return w if 1 <= w <= 200 else None
    m = re.match(r'^(\d{1,3})\1$', s)          # '176176' (cell printed twice)
    return int(m.group(1)) if m else None


def yes(s):
    s = one_line(s).lower()
    return True if s.startswith(('yes', 'y', 'available', 'avl')) else False if s.startswith(('no', 'n', 'nil', 'not')) else None


def place_text(s):
    """A ward cell sometimes carries the ward name: '4 Ernavoor' -> 'Ernavoor'."""
    return re.sub(r'^\s*(ward\s*)?\d{1,3}\s*[/,.-]?\s*', '', one_line(s), flags=re.I).strip()


def year_of(*texts):
    for s in texts:
        m = re.findall(r'(?<!\d)(20[12]\d)(?!\d)', s or '')
        if m:
            return int(m[-1])
    return None


def zone_of_ward(w):
    ZR = [(1, 14), (15, 22), (23, 33), (34, 48), (49, 63), (64, 78), (79, 93), (94, 108), (109, 126),
          (127, 142), (143, 155), (156, 167), (168, 180), (181, 191), (192, 200)]
    return next((i + 1 for i, (a, b) in enumerate(ZR) if w and a <= w <= b), None)


def zone_val(z):
    z = one_line(z).upper().replace('ZONE', '').strip(' -.')
    return ROMAN.get(z) or (int(z) if z.isdigit() and 1 <= int(z) <= 15 else None)


def base(t, pg):
    return {'zone': t['zone'], 'pdf_page': pg, 'table_id': t['id']}


def phone_list(s):
    return ';'.join(dict.fromkeys(phones_in(s)))


# ----------------------------------------------------------------------------------- per kind
def ward_committee(t, councillors):
    out = []
    ward = t.get('ward_heading')
    dj, gj, pj = col(t, r'department'), col(t, r'designation'), col(t, r'contact|number|phone|mobile')
    if dj is None:
        dj, gj, pj = 0, 1, len(t['columns']) - 1
    dept = ''
    for r, pg in zip(t['rows'], t['row_pages']):
        d = cell(r, dj)
        m = re.match(r'^Ward\s+committee\s*[–-]\s*(\d+)', d, re.I)
        if m:                        # two wards' tables drawn as one
            ward = int(m.group(1)); continue
        if d.lower().startswith('name of the dep'):
            continue
        if d:
            dept = d
        g, p = cell(r, gj), cell(r, pj)
        if 'councillor' in g.lower():
            councillors[ward].setdefault('name', d)
            councillors[ward].setdefault('phones', [])
            councillors[ward]['phones'] += [x for x in phones_in(p) if x not in councillors[ward]['phones']]
            continue
        if not (g or p):
            continue
        out.append({**base(t, pg), 'ward': ward, 'department': dept, 'designation': g, 'number_as_printed': p, 'phones': phone_list(p)})
    return out


def inundation_history(t):
    out = []
    year = year_of(t.get('caption'), t['title'], t['section'])
    zj, wj, lj = col(t, r'^zone'), col(t, r'ward|division|^div'), col(t, r'location|street|area')
    cls = [(col(t, p), name) for p, name in [(r'very ?high', 'very_high'), (r'(?<!very )high(?! ?vul.*very)', 'high'),
                                              (r'medium', 'medium'), (r'low', 'low')]]
    cls = [(j, n) for j, n in cls if j is not None]
    sj = col(t, r'status')
    for first, rows, pg in records(t):
        loc = merged(rows, lj)
        if not loc:
            continue
        c = next((n for j, n in cls if re.match(r'\s*(yes|y|✓|√)', cell(first, j), re.I)), None)
        out.append({**base(t, pg), 'year': year, 'zone': zone_val(cell(first, zj)) or t['zone'], 'ward': ward_of(cell(first, wj)),
                    'location': loc, 'depth_class': c, 'status': cell(first, sj)})
    return out


def inundation_streets(t):
    out = []
    wj = col(t, r'^ward|ward ?no|div')
    lj = col(t, r'inundation seen|streets? where|name of the (street|area|location)|location|street', exclude=r'pump')
    dep, dur = col(t, r'depth'), col(t, r'time|days|duration')
    pc, pl = col(t, r'capacity of pump|pump.*(capacity|hp)|^pumps?$|no\.? of pump'), col(t, r'location of pump|pump.*location')
    dp = col(t, r'disposal')
    rs = col(t, r'reason|cause')
    for first, rows, pg in records(t):
        s = merged(rows, lj)
        if not s:
            continue
        out.append({**base(t, pg), 'ward': ward_of(cell(first, wj)), 'street': s, 'max_depth': merged(rows, dep), 'time_to_drain': merged(rows, dur),
                    'pump': merged(rows, pc), 'pump_location': merged(rows, pl), 'disposal_point': merged(rows, dp), 'reason': merged(rows, rs),
                    'rain': rain_of(t)})
    return out


def rain_of(t):
    s = ' '.join([t.get('caption') or '', t['title'] or '']).lower()
    for k in ('sewer', 'heavy', 'moderate', 'mild'):
        if k in s:
            return 'sewer_block' if k == 'sewer' else k
    return ''


def water_stagnation(t):
    out = []
    wj = col(t, r'ward|div')
    lj = col(t, r'street|location|area|name of the', exclude=r'ward')
    mj = col(t, r'manhole')
    for first, rows, pg in records(t):
        s = merged(rows, lj)
        if not s or s.lower() in ('nil', '-', 'total'):
            continue
        out.append({**base(t, pg), 'ward': ward_of(cell(first, wj)), 'street': s, 'rain': rain_of(t), 'year': year_of(t.get('caption'), t['title']),
                    'manholes': cell(first, mj)})
    return out


def fill(t, j):
    return sum(1 for r in t['rows'] if j is not None and j < len(r) and (r[j] or '').strip()) / max(1, len(t['rows']))


def longest_text_col(t, exclude):
    """The column holding the longest text, ignoring columns whose header names another field."""
    best, bj = 0, None
    for j, c in enumerate(t['columns']):
        if re.search(exclude, c, re.I):
            continue
        vals = [one_line(r[j]) for r in t['rows'] if j < len(r) and r[j]]
        if not vals:
            continue
        avg = sum(len(v) for v in vals) / len(t['rows'])
        if avg > best and not all(re.fullmatch(r'[\d\s.,/-]*', v) for v in vals):
            best, bj = avg, j
    return bj


def relief_centres(t):
    out = []
    wj, cj = col(t, r'ward|div'), col(t, r'capacity')
    nj = col(t, r'name ?& ?addr|name ?of ?(the )?relief|relief cent|name|address', exclude=r'street|shift|ward')
    if nj is None or fill(t, nj) < 0.15:
        nj = longest_text_col(t, r'ward|capacity|street|shift|drink|toilet|cook|responsib|officer|designation|contact|room|available|s\.? ?no|sl')
    stj = col(t, r'street|shift')
    dw, tl, ck = col(t, r'drinking'), col(t, r'toilet'), col(t, r'cook')
    rj, gj, pj = col(t, r'responsib'), col(t, r'officer|designation|in-? ?charge'), col(t, r'contact|phone|mobile')
    for first, rows, pg in records(t):
        name = merged(rows, nj)
        if not name or name.lower() == 'total' or re.fullmatch(r'[\d\s/.-]+', name):
            continue
        contacts = []
        for r in rows:
            ph = phones_in(cell(r, pj)) or phones_in(' '.join(cell(r, j) for j in range(len(r))))
            role = ' '.join(x for x in [cell(r, gj), f"({cell(r, rj)})" if cell(r, rj) else ''] if x)
            if ph or role:
                contacts.append({'role': role, 'phones': ph})
        cap = re.sub(r'[^\d]', '', cell(first, cj))
        if not cap:                      # capacity printed under a split header: the nearest numeric cell after the name
            cap = next((re.sub(r'\D', '', cell(first, k)) for k in range((nj or 0) + 1, len(first)) if re.fullmatch(r'\d{2,5}', cell(first, k))), '')
        out.append({**base(t, pg), 'ward': ward_of(cell(first, wj)), 'name_address': name, 'capacity': int(cap) if cap else None,
                    'streets_to_shift': merged(rows, stj), 'drinking_water': yes(cell(first, dw)), 'toilets': yes(cell(first, tl)),
                    'cooking': yes(cell(first, ck)), 'contacts': json.dumps(contacts, ensure_ascii=False)})
    return out


def subways(t):
    out = []
    wj = col(t, r'ward|name')
    nj = col(t, r'name of the subway|subway name|location|name', exclude=r'ward') or wj
    lj, dj, pj = col(t, r'length'), col(t, r'disposal'), col(t, r'pump')
    for first, rows, pg in records(t):
        name = merged(rows, nj)
        if not name:
            continue
        out.append({**base(t, pg), 'ward': ward_of(cell(first, wj)), 'name': place_text(name) or name, 'length_m': cell(first, lj),
                    'disposal_point': merged(rows, dj), 'pumps': merged(rows, pj)})
    return out


def evacuation(t, needs):
    out = []
    wj = col(t, r'ward|div')
    sj = col(t, r'streets?|area|location|name of', exclude=r'ward|relief')
    pj, yj, rj = col(t, r'persons|people'), col(t, r'year'), col(t, r'relief')
    for first, rows, pg in records(t):
        s = merged(rows, sj) or place_text(merged(rows, wj))
        if not s or s.lower() in ('total', 'nil'):
            continue
        out.append({**base(t, pg), 'ward': ward_of(cell(first, wj)), 'area': place_text(cell(first, wj)), 'streets': s,
                    'persons': cell(first, pj), 'year': cell(first, yj), 'relief_centre': merged(rows, rj), 'needs_evacuation': needs})
    return out


def simple_places(t, kind):
    """tree falls, NDRF stations, parks: ward + name/location."""
    out = []
    wj = col(t, r'ward|div')
    nj = col(t, r'name of (the )?(park|play|street|part)|name|where|location|street|area', exclude=r'ward|officer|contact')
    lj = col(t, r'location of|address|location', exclude=r'ward')
    if lj == nj:
        lj = None
    for first, rows, pg in records(t):
        n = merged(rows, nj)
        if not n or n.lower() in ('total', 'nil') or re.fullmatch(r'[\d\s,./-]+', n):
            continue
        rec = {**base(t, pg), 'ward': ward_of(cell(first, wj)), 'name': n, 'location': merged(rows, lj)}
        txt = ' '.join(one_line(c) for r in rows for c in r if c)
        if kind in ('ndrf', 'boats'):
            rec['contact'] = txt if phones_in(txt) else ''
            rec['phones'] = phone_list(txt)
        out.append(rec)
    return out


def assembly_points(t):
    """§5.1.4 playground list: printed as two or three (Zone, Ward, Name) groups side by side."""
    out = []
    zs = [j for j, c in enumerate(t['columns']) if re.match(r'^zo', c, re.I)]
    groups = []
    for z in zs:
        w = next((j for j in range(z + 1, min(z + 3, len(t['columns']))) if re.search(r'ward', t['columns'][j], re.I)), None)
        n = next((j for j in range(z + 1, min(z + 4, len(t['columns']))) if re.search(r'play|ground|name|location', t['columns'][j], re.I)), None)
        if n is not None:
            groups.append((z, w, n))
    if not groups:
        return simple_places(t, 'parks')
    for r, pg in zip(t['rows'], t['row_pages']):
        for z, w, n in groups:
            name = cell(r, n)
            if name and not re.fullmatch(r'[\d\s,./-]+', name):
                out.append({**base(t, pg), 'zone': zone_val(cell(r, z)) or zone_of_ward(ward_of(cell(r, w))), 'ward': ward_of(cell(r, w)), 'name': name,
                            'location': ''})
    return out


def officials(t):
    """Any contact table: flatten rows that carry a phone number."""
    out = []
    gj = col(t, r'designation|officer|name|contact person', exclude=r'number|no\.$|phone|mobile')
    uj = col(t, r'unit|ward|area|zone|div')
    for r, pg in zip(t['rows'], t['row_pages']):
        txt = ' | '.join(one_line(c) for c in r if c)
        ph = phones_in(txt)
        if not ph:
            continue
        out.append({**base(t, pg), 'kind': t['kind'], 'table': (t.get('caption') or t['section'] or '')[:120],
                    'role': cell(r, gj), 'unit_or_wards': cell(r, uj), 'row_text': txt, 'phones': ';'.join(dict.fromkeys(ph))})
    return out


def generic(t):
    out = []
    for r, pg in zip(t['rows'], t['row_pages']):
        rec = {**base(t, pg), 'kind': t['kind'], 'caption': (t.get('caption') or '')[:120]}
        for j, c in enumerate(t['columns']):
            rec[c] = cell(r, j)
        out.append(rec)
    return out


# ----------------------------------------------------------------------------------- driver
def write(path, rows):
    if not rows:
        return 0
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(rows)
    return len(rows)


def compact(t):
    """Fold columns that only carry header text (rotated headers split over thin columns) into the
    neighbouring column that holds the data."""
    rows = t['rows']; cols = list(t['columns'])
    filled = [sum(1 for r in rows if j < len(r) and (r[j] or '').strip()) for j in range(len(cols))]
    keep = list(range(len(cols)))
    for j in range(len(cols)):
        if filled[j] == 0 and rows:
            nb = [k for k in (j + 1, j - 1) if 0 <= k < len(cols) and filled[k] > 0]
            if nb:
                k = nb[0]
                cols[k] = (cols[j] + ' ' + cols[k]) if k > j else (cols[k] + ' ' + cols[j])
            keep.remove(j)
    # a header repeated at the top of the first data cells: 'Name of the department\nGCC-Engineering'
    head = t['header'][-1] if t.get('header') else []
    rows = [list(r) for r in rows]
    for r in rows[:2]:
        for j, v in enumerate(r):
            h = (head[j] if j < len(head) else '') or ''
            if v and h and v.startswith(h + '\n'):
                r[j] = v[len(h) + 1:]
    t = dict(t)
    cols = [cols[j] for j in keep]
    pre = os.path.commonprefix(cols)
    if len(cols) > 2 and ' / ' in pre:           # a table title printed above every column
        cut = pre.rfind(' / ') + 3
        cols = [c[cut:] or c for c in cols]
    t['columns'] = cols
    t['rows'] = [[r[j] if j < len(r) else None for j in keep] for r in rows]
    return t


def inherit_headers(tables):
    """A table continued on the next page sometimes comes back as its own table with no header
    (col1, col2...). Give it the columns of the table before it when the shape matches."""
    prev = None
    for t in tables:
        if prev and all(re.fullmatch(r'col\d+', c) for c in t['columns']) and len(t['columns']) == len(prev['columns']) \
                and t['pages'][0] - prev['pages'][-1] <= 1:
            t['columns'] = list(prev['columns'])
            if t['kind'] in ('other', 'contacts'):
                t['kind'] = prev['kind']
        if not all(re.fullmatch(r'col\d+', c) for c in t['columns']):
            prev = t
        elif prev and len(t['columns']) == len(prev['columns']):
            prev = t if False else prev
    return tables


def build_datasets(tables, text_phones, pages, out):
    os.makedirs(out, exist_ok=True)
    tables = inherit_headers([compact(t) for t in tables])
    for fn in os.listdir(out):
        os.remove(f'{out}/{fn}')
    D = defaultdict(list)
    councillors = defaultdict(dict)
    for t in tables:
        if t['kind'] == 'ward_committee' and not t.get('ward_heading'):
            m = WARD_HEAD.match(one_line(t['title'] or ''))
            if m and 1 <= int(m.group(1)) <= 200:
                t['ward_heading'] = int(m.group(1))
    for t in tables:
        k = t['kind']
        # councillor line printed above each ward table: "Ward councillor – 98xxxxxxx"
        if k == 'ward_committee' and t.get('ward_heading'):
            m = re.search(r'councill?or\s*[–-]?\s*([^|]*)', t['title'] or '', re.I)
            if m:
                c = councillors[t['ward_heading']]
                c['phones'] = phones_in(m.group(1)); c['as_printed'] = one_line(m.group(1))[:40]
                c['pdf_page'] = t['pages'][0]
        if k == 'ward_committee':
            D['ward_contacts'] += ward_committee(t, councillors)
        elif k == 'inundation_history':
            D['inundation_history'] += inundation_history(t)
        elif k == 'inundation_streets':
            D['inundation_streets'] += inundation_streets(t)
        elif k == 'water_stagnation':
            D['water_stagnation'] += water_stagnation(t)
        elif k == 'relief_centres':
            D['relief_centres'] += relief_centres(t)
        elif k == 'subways':
            D['subways'] += subways(t)
        elif k == 'evacuation_streets':
            D['evacuation_streets'] += evacuation(t, True)
        elif k == 'water_entered_houses':
            D['evacuation_streets'] += evacuation(t, False)
        elif k in ('tree_fall', 'ndrf', 'boats', 'parks'):
            D[k] += simple_places(t, k)
        elif k == 'assembly_points':
            D['assembly_points'] += assembly_points(t)
        elif k in ('pumping_stations', 'water_bodies', 'storm_water_drains', 'tenements', 'narrow_lanes', 'vehicles', 'population'):
            D[k] += generic(t)
        if k in ('contacts', 'lighting', 'health_facilities', 'ndrf', 'boats', 'tenements', 'relief_centres', 'vehicles', 'pumping_stations'):
            D['officials'] += officials(t)
    D['ward_councillors'] = [{'ward': w, 'zone': zone_of_ward(w), 'name': c.get('name', ''), 'as_printed': c.get('as_printed', ''),
                              'phones': ';'.join(c.get('phones', [])), 'pdf_page': c.get('pdf_page')} for w, c in sorted(councillors.items()) if w]
    return {name: write(f'{out}/{name}.csv', rows) for name, rows in sorted(D.items())}
