"""Ward committee contacts (CDMP appendix, all zones) -> data/ward_contacts.json
Tables via pdfplumber (ruled cells), each tied to the nearest 'Ward committee – N' heading above it.
{ward: {"councillor": [phones], "councillor_name": str|None, "contacts": [{dept, designation, phones:[...], raw}], "page": n}}"""
import re, json
import pdfplumber

PH = re.compile(r'(?:\b(?:044|0?44)[\s-]?\d{8}\b|\b[6-9]\d{9}\b)')


def phones(cell):
    """Phone numbers in a cell, as printed. Keeps short labels ('ICF-', 'V1-'); expands '9445026046/6043';
    8-digit Chennai landlines get 044. Anything else that looks like a number is kept with bad=True."""
    out, label = [], ''
    pieces = [p.strip() for p in re.split(r'[\n,/]+|(?<=\d{10})\s+(?=\d)|(?<=\d{8})\s+(?=\d{8})', cell or '') if p.strip()]
    merged = []
    for p in pieces:          # a number wrapped over two lines: '94' + '45850224'
        if merged and re.fullmatch(r'\d+', p) and re.fullmatch(r'\d+', merged[-1]) and len(merged[-1] + p) == 10 and len(p) < 10:
            merged[-1] += p
        else:
            merged.append(p)
    for piece in merged:
        lm = re.match(r'^([A-Z]{1,3}\d{0,2})\s*[-–]\s*(?=\d)', piece) or re.search(r'(?<=\d)\s*[-–]\s*([A-Z]{1,3}\d{0,2})$', piece)
        if lm:
            label = lm.group(1); piece = (piece[:lm.start()] + piece[lm.end():]).strip()
        m = re.search(r'\d[\d\s–-]{2,}\d', piece)
        if not m:
            if re.search(r'[A-Za-z]', piece):
                label = piece.strip(' -:–')
            continue
        d = re.sub(r'\D', '', m.group(0))
        lab = (label + ' ' + piece[:m.start()].strip(' -:–')).strip(); label = ''
        if len(d) == 10 and d[0] in '6789':
            n, bad = d, False
        elif len(d) in (10, 11) and d.lstrip('0').startswith('44') and len(d.lstrip('0')) == 10:
            n, bad = '044' + d[-8:], False
        elif len(d) == 8 and d[0] == '2':
            n, bad = '044' + d, False
        elif len(d) == 4 and out and len(out[-1]['n']) == 10:
            n, bad = out[-1]['n'][:6] + d, False
        else:
            n, bad = d, True
        out.append({'n': n, 'label': lab, **({'bad': True} if bad else {})})
    return out


pdf = pdfplumber.open('raw/cdmp_2024-compressed.pdf')
wards = {}
for pn in range(192, 807):
    pg = pdf.pages[pn - 1]
    txt = pg.extract_text() or ''
    if not re.search(r'Ward\s+[Cc]ommittee\s*[–-]\s*\d', txt):
        continue
    heads = []
    for h in pg.search(r'Ward\s+[Cc]ommittee\s*[–-]\s*\d+'):
        n = int(re.search(r'\d+$', h['text']).group())
        # councillor on the same line or the next
        line = [w for w in pg.extract_words() if abs(w['top'] - h['top']) < 3 or 0 < w['top'] - h['top'] < 22]
        cl = ' '.join(w['text'] for w in sorted(line, key=lambda w: (round(w['top']), w['x0'])))
        m = re.search(r'Councill?or\s*[–-]?\s*(\d{10})', cl, re.I)
        heads.append((h['top'], n, m.group(1) if m else None))
    for tb in pg.find_tables():
        rows = tb.extract()
        if not rows or not rows[0] or not (rows[0][0] or '').lower().startswith('name of the'):
            continue
        tops = [rw.bbox[1] for rw in tb.rows]
        w = None
        for r, top in zip(rows[1:], tops[1:]):
            above = [h for h in heads if h[0] < top]
            if not above:
                continue
            _, n, cphone = above[-1]
            if n > 200 and cphone and cphone.startswith('9445467'):
                n = int(cphone[-3:])      # source typo: 'Ward Committee – 311' for ward 44 etc.
            w = wards.setdefault(n, {'councillor': [cphone] if cphone else [], 'councillor_name': None, 'contacts': [], 'page': pn})
            r = [(c or '').strip() for c in r] + ['', '', '']
            dept, des, num = r[0], r[1], r[2]
            mh = re.match(r'Ward\s+[Cc]ommittee\s*[–-]\s*(\d+)', dept)
            if mh:                       # two wards' tables drawn as one
                n = int(mh.group(1))
                w = wards.setdefault(n, {'councillor': [], 'councillor_name': None, 'contacts': [], 'page': pn})
                continue
            if dept.startswith('Name of the department') or re.match(r'^(Zone\s*-\s*\d+\s+\d+|\d+\s+Zone\s*-\s*\d+)$', dept):
                continue
            des = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', ' '.join(des.split()))
            ph = phones(num)
            if 'councillor' in des.lower():
                w['councillor_name'] = dept or None
                for p in ph:
                    if p['n'] not in w['councillor']: w['councillor'].append(p['n'])
                continue
            if not (dept or des or ph) or (not ph and not des):
                continue
            if not dept and w['contacts']:  # continuation row: extra numbers for the row above
                w['contacts'][-1]['phones'] += ph; w['contacts'][-1]['raw'] += '\n' + num
                continue
            w['contacts'].append({'dept': ' '.join(dept.split()), 'designation': des, 'phones': ph, 'raw': num})
print(len(wards), 'wards; missing', [w for w in range(1, 201) if w not in wards], 'extra', [w for w in wards if w > 200])
import collections
print(collections.Counter(len(v['contacts']) for v in wards.values()))
print('no councillor', [w for w, v in wards.items() if not v['councillor']])
for n, v in wards.items():
    if not v['councillor']: v['councillor'] = ['9445467%03d' % n]; v['councillor_formula'] = True
print('contacts without phone', sum(1 for v in wards.values() for c in v['contacts'] if not c['phones']))
for v in list(wards.values())[:0]: pass

json.dump(dict(sorted(wards.items())), open('data/ward_contacts.json', 'w'), indent=1, ensure_ascii=False)
