"""CDMP §4.2 inundation tables (PDF pp. 58-111) -> data/inundation_points.json
Each row: zone, ward, location, depth class (column holding 'Yes'), year of the table it came from."""
import re, json, pdfplumber
ROM = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
       'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15}
CLS = ['very_high', 'high', 'medium', 'low']
pdf = pdfplumber.open('raw/cdmp_2024-compressed.pdf')
rows, year, titles = [], None, []
for pn in range(58, 112):
    pg = pdf.pages[pn - 1]
    text = pg.extract_text() or ''
    tables = pg.find_tables()
    # title lines on this page, with their y, to date each table
    marks = []
    for ln in pg.extract_text_lines():
        m = re.search(r'(Inundation|Monsoon|Flood|Vulnerab).*?\b(20\d\d)\b', ln['text'], re.I)
        if m and len(ln['text']) < 140:
            marks.append((ln['top'], int(m.group(2)), ln['text']))
    for tb in tables:
        data = tb.extract()
        for r in data:
            if r and r[0] and re.search(r'Monsoon\s*-?\s*(20\d\d)', r[0] or ''):
                marks.append((tb.bbox[1] - 1, int(re.search(r'(20\d\d)', r[0]).group(1)), r[0]))
        above = [m for m in sorted(marks) if m[0] <= tb.bbox[1] + 2]
        if above:
            year = above[-1][1]; titles.append((pn, year, above[-1][2][:80]))
        if pn in (108, 109):
            year = 2022     # detail table after the 2022 summary (p107) is mis-titled '-2021' in the source
        for r in data:
            r = [(c or '').strip() for c in r]
            if pn == 110 and len(r) == 4 and re.fullmatch(r'\d+', r[0]) and r[1].isdigit() and r[2].isdigit():   # 2023: S.No, Zone, Division, Location
                rows.append({'page': pn, 'year': 2023, 'sno': int(r[0]), 'zone': int(r[1]), 'ward': int(r[2]),
                             'location': ' '.join(r[3].split()), 'class': None, 'status': None})
                continue
            if len(r) < 8 or not re.fullmatch(r'\d+', r[0]):
                continue
            z = r[1].replace(' ', '').upper()
            zone = ROM.get(z) or (int(z) if z.isdigit() else None)
            ward = r[2]
            loc = ' '.join(r[3].replace('-\n', '').split())
            yes = [i for i in range(4) if r[4 + i].lower().startswith('yes')]
            if not loc or zone is None:
                continue
            rows.append({'page': pn, 'year': year, 'sno': int(r[0]), 'zone': zone,
                         'ward': int(ward) if ward.isdigit() else ward, 'location': loc,
                         'class': CLS[yes[0]] if yes else None,
                         'status': r[8] if len(r) > 8 and r[8] else None})
json.dump(rows, open('data/inundation_rows.json', 'w'), indent=0, ensure_ascii=False)
import collections
print(len(rows), sorted(collections.Counter((r['year'], r['page']) for r in rows).items()))
print(collections.Counter(r['class'] for r in rows))
seen = set()
for t in titles:
    if t[1:] not in seen: seen.add(t[1:]); print(t)
