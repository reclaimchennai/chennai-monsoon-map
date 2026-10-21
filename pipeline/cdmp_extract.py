#!/usr/bin/env python3
"""
cdmp_extract.py: extract every table in a Greater Chennai Corporation
City Disaster Management Plan (CDMP) PDF, in document order, plus the
monsoon-relevant datasets built from them.

    python pipeline/cdmp_extract.py raw/cdmp/cdmp_2026.pdf --out data/cdmp/2026

Nothing in here is tied to page numbers of one edition. Pages are located by
what is printed on them: the running footer ("Zone - 7   452") gives the zone
and printed page, 16 pt headings give the section, and each table is classified
by its own title and column headers. A new edition of the plan should therefore
run unchanged. Check `audit.json` afterwards: it lists any phone number printed
in the PDF that did not make it into the output, and any table that could not
be classified.

Outputs (in --out):
  pages.csv              one row per PDF page: printed page, zone, heading
  tables.jsonl           one JSON object per table, in reading order, with the
                         full cell grid, header, title, section, zone, kind
  tables/NNNN_*.csv      the same tables as CSV (header row first)
  text_phones.csv        phone numbers printed outside tables (e.g. "Ward councillor – …")
  datasets/*.csv         normalised, monsoon-relevant datasets (see KINDS below)
  audit.json             completeness checks
"""
import argparse, csv, json, os, re, statistics, sys
from collections import Counter, defaultdict

import pdfplumber

# --------------------------------------------------------------------------------------------- text utils
PHONE = re.compile(r'(?<![\d])(?:0?44[\s.-]*\d{8}|0\d{3,4}[\s-]+\d{6,8}'
                   r'|[6-9]\d{4}[\s-]?\d{5}|[6-9]\d{2}[\s-]\d{3}[\s-]\d{4}|[6-9]\d{3}[\s-]\d{3}[\s-]\d{3}|[6-9]\d{2}[\s-]\d{7}|[6-9]\d{3}[\s-]\d{6})(?![\d])')
# mobile numbers as printed: 98410 12345 / 984-101-2345 / 9841 012 345 / 984 1012345 / 9841 012345
ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
         'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15}
LIGATURES = {'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl', '’': "'", '‘': "'",
             '“': '"', '”': '"', ' ': ' '}


def clean(s):
    if s is None:
        return ''
    for a, b in LIGATURES.items():
        s = s.replace(a, b)
    # words from fonts with a private encoding come out as 'rÇ~ó~ã=å~Ö~ê': drop such tokens
    if '~' in s or '=' in s:
        s = re.sub(r'\S*[~=]\S*', lambda m: '' if re.search(r'[^\x00-\x7f]', m.group(0)) or m.group(0).count('~') + m.group(0).count('=') >= 2 else m.group(0), s)
    return s.strip()


def one_line(s):
    """Join a wrapped cell into one line, re-joining words hyphenated at the wrap ('Radakrish-\\nnan')."""
    s = clean(s)
    s = re.sub(r'(\w)-\n(\w)', r'\1\2', s)
    return ' '.join(s.split())


def phones_in(s):
    """All phone numbers in a string, digits only (landlines keep their STD code)."""
    out = []
    for m in PHONE.finditer(clean(s).replace('\n', ' ')):
        d = re.sub(r'\D', '', m.group(0))
        if len(d) == 10 and d[0] in '6789':
            out.append(d)
        elif d.startswith('44') and len(d) == 10:
            out.append('0' + d)
        elif d.startswith('0'):
            out.append(d)
    return out


def slug(s, n=48):
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')[:n] or 'table'


