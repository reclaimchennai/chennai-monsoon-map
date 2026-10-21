"""Second, independent OCR of the mobile-number column (different scale, binarised,
digit whitelist) to catch digit misreads in the first pass."""
import json, subprocess, tempfile, os, re, csv, sys
import cv2
from concurrent.futures import ThreadPoolExecutor
def ocr(cell):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        cv2.imwrite(f.name, cell)
        r = subprocess.run(['tesseract', f.name, '-', '--psm', '7', '-c', 'tessedit_char_whitelist=0123456789/ '],
                           capture_output=True, text=True)
    os.unlink(f.name); return re.sub(r'[^0-9/]', '', r.stdout)
jobs = []
for n in range(11, 21):
    d = json.load(open(f'build/ocr/{n}.json')); im = cv2.imread(f'raw/{n}.webp'); xs, ys = d['cols'], d['rows_y']
    for i, r in enumerate(d['rows']):
        if not r[0].isdigit(): continue
        c = im[ys[i] + 3:ys[i + 1] - 2, xs[3] + 3:xs[4] - 2]
        g = cv2.cvtColor(cv2.resize(c, None, fx=4.5, fy=4.5, interpolation=cv2.INTER_LANCZOS4), cv2.COLOR_BGR2GRAY)
        g = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        g = cv2.copyMakeBorder(g, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
        jobs.append((int(r[0]), g))
with ThreadPoolExecutor(8) as ex:
    res = dict(zip([j[0] for j in jobs], ex.map(lambda j: ocr(j[1]), jobs)))
bad = 0
for row in csv.DictReader(open('data/tractor_pumps.csv')):
    a = row['phones'].replace(' ', ''); b = res[int(row['sno'])]
    if a != b:
        bad += 1; print(row['sno'], a, '| second pass:', b)
print('disagreements', bad, 'of', len(res))
