"""Diesel / RP pump list (raw/21-25 screenshots) -> data/diesel_pumps.csv."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import json, re, csv
LOC = {  # read by eye where the OCR garbled multi-line cells
    18: 'KADUMBADI AMMAN KOIL ST', 39: 'IYYA SAMMY ST',
    90: 'Thiruvalluvar Salai Jn of Arumuga Nayaknar street',
    91: 'Rayala Nagar 1st Main Road Jn of 3rd Cross St',
    95: 'VGN Lakshmi Nagar Kaveri street TVS Emrolled',
    109: '(100 HP) River view road TNUHDB tenements',
    115: '(100 HP) Kalki nagar (AGS Colony 4th Cross Street)',
    117: '(100 HP) Ram nagar 6th main road North Extn',
    121: '(100 HP) MRTS Road Jn of VGP Selva Nagar 2nd Main Road',
    137: 'Rajiv Gandhi Salai (OMR) in front of Olympia Bui[lding]',
    144: 'The Chennai Mobiles (OMR Service Road), Cosmos marble Shop, Karapakkam',
}
ZR = [(1, 14), (15, 22), (23, 33), (34, 48), (49, 63), (64, 78), (79, 93), (94, 108), (109, 126),
      (127, 142), (143, 155), (156, 167), (168, 180), (181, 191), (192, 200)]
zone_of = lambda w: next(i + 1 for i, (a, b) in enumerate(ZR) if a <= w <= b)
rows = []
for n, ext in [(21, 'png'), (22, 'png'), (23, 'webp'), (24, 'webp'), (25, 'png')]:
    for r in json.load(open(f'{ROOT}/data/pump_lists/ocr/{n}.json'))['rows']:
        if not r[0].isdigit():
            continue
        sno = int(r[0])
        loc = LOC.get(sno, ' '.join(r[4].split()))
        loc = re.sub(r'\bIst\b', '1st', re.sub(r'\bSth\b', '5th', loc))
        hp = '100 HP' if '100 HP' in loc else ''
        loc = loc.replace('(100 HP)', '').strip()
        divs = [int(x) for x in re.findall(r'\d+', r[2])]
        zone = zone_of(divs[0])
        note = []
        if sno == 28: note.append('date printed as 18-Oct-28')
        if sno == 145: note.append('stretch across divisions 198 to 182')
        if '2 Nos' in loc: note.append('2 pumps')
        date = r[6]
        m = re.search(r'(\d{1,2})[.-](\w{2,3})[.-](\d{2,4})', date)
        if m:
            d, mo, y = m.groups()
            mo = {'Oct': 10, 'Nov': 11, 'Sep': 9}.get(mo, mo)
            date = f'2026-{int(mo):02d}-{int(d):02d}'
        rows.append(dict(sno=sno, zone=zone, div=divs[0], pump_no=r[3].strip() if r[3].strip() != 'RP-' else '',
                         kind='DL' if r[3].startswith('DL') else 'RP', location=loc, hp=hp, placed=date,
                         operating='operating' in r[6].lower(), note='; '.join(note)))
F = list(rows[0])
with open(f'{ROOT}/data/pump_lists/diesel_pumps.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, F); w.writeheader(); w.writerows(rows)
print(len(rows))
for r in rows: print(r['sno'], r['zone'], r['div'], r['pump_no'], r['location'], r['hp'], r['placed'], r['note'])