# --------------------------------------------------------------------------------------------- page reading
def cell_text(page_chars, bbox, page=None):
    """Text of one cell. Upright text in reading order; text rotated 90 degrees (vertical column
    headers on landscape tables) is read bottom-to-top, columns left to right."""
    x0, top, x1, bottom = bbox
    cs = [c for c in page_chars if x0 - 0.5 <= (c['x0'] + c['x1']) / 2 <= x1 + 0.5 and top - 0.5 <= (c['top'] + c['bottom']) / 2 <= bottom + 0.5]
    if not cs:
        return ''
    up = [c for c in cs if c.get('upright', True)]
    rot = [c for c in cs if not c.get('upright', True)]
    parts = []
    if up:
        if page is not None:
            crop = page.crop((max(bbox[0], 0), max(bbox[1], 0), min(bbox[2], page.width), min(bbox[3], page.height)), strict=False)
            crop = crop.filter(lambda o: o.get('object_type') != 'char' or o.get('upright', True))
            parts.append(crop.extract_text(x_tolerance=1.5, y_tolerance=3) or '')
        else:
            parts.append(_lines(up, key_line=lambda c: c['top'], key_char=lambda c: c['x0'], size=lambda c: c['size']))
    if rot:
        # matrix (0, s, -s, 0): baseline runs bottom->top; lines advance left->right
        ccw = statistics.mean(c['matrix'][1] for c in rot) > 0
        parts.append(_lines(rot, key_line=(lambda c: c['x0']) if ccw else (lambda c: -c['x1']),
                            key_char=(lambda c: -c['bottom']) if ccw else (lambda c: c['top']), size=lambda c: c['size'], vertical=True))
    return clean('\n'.join(p for p in parts if p))


def _lines(chars, key_line, key_char, size, vertical=False):
    """Group chars into lines along key_line, order each line by key_char, insert spaces at gaps."""
    chars = sorted(chars, key=key_line)
    lines, cur, mean = [], [], None
    for c in chars:
        k = key_line(c)
        if mean is not None and abs(k - mean) > size(c) * 0.55:
            lines.append(cur); cur = []
        cur.append(c)
        mean = sum(key_line(x) for x in cur) / len(cur)
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln = sorted(ln, key=key_char)
        s, prev = '', None
        for c in ln:
            if prev is not None:
                if vertical:  # extent along the baseline is the char's top..bottom
                    gap = max(prev['top'] - c['bottom'], c['top'] - prev['bottom'])
                else:
                    gap = c['x0'] - prev['x1']
                if gap > size(c) * (0.12 if vertical else 0.22):
                    s += ' '
            s += c['text']; prev = c
        out.append(s)
    return '\n'.join(out)


def page_lines(page):
    """Upright text lines with font size and whether they are bold."""
    out = []
    for l in page.extract_text_lines(return_chars=True, strip=True):
        cs = [c for c in l['chars'] if c.get('upright', True)]
        if not cs:
            continue
        size = statistics.median(c['size'] for c in cs)
        font = Counter(c['fontname'].split('+')[-1] for c in cs).most_common(1)[0][0]
        out.append({'text': clean(l['text']), 'top': l['top'], 'bottom': l['bottom'], 'x0': l['x0'], 'x1': l['x1'], 'size': size, 'font': font})
    return out


FOOTER_ZONE = [re.compile(r'^Zone\s*[-–]\s*(\d{1,2})\s+(\d{1,4})$', re.I), re.compile(r'^(\d{1,4})\s+Zone\s*[-–]\s*(\d{1,2})$', re.I)]


def footer(lines, height):
    """(zone, printed page) from the running footer, e.g. 'Zone - 7   452' / '452   Zone - 7'. The footer
    text is sometimes fused with other numbers ('128095 Zone - 1'), so the zone is searched anywhere in
    the bottom lines and the printed page only taken when it stands alone."""
    zone = printed = None
    for l in lines:
        if l['top'] < height - 90:
            continue
        t = ' '.join(l['text'].split())
        m = re.search(r'Zone\s*[-–]\s*(\d{1,2})\b', t, re.I)
        if m and 1 <= int(m.group(1)) <= 15:
            zone = int(m.group(1))
            rest = (t[:m.start()] + ' ' + t[m.end():]).split()
            if len(rest) == 1 and re.fullmatch(r'\d{1,3}', rest[0]):
                printed = rest[0]
        elif re.fullmatch(r'\d{1,3}|[ivxlc]{1,7}', t, re.I):
            printed = t
    return zone, printed


