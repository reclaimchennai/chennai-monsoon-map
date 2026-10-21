"""Tractor-pump list (raw/11-20 screenshots) -> data/tractor_pumps.csv.
OCR cells (build/ocr) + plate/phone normalisation + manual fixes read off the images."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import json, re, csv
FIX = {  # sno: {field: value}  -- read by eye from the screenshot
    1: {'location': 'JJ Nagar'},
    15: {'driver': 'VENKATESAN KRISHNA'},   # cell clipped in the source
    16: {'driver': 'KUPPURAJ'},
    11: {'location': 'Ennore Express Road (Tuna Fishing Harbour)'},
    141: {'tractor': 'TN 15 L 1373'}, 143: {'tractor': 'TN 32 AJ 9808'},
    307: {'driver': 'KRISHANAN MOORTHY'}, 308: {'tractor': 'TN 31 J 8215'},
    315: {'tractor': 'TN 19 Y 5437'}, 499: {'tractor': 'TN 31 J 7413'},
    437: {'tractor': 'TN 15 B 5844'}, 459: {'tractor': 'TN 32 BM 5042'},
    358: {'driver': 'VIJI'}, 363: {'tractor': 'TN 16 C 2819'},
    376: {'tractor': 'TN 25 PW 5352'}, 381: {'driver': 'VIJAYAN'}, 383: {'tractor': 'TN 55 AZ 2261'},
    385: {'tractor': 'TN 51 T 4579'}, 391: {'tractor': 'TN 31 BM 4768'}, 394: {'tractor': 'TN 46 J 9949'},
    400: {'driver': 'DHASHNAMORRTY'}, 403: {'tractor': 'TN 25 8196'}, 404: {'location': 'LAKSHMINAGAR 5TH STREET'},
    406: {'tractor': 'TN 73 Z 0075'}, 407: {'driver': 'DHASANAMOORTHY'}, 408: {'location': 'DEVI KARUMARIYAMMAN NAGAR 1ST STREET'},
    411: {'tractor': 'TN 51 A 4637'}, 414: {'tractor': 'TN 25 AA 0640'}, 417: {'tractor': 'TN 32 BD 9142'},
    418: {'tractor': 'TN 16 Z 0003', 'driver': 'VIJAYARAJ'}, 420: {'driver': 'VIJAY'},
    456: {'tractor': 'TN 15 9513'}, 460: {'driver': 'SIVARAJ'}, 365: {'tractor': 'TN 65 Z 0239'}, 367: {'tractor': 'TN 32 Q 4295'},
    373: {'tractor': 'TN 50 AY 3360'}, 428: {'tractor': 'TN 32 AT 5368'}, 495: {'zone': 15}, 422: {'div': 179}, 506: {'tractor': 'TN 25 6203'},
}
DIV_FIX = {335: 143, 336: 143, 337: 143, 338: 144, 339: 145, 340: 145, 341: 145, 342: 145, 343: 145, 344: 146,
           345: 147, 346: 148, 347: 151, 348: 153, 349: 154, 350: 155, 351: 150, 352: 153, 353: 150, 354: 151,
           355: 154, 356: 155, 357: 156, 358: 156, 359: 156, 360: 157, 361: 158, 362: 160, 363: 160, 364: 160,
           365: 161, 366: 161, 367: 162, 368: 162, 369: 163, 370: 164, 371: 164, 372: 168, 373: 168, 374: 169}
ZONE_FIX = {335: 11, 336: 11, 337: 11, 338: 11, 339: 11, 340: 11, 342: 11, 346: 11, 347: 11, 350: 11,
            352: 11, 354: 11, 355: 11, 356: 11, 434: 14, 450: 14, 453: 14, 455: 14}
# GCC 15-zone division (ward) ranges
ZR = [(1, 14), (15, 22), (23, 33), (34, 48), (49, 63), (64, 78), (79, 93), (94, 108), (109, 126),
      (127, 142), (143, 155), (156, 167), (168, 180), (181, 191), (192, 200)]
zone_of = lambda w: next(i + 1 for i, (a, b) in enumerate(ZR) if a <= w <= b)


def plate(s):
    s = s.upper().replace('™', 'T').replace('€', 'C').replace('¥', 'Y').replace('$', '5')
    m = re.match(r'^\s*(TN|PY|AP)\s*(\d\d)\s*(.*?)\s*(\d{4})\s*$', s)
    if not m:
        return s.strip(), False
    st, rto, ser, num = m.groups()
    ser = ser.replace(' ', '').replace(')', 'J').replace('3', 'J').replace('8', 'B').replace('0', 'D')
    return ' '.join(x for x in (st, rto, ser, num) if x), bool(re.fullmatch(r'[A-Z]{0,2}', ser))


def phones(s):
    out = []
    for p in re.split(r'/', s):
        d = re.sub(r'\D', '', p)
        if d:
            out.append(d)
    return out


rows = []
for n in range(11, 21):
    for r in json.load(open(f'{ROOT}/data/pump_lists/ocr/{n}.json'))['rows']:
        if not r[0].isdigit():
            continue
        sno = int(r[0])
        rec = dict(sno=sno, tractor=r[1], driver=r[2].replace('VUAY', 'VIJAY').replace(')', 'J'),
                   phone=r[3], location=r[4], zone=r[5], div=r[6])
        rec.update(FIX.get(sno, {}))
        rec['tractor'], ok = plate(rec['tractor'])
        rec['div'] = DIV_FIX.get(sno, rec['div'])
        rec['zone'] = ZONE_FIX.get(sno, rec['zone'])
        rec['div'] = int(rec['div']); rec['zone'] = int(rec['zone'])
        ph = phones(rec['phone'])
        rec['phones'] = ' / '.join(ph)
        notes = []
        bad = [p for p in ph if not re.fullmatch(r'[6-9]\d{9}', p)]
        if bad:
            notes.append('number as printed is not a valid 10-digit mobile: ' + ', '.join(bad))
        if zone_of(rec['div']) != rec['zone']:
            notes.append(f'division {rec["div"]} is not in zone {rec["zone"]} (as printed)')
        if not ok:
            notes.append('plate as printed')
        rec['note'] = '; '.join(notes)
        rec['location'] = re.sub(r'RA[I!]\b', 'RAJ', ' '.join(rec['location'].split()))
        rec['driver'] = re.sub(r'RA[I!]\b', 'RAJ', rec['driver'])
        rows.append(rec)
rows.sort(key=lambda r: r['sno'])
F = ['sno', 'tractor', 'driver', 'phones', 'location', 'zone', 'div', 'note']
with open(f'{ROOT}/data/pump_lists/tractor_pumps.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, F, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
print(len(rows), 'rows; missing:', sorted(set(range(1, 511)) - {r['sno'] for r in rows})[:3], '...')
for a, b in zip(rows, rows[1:]):
    if b['div'] < a['div'] and b['zone'] == a['zone']:
        print('non-monotonic', a['sno'], a['div'], '->', b['sno'], b['div'])
for r in rows:
    if r['note']:
        print(r['sno'], r['tractor'], r['phones'], r['zone'], r['div'], '|', r['note'])
