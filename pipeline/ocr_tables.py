"""OCR the screenshot tables cell by cell.

Finds the ruled grid (long horizontal / vertical lines), crops each cell,
upscales it and runs tesseract on it. Writes build/ocr/<img>.json:
  {"cols": [x0..xn], "rows": [[cell text, ...], ...]}
These are a first pass only; every row is checked by eye against the image
(see transcribe notes in data/*.csv).
"""
import json, subprocess, sys, os, tempfile
from concurrent.futures import ThreadPoolExecutor
import cv2, numpy as np

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'pump_lists', 'ocr')
os.makedirs(OUT, exist_ok=True)


def lines(mask, axis, min_frac):
    """Positions of ruled lines: rows/cols whose dark-pixel run covers min_frac."""
    prof = mask.sum(axis=axis) / 255
    n = mask.shape[axis]
    idx = np.where(prof > min_frac * n)[0]
    out = []
    for i in idx:
        if out and i - out[-1][-1] <= 2:
            out[-1].append(i)
        else:
            out.append([i])
    return [int(np.mean(g)) for g in out]


def grid(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bw = cv2.threshold(g, 160, 255, cv2.THRESH_BINARY_INV)[1]
    h = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (120, 1)))
    v = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 60)))
    ys = lines(h, 1, 0.45)
    xs = lines(v, 0, 0.30)
    return xs, ys


def ocr(cell, psm):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        cv2.imwrite(f.name, cell)
        r = subprocess.run(['tesseract', f.name, '-', '--psm', str(psm), '-l', 'eng'],
                           capture_output=True, text=True)
    os.unlink(f.name)
    return ' '.join(r.stdout.split())


def run(path):
    img = cv2.imread(path)
    xs, ys = grid(img)
    jobs = []
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            y0, y1, x0, x1 = ys[r] + 3, ys[r + 1] - 2, xs[c] + 3, xs[c + 1] - 2
            if y1 - y0 < 8 or x1 - x0 < 8:
                continue
            cell = img[y0:y1, x0:x1]
            cell = cv2.resize(cell, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            cell = cv2.copyMakeBorder(cell, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=(255, 255, 255))
            jobs.append((r, c, cell))
    with ThreadPoolExecutor(8) as ex:
        texts = list(ex.map(lambda j: ocr(j[2], 7), jobs))
    rows = {}
    for (r, c, _), t in zip(jobs, texts):
        rows.setdefault(r, {})[c] = t
    table = [[rows[r].get(c, '') for c in range(len(xs) - 1)] for r in sorted(rows)]
    name = os.path.splitext(os.path.basename(path))[0]
    json.dump({'cols': xs, 'rows_y': ys, 'rows': table}, open(f'{OUT}/{name}.json', 'w'), indent=0)
    print(name, len(xs) - 1, 'cols', len(table), 'rows')


if __name__ == '__main__':
    for p in sys.argv[1:]:
        run(p)