# --------------------------------------------------------------------------------------------- tables
TABLE_SETTINGS = {'vertical_strategy': 'lines', 'horizontal_strategy': 'lines', 'snap_tolerance': 3, 'join_tolerance': 3,
                  'intersection_tolerance': 3}


def grid(page, tb, chars):
    """Cell grid of a pdfplumber table, plus each column's x-range. Cells covered by a merged
    neighbour come back as None. Rows printed without horizontal rules (one cell holding a whole
    column, '1\n2\n3') are split back into rows using the text lines' positions."""
    rows, boxes = [], []
    for r in tb.rows:
        rows.append([None if c is None else cell_text(chars, c, page) for c in r.cells])
        boxes.append(r)
    ncol = max(len(r) for r in rows)
    rows = [r + [None] * (ncol - len(r)) for r in rows]
    xs = [[None, None] for _ in range(ncol)]
    for r in tb.rows:
        for j, c in enumerate(r.cells):
            if c is not None:
                xs[j][0] = c[0] if xs[j][0] is None else min(xs[j][0], c[0]); xs[j][1] = c[2] if xs[j][1] is None else max(xs[j][1], c[2])
    out_rows = []
    for r, br in zip(rows, boxes):
        first = next((k for k, c in enumerate(r) if (c or '').strip()), None)
        lines = (r[first] or '').split('\n') if first is not None else []
        nsno = sum(bool(SNO.match(x)) for x in lines)
        header_plus_data = len(lines) >= 2 and not SNO.match(lines[0]) and nsno >= 1 and all(SNO.match(x) for x in lines[1:] if x.strip()) and nsno == len(lines) - 1
        if first is not None and (len(lines) >= 3 and nsno >= max(2, len(lines) - 1) or header_plus_data):
            out_rows += explode(page, br, xs, first)
        else:
            out_rows.append(r)
    keep = [j for j in range(ncol) if any((r[j] or '').strip() for r in out_rows)]
    return [[r[j] for j in keep] for r in out_rows], [xs[j] for j in keep]


def explode(page, row, xs, sno_col):
    """Split one ruled row that holds many unruled rows. Anchors = the serial numbers' text lines."""
    x0, top, x1, bottom = row.bbox
    words = page.crop((x0, top, x1, bottom), strict=False).extract_words(x_tolerance=1.5, y_tolerance=3, keep_blank_chars=False)
    sx0, sx1 = xs[sno_col]
    anchors = sorted({round(w['top'], 1) for w in words if sx0 - 1 <= w['x0'] and w['x1'] <= sx1 + 1 and SNO.match(w['text'])})
    if not anchors:
        return [[None] * len(xs)]
    sub = [[[] for _ in xs] for _ in range(len(anchors) + 1)]       # sub[0]: header text printed above the first serial no.
    for w in words:
        j = next((k for k, (a, b) in enumerate(xs) if a is not None and a - 1 <= (w['x0'] + w['x1']) / 2 <= b + 1), None)
        if j is None:
            continue
        i = sum(1 for a in anchors if a - 4 <= w['top'])
        sub[i][j].append(w)
    if not any(sub[0]):
        sub = sub[1:]
    out = []
    for cells in sub:
        row_txt = []
        for ws in cells:
            ws.sort(key=lambda w: (round(w['top'] / 4), w['x0']))
            row_txt.append(' '.join(w['text'] for w in ws) or None)
        out.append(row_txt)
    return out


# 'Ward committee – 17', with the source's typos: 'W ard committee - 17', 'Ward councillor - 178' (for 'committee')
WARD_HEAD = re.compile(r'^W\s?ard\s+(?:[Cc]ommittee|[Cc]ouncill?or)\s*[–-]\s*(\d{1,3})(?!\d)')
SNO = re.compile(r'^\s*(\d{1,4}|[ivx]{1,5})\s*[.)]?\s*$', re.I)


def remap(row, colx, target):
    """Re-align a row from a table with different columns onto `target` columns by x-overlap."""
    out = [None] * len(target)
    for v, (a, b) in zip(row, colx):
        if v is None or a is None:
            continue
        best = max(range(len(target)), key=lambda k: min(b, target[k][1] or 0) - max(a, target[k][0] or 0))
        out[best] = (out[best] + '\n' + v) if out[best] else v
    return out


def split_header(rows):
    """Leading rows that are column titles: everything before the first data row (a row starting with
    a serial number, or holding a phone number or a number-only cell). At most 4."""
    for i, r in enumerate(rows[:5]):
        first = next((c for c in r if (c or '').strip()), '')
        if SNO.match(first or '') or any(phones_in(c or '') for c in r):
            return i
    return 1 if len(rows) > 1 else 0


def column_names(head_rows, ncol):
    names = []
    for j in range(ncol):
        parts = []
        for r in head_rows:
            v = r[j] if j < len(r) else None
            if v is None:  # horizontally merged: inherit from the left
                k = j
                while k > 0 and (r[k] is None):
                    k -= 1
                v = r[k] if r[k] is not None else ''
            v = one_line(v)
            if v and (not parts or parts[-1] != v):
                parts.append(v)
        names.append(' / '.join(parts) or f'col{j + 1}')
    return names


def datasets_only(out):
    from cdmp_datasets import build_datasets
    tables = [json.loads(l) for l in open(f'{out}/tables.jsonl')]
    for t in tables:
        t['ncol'] = len(t['columns'])
        t['kind'] = classify(t)                  # rules may have changed since extraction
    with open(f'{out}/tables.jsonl', 'w') as f:
        for t in tables:
            f.write(json.dumps({k: v for k, v in t.items() if k != 'ncol'}, ensure_ascii=False) + '\n')
    text_phones = list(csv.DictReader(open(f'{out}/text_phones.csv')))
    pages = list(csv.DictReader(open(f'{out}/pages.csv')))
    counts = build_datasets(tables, text_phones, pages, f'{out}/datasets')
    print(json.dumps(counts, indent=1))
    a = json.load(open(f'{out}/audit.json')); a['dataset_rows'] = counts
    a['tables_by_kind'] = dict(Counter(t['kind'] for t in tables).most_common())
    a['unclassified_tables'] = [{'id': t['id'], 'pages': t['pages'], 'title': (t['title'] or '')[:80], 'columns': t['columns'][:6]} for t in tables if t['kind'] == 'other']
    json.dump(a, open(f'{out}/audit.json', 'w'), indent=1, ensure_ascii=False)


def box_caption_used(above):
    return any(len(l['text']) > 0 for l in above if len(l['text']) < 110)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pdf')
    ap.add_argument('--out', required=True)
    ap.add_argument('--pages', help='e.g. 200-260 (for testing)')
    ap.add_argument('--datasets-only', action='store_true', help='rebuild datasets/ from an existing tables.jsonl')
    a = ap.parse_args()
    if a.datasets_only:
        return datasets_only(a.out)
    os.makedirs(f'{a.out}/tables', exist_ok=True)
    os.makedirs(f'{a.out}/datasets', exist_ok=True)

    pdf = pdfplumber.open(a.pdf)
    rng = range(1, len(pdf.pages) + 1)
    if a.pages:
        p0, p1 = map(int, a.pages.split('-')); rng = range(p0, p1 + 1)

    pages, tables, text_phones, page_phones = [], [], [], {}
    last_zone = None
    heading = {'chapter': '', 'section': ''}
    body_size = 12.0
    for pn in rng:
        page = pdf.pages[pn - 1]
        chars = [dict(c, text=clean(c['text'])) for c in page.chars]
        lines = page_lines(page)
        zone, printed = footer(lines, page.height)
        txt0 = ' '.join(l['text'] for l in lines[:6])
        if re.search(r'APPENDIX|TABLE OF CONTENTS', txt0):
            last_zone = None
        mz = re.search(r'\bZONE\s*[-–]?\s*([IVX]{1,4})\b\s*(ZONE CONTENTS|-)', txt0)
        if mz and mz.group(1) in ROMAN:
            last_zone = ROMAN[mz.group(1)]
        if zone is None:
            zone = last_zone
        else:
            last_zone = zone
        # headings: noticeably larger than body text, not the running header/footer
        page_heads = []           # (top, chapter, section) after each heading on this page
        start = dict(heading)
        for l in lines:
            if l['top'] < 52 or l['top'] > page.height - 80:
                continue
            if l['size'] >= body_size * 1.2 and len(l['text']) < 90 and re.search(r'[A-Za-z]{3}', l['text']):
                if re.match(r'^\d+(\.\d+)*\s', l['text']) or l['text'].isupper():
                    heading['chapter'] = l['text']; heading['section'] = ''
                else:
                    heading['section'] = l['text']
                page_heads.append((l['top'], dict(heading)))
        head_at = lambda y: ([h for t_, h in page_heads if t_ < y] or [start])[-1]
        pages.append({'pdf_page': pn, 'printed_page': printed, 'zone': zone, 'chapter': heading['chapter'], 'section': heading['section']})

        tbs = [t for t in page.find_tables(TABLE_SETTINGS) if not (t.bbox[1] < 56 and len(t.rows) <= 1)]
        tbs.sort(key=lambda t: (round(t.bbox[1]), t.bbox[0]))
        boxes = [t.bbox for t in tbs]
        inside = lambda l: any(b[0] - 2 <= l['x0'] and l['x1'] <= b[2] + 2 and b[1] - 2 <= l['top'] and l['bottom'] <= b[3] + 2 for b in boxes)
        free = [l for l in lines if 52 <= l['top'] <= page.height - 80 and not inside(l)]

        # phones printed outside tables (ward councillor lines, zonal office lines, ...)
        for l in free:
            for p in phones_in(l['text']):
                text_phones.append({'pdf_page': pn, 'zone': zone, 'section': heading['section'] or heading['chapter'], 'top': round(l['top']),
                                    'line': l['text'], 'phone': p})
        page_phones[pn] = set(phones_in(page.extract_text() or ''))

        prev_bottom = 52
        box_caption = ''
        for ti, tb in enumerate(tbs):
            rows, colx = grid(page, tb, chars)
            if not rows or not any(any((c or '').strip() for c in r) for r in rows):
                continue
            if len(rows) == 1 and len(rows[0]) == 1 and len(one_line(rows[0][0])) < 160 and not phones_in(rows[0][0]):
                box_caption = one_line(rows[0][0]); prev_bottom = tb.bbox[3]   # a framed title, not a table
                continue
            above = [l for l in free if prev_bottom - 2 <= l['top'] and l['bottom'] <= tb.bbox[1] + 2]
            # caption: the short line(s) directly above the table (or a framed title box)
            cap = []
            for k in range(len(above) - 1, -1, -1):
                l = above[k]
                if tb.bbox[1] - l['bottom'] > 40 + 18 * len(cap) or len(l['text']) > 110 or l['text'].endswith('.') and len(l['text']) > 60:
                    break
                prev_l = above[k - 1] if k else None
                if prev_l and l['top'] - prev_l['bottom'] < 9 and len(prev_l['text']) > 70 and not cap:
                    break            # last line of a paragraph, not a caption
                cap.insert(0, l['text'])
            caption = box_caption or ' '.join(cap[-2:])
            had_box = bool(box_caption); box_caption = ''
            title = ' '.join(l['text'] for l in above[-3:])
            ward_head = None
            for l in above:
                m = WARD_HEAD.match(l['text'])
                if m:
                    ward_head = int(m.group(1))
            prev_bottom = tb.bbox[3]
            # continuation of the previous page's table? Only if nothing is printed above it, the previous
            # table ran to the bottom of the last page, and this one starts with data rows (or repeats the header).
            last = tables[-1] if tables else None
            if last and ti == 0 and not above and not had_box and last['pages'][-1] == pn - 1 and last['bottom'] > 640 and tb.bbox[1] < 140:
                h = last['header']
                same_head = h and [one_line(c) for c in rows[0]] == [one_line(c) for c in h[0]]
                starts_with_data = split_header(rows) == 0
                if same_head or starts_with_data:
                    body = rows[split_header(rows):] if same_head else rows
                    if len(rows[0]) != last['ncol']:
                        body = [remap(r, colx, last['colx']) for r in body]
                    last['rows'] += body; last['pages'].append(pn); last['bottom'] = tb.bbox[3]
                    last['row_pages'] += [pn] * len(body)
                    continue
            nh = split_header(rows)
            hd = head_at(tb.bbox[1])
            tables.append({'pages': [pn], 'printed_page': printed, 'zone': zone, 'chapter': hd['chapter'], 'section': hd['section'],
                           'caption': caption, 'title': title, 'ward_heading': ward_head, 'bbox': [round(v, 1) for v in tb.bbox], 'bottom': tb.bbox[3],
                           'ncol': len(rows[0]), 'colx': colx, 'header': rows[:nh], 'rows': rows[nh:], 'row_pages': [pn] * (len(rows) - nh)})
        page.flush_cache()
        if pn % 50 == 0:
            print(f'  page {pn}: {len(tables)} tables so far', file=sys.stderr)

    # printed page numbers: footers are noisy, so use the PDF-to-printed offset that most nearby pages agree on
    offs = {p['pdf_page']: p['pdf_page'] - int(p['printed_page']) for p in pages if str(p['printed_page'] or '').isdigit()}
    for p in pages:
        near = [o for q, o in offs.items() if abs(q - p['pdf_page']) <= 12]
        if near:
            o = Counter(near).most_common(1)[0][0]
            p['printed_page'] = p['pdf_page'] - o if p['pdf_page'] - o > 0 else p['printed_page']
    pp = {p['pdf_page']: p['printed_page'] for p in pages}
    for t in tables:
        t['printed_page'] = pp.get(t['pages'][0], t['printed_page'])

    # ------------------------------------------------------------------ write raw outputs
    for i, t in enumerate(tables, 1):
        t['id'] = i
        t['columns'] = column_names(t['header'], t['ncol']) if t['header'] else [f'col{j + 1}' for j in range(t['ncol'])]
        t['kind'] = classify(t)
    with open(f'{a.out}/pages.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, list(pages[0])); w.writeheader(); w.writerows(pages)
    with open(f'{a.out}/tables.jsonl', 'w') as f:
        for t in tables:
            f.write(json.dumps({k: t[k] for k in ('id', 'kind', 'pages', 'printed_page', 'zone', 'chapter', 'section', 'caption', 'title', 'ward_heading',
                                                  'columns', 'header', 'rows', 'row_pages')}, ensure_ascii=False) + '\n')
    for fn in os.listdir(f'{a.out}/tables'):
        os.remove(f'{a.out}/tables/{fn}')
    for t in tables:
        name = f"{t['id']:04d}_p{t['pages'][0]}_{slug(t['kind'] if t['kind'] != 'other' else (t['title'] or t['section'] or 'table'))}.csv"
        with open(f'{a.out}/tables/{name}', 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['pdf_page'] + t['columns'])
            for r, p in zip(t['rows'], t['row_pages']):
                w.writerow([p] + [one_line(c) if c is not None else '' for c in r])
    with open(f'{a.out}/text_phones.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, ['pdf_page', 'zone', 'section', 'top', 'line', 'phone']); w.writeheader(); w.writerows(text_phones)

    # ------------------------------------------------------------------ datasets
    from cdmp_datasets import build_datasets
    counts = build_datasets(tables, text_phones, pages, f'{a.out}/datasets')

    # ------------------------------------------------------------------ audit
    found = set(p['phone'] for p in text_phones)
    for t in tables:
        for r in t['header'] + t['rows']:
            for c in r:
                found |= set(phones_in(c or ''))
    missing = {pn: sorted(ps - found) for pn, ps in page_phones.items() if ps - found}
    kinds = Counter(t['kind'] for t in tables)
    audit = {'pdf': os.path.basename(a.pdf), 'pages': len(pages), 'tables': len(tables), 'table_rows': sum(len(t['rows']) for t in tables),
             'tables_by_kind': dict(kinds.most_common()), 'dataset_rows': counts,
             'phones_on_pages': len(set().union(*page_phones.values())) if page_phones else 0,
             'phones_not_extracted': {str(k): v for k, v in missing.items()},
             'unclassified_tables': [{'id': t['id'], 'pages': t['pages'], 'title': t['title'][:80], 'columns': t['columns'][:6]}
                                     for t in tables if t['kind'] == 'other']}
    json.dump(audit, open(f'{a.out}/audit.json', 'w'), indent=1, ensure_ascii=False)
    print(json.dumps({k: audit[k] for k in ('pages', 'tables', 'table_rows', 'tables_by_kind', 'dataset_rows', 'phones_on_pages')}, indent=1))
    print('phones not extracted:', sum(len(v) for v in missing.values()), 'on', len(missing), 'pages')


# --------------------------------------------------------------------------------------------- classification
def _has(s, *words):
    return all(re.search(w, s, re.I) for w in words)


RULES = [
    # (kind, where, pattern): first match wins. where = cols (column headers) / sec (16 pt section heading
    # above the table) / cap (caption line or framed title) / ctx (paragraph text above).
    # 1. legends of the zone maps repeat other tables; keep them out of the datasets
    ('map_legend', 'cols', r'(^|\| )id\.? ?no|id\.no\.|µ|inundation extent|ward boundary|^ward ?number|^name of the zone'),
    ('map_legend', 'cap', r'^zone [ivx]+ ?[-–]|inundation extent|evacuation area|boat location|relief shelters|roads/streets prone'),
    # 2. column headers that only one kind of table has
    ('ward_committee', 'cols', r'name of the de.*designation'),
    ('inundation_summary', 'cols', r'(chronic|no\.? ?of\.? ?water stag|\btotal\b).*vulnerab|vulnerab.*(\btotal\b|chronic)|^sl\.? ?no\.? \| zone \| (very ?high|no\.)'),
    ('inundation_history', 'cols', r'vulnerab.*location|location.*vulnerab'),
    ('inundation_summary', 'cols', r'vulnerab'),
    ('contacts', 'cols', r'team member'),
    ('relief_centres', 'cols', r'relief cent.*capacity|capacity.*relief cent|people ?to ?be ?shift.*capacity|capacity.*people ?to ?be ?shift|cooking'),
    ('evacuation_streets', 'cols', r'no\.? ?of persons'),
    ('pumping_stations', 'cols', r'pumping s'),
    ('water_stagnation', 'cols', r'manholes?'),
    ('inundation_streets', 'cols', r'inundation seen|max\.? ?depth|time taken'),
    ('subways', 'cols', r'subway'),
    ('water_entered_houses', 'cols', r'name of the area ?/ ?streets|streets where water enters'),
    # 3. the zone chapter's section heading
    ('water_entered_houses', 'sec', r'water entered|where water'),
    ('evacuation_streets', 'sec', r'require evacuation|need evacuation'),
    ('tree_fall', 'sec', r'tree ?fall'),
    ('inundation_streets', 'sec+cols', r'stagnat.*\|\|.*(pump|disposal|capacity)'),
    ('water_stagnation', 'sec', r'stagnat'),
    ('parks', 'sec', r'\bparks?\b|play ?field'),
    ('relief_centres', 'sec', r'relief cent'),
    ('ndrf', 'sec', r'ndrf|disaster response force'),
    ('boats', 'sec', r'boat'),
    ('lighting', 'sec', r'light'),
    ('vehicles', 'sec', r'lorr|transport|equipment'),
    ('narrow_lanes', 'sec', r'2\.5 ?m|cannot be accessed'),
    ('pumping_stations', 'sec', r'pumping'),
    ('storm_water_drains', 'sec', r'storm ?water'),
    ('water_bodies', 'sec', r'canal|water bod|waterway'),
    ('tenements', 'sec', r'tenement|tnscb|tnuhdb|slum'),
    ('population', 'sec', r'^profile'),
    # 4. caption, then remaining column hints, then the paragraph above
    ('inundation_history', 'cap', r'inundation.*monsoon\s*-?\s*20\d\d|monsoon\s*-?\s*20\d\d.*inundation'),
    ('inundation_history', 'cap', r'inundation locations?\b.*\d{4}|\d{4}.*inundation locations?'),
    ('narrow_lanes', 'cap', r'2\.5 ?m|cannot be accessed'),
    ('water_entered_houses', 'cap', r'water entered|do not require'),
    ('evacuation_streets', 'cap', r'require evacuation|need evacuation'),
    ('water_stagnation', 'cap', r'stagnat|sewer block'),
    ('inundation_streets', 'cap', r'heavy rain|inundat'),
    ('tree_fall', 'cap', r'tree ?fall'),
    ('water_bodies', 'cap', r'^(ponds?|lakes?|canals?|tanks?)\b'),
    ('assembly_points', 'cols', r'play ?ground|play ?field'),
    ('parks', 'cols', r'\bpark|osr'),
    ('ndrf', 'cols', r'ndrf|sdrf'),
    ('boats', 'cols', r'boats?'),
    ('subways', 'sec', r'subway'),
    ('water_entered_houses', 'ctx', r'water entered|do not require evacuation'),
    ('evacuation_streets', 'ctx', r'require evacuation'),
    ('lighting', 'ctx', r'battery|lighting|street ?light'),
    ('vehicles', 'cols', r'jcb|bob ?cat|lorr|loader'),
    ('tenements', 'cols', r'tenement'),
    ('health_facilities', 'cols', r'medical officer|hospital|uphc|uchc'),
    ('water_bodies', 'cols', r'canal|water ?bod|pond|lake|tank'),
    ('storm_water_drains', 'cols', r'swd|storm'),
    ('rainfall', 'cols', r'rainfall|\bmm\b'),
    ('population', 'cols', r'population|house ?holds'),
    ('contents', 'cols', r'description.*page'),
    ('contacts', 'cols', r'designation|mobile|contact|phone'),
]


def classify(t):
    """Name the kind of table from its own column headers, caption and section (edition-independent)."""
    where = {'cols': ' | '.join(t['columns']).lower(), 'cap': (t.get('caption') or '').lower(),
             'sec': (t['section'] or '').lower(), 'ctx': (t['title'] or '').lower()}
    where['sec+cols'] = where['sec'] + ' || ' + where['cols']
    if t['zone'] is None:            # outside the zone chapters, section names like 'Subways' describe city-wide text
        where['sec'] = '' if not re.search(r'assembly|inundat|flood', where['sec']) else where['sec']
    if t['ward_heading']:
        return 'ward_committee'
    serial_rows = sum(1 for r in t['rows'] if r and SNO.match(one_line(r[0]) or ''))
    if len(t['columns']) >= 2 and len(set(t['columns'])) == 1 and serial_rows < 2:
        return 'map_legend'        # a legend box: every column carries the same title
    toks = re.findall(r'[A-Za-z&]+', ' '.join(t['columns']))
    if toks and serial_rows < 2 and (sum(len(x) > 18 for x in toks) / len(toks) > 0.25 or sum(len(x) > 22 for x in toks) and sum(len(x) > 14 for x in toks) / len(toks) > 0.15):
        return 'map_legend'        # glyph runs without spaces: text drawn on a map, not a table
    if t['ncol'] == 1 and len(t['rows']) <= 2 and not any(phones_in(c or '') for r in t['rows'] for c in r) and not ''.join(map(str, t['header'][0] if t['header'] else [])).strip():
        return 'figure_label'      # the label box under a photograph
    for kind, w, rx in RULES:
        if re.search(rx, where[w]):
            return kind
    if any(phones_in(c or '') for r in t['rows'][:6] for c in r):
        return 'contacts'
    return 'other'


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
