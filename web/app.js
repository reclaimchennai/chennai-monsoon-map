/* Chennai Monsoon Map — maps.reclaimchennai.city/monsoon
   Data: github.com/reclaimchennai/chennai-monsoon-map (GCC pump lists, GCC City Disaster Management Plan, TNGIS, OSM, SWD).
   MapLibre: layers are wired on 'style.load' — 'load' never fires reliably on this host. */
(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ZN = ['Thiruvottiyur', 'Manali', 'Madhavaram', 'Tondiarpet', 'Royapuram', 'Thiru-Vi-Ka Nagar', 'Ambattur', 'Anna Nagar',
    'Teynampet', 'Kodambakkam', 'Valasaravakkam', 'Alandur', 'Adyar', 'Perungudi', 'Sholinganallur'];
  const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII', 'XIV', 'XV'];
  const PH = '<svg viewBox="0 0 24 24"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/></svg>';
  const PIN = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3.2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/><circle cx="12" cy="12" r="7.5"/></svg>';
  const APPROX = new Set(['locality']);   // placed at a neighbourhood's centre, not the exact spot
  const SEV = ['#f5c542', '#f5c542', '#f59f00', '#e8590c', '#d6336c', '#a61e4d'];

  const LAYERS = [
    { id: 'tractors', name: 'Tractor pumps', sub: 'Driver and mobile number for each', color: '#e8590c', letter: 'T', on: true },
    { id: 'pumps', name: 'Diesel & RP pumps', sub: 'Placed in 151 flood-prone spots', color: '#6741d9', letter: 'D', on: true },
    { id: 'flood_spots', name: 'Flood-prone streets', sub: 'GCC flood records (City Disaster Management Plan)', color: '#d6336c', on: true, kind: 'flood' },
    { id: 'subways', name: 'Subways', sub: 'Usually closed first in heavy rain', color: '#1c7ed6', letter: 'S', on: true },
    { id: 'relief', name: 'Relief centres', sub: 'Shelters with officers to call', color: '#2f9e44', letter: 'R', on: true },
    { id: 'evacuation', name: 'Evacuation-prone streets', sub: 'People moved out / water entered homes', color: '#ae3ec9', letter: 'E', on: false },
    { id: 'assembly', name: 'Assembly points & parks', sub: 'Open ground for gathering', color: '#0ca678', letter: 'A', on: false },
    { id: 'ndrf', name: 'NDRF teams & boats', sub: 'Where rescue teams are stationed', color: '#f08c00', letter: 'B', on: false },
    { id: 'trees', name: 'Tree-fall spots', sub: 'Past monsoon tree falls', color: '#8d6e63', letter: '', on: false },
    { id: 'swd', name: 'Storm water drains', sub: 'Traced from GCC ward sheets (107 wards)', color: '#1971c2', on: false, kind: 'swd' },
    { id: 'water', name: 'Lakes, tanks & rivers', sub: 'TNGIS water bodies', color: '#5fb3d6', on: true, kind: 'water', file: '../old/data/chennai_waterbodies_merged.geojson' },
    { id: 'flood2015', name: 'Flooded streets, Dec 2015', sub: 'Crowd-mapped (osm-in/flood-map)', color: '#5c7cfa', on: false, kind: 'f2015', file: '../old/data/chennai_flood.geojson' },
    { id: 'wards', name: 'Ward boundaries', sub: 'GCC 200 wards, 15 zones', color: '#7d8f99', on: true, kind: 'wards' },
  ];
  const L = Object.fromEntries(LAYERS.map(l => [l.id, l]));
  const POINT_LAYERS = LAYERS.filter(l => l.letter !== undefined).map(l => l.id);
  const DATA = {};            // id -> FeatureCollection
  let INFO = null;            // wards_info.json
  let UNPLACED = [], ED = '';  // items whose printed location could not be found on the map
  let WARDS = null;           // wards polygons
  let me = null, meMarker = null, selWard = null, current = 'near', detailStack = [];

  try { const s = JSON.parse(localStorage.getItem('monsoonLayers') || '{}'); LAYERS.forEach(l => { if (l.id in s) l.on = s[l.id]; }); } catch (e) {}
  const saveLayers = () => { try { localStorage.setItem('monsoonLayers', JSON.stringify(Object.fromEntries(LAYERS.map(l => [l.id, l.on])))); } catch (e) {} };

  // ---------- loader rain
  const rain = $('#rain');
  for (let i = 0; i < 18; i++) { const d = document.createElement('i'); d.style.left = (i * 6.7) + 'px'; d.style.animationDelay = (Math.random() * .9).toFixed(2) + 's'; rain.appendChild(d); }

  // ---------- map
  const map = new maplibregl.Map({
    container: 'map', style: 'https://tiles.openfreemap.org/styles/positron',
    center: [80.235, 13.05], zoom: window.innerWidth < 860 ? 10.4 : 11.2, minZoom: 9, maxZoom: 18.5,
    hash: 'm', attributionControl: false, dragRotate: false, pitchWithRotate: false,
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
  map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: 'GCC pump lists · GCC City Disaster Management Plan · TNGIS · SWD: @reclaimchennai · © OpenStreetMap' }), 'bottom-right');

  const fetchJSON = u => fetch(u).then(r => { if (!r.ok) throw new Error(u + ' ' + r.status); return r.json(); });
  const files = LAYERS.map(l => fetchJSON(l.file || ('data/' + (l.id === 'wards' ? 'wards' : l.id) + '.geojson')).then(d => { DATA[l.id] = d; }).catch(e => console.warn(e)));
  const labelsP = fetchJSON('data/ward_labels.geojson');
  const infoP = fetchJSON('data/wards_info.json').then(d => { INFO = d; ED = (d.meta && d.meta.cdmp) || ''; });
  const unplacedP = fetchJSON('data/unplaced.json').then(d => { UNPLACED = d; }).catch(() => {});
  const dataReady = Promise.all([...files, labelsP, infoP, unplacedP]).then(() => { WARDS = DATA.wards; });

  map.on('style.load', async () => {
    map.getStyle().layers.forEach(l => {   // the mtc v2 cream recolour
      try {
        if (l.type === 'background') map.setPaintProperty(l.id, 'background-color', '#f9f5ed');
        else if (l.type === 'fill' && /water|ocean|sea/i.test(l.id)) map.setPaintProperty(l.id, 'fill-color', '#bfe3f2');
        else if (l.type === 'fill' && /(wood|forest|park|grass|landcover|landuse_|cemetery|pitch)/i.test(l.id)) map.setPaintProperty(l.id, 'fill-color', '#e6ebda');
      } catch (e) {}
    });
    await dataReady;
    const labels = await labelsP;
    addLayers(labels);
    $('#loader').classList.add('gone');
    buildSearch();
    route();
  });

  function vis(on) { return on ? 'visible' : 'none'; }

  function addLayers(labels) {
    const firstSym = (map.getStyle().layers.find(l => l.type === 'symbol') || {}).id;
    const add = (l, below) => map.addLayer(l, below ? firstSym : undefined);
    for (const l of LAYERS) if (DATA[l.id]) map.addSource(l.id, { type: 'geojson', data: DATA[l.id], promoteId: undefined });
    map.addSource('ward_labels', { type: 'geojson', data: labels });

    // water + 2015 floods + drains under labels
    add({ id: 'water-fill', type: 'fill', source: 'water', layout: { visibility: vis(L.water.on) }, paint: { 'fill-color': '#a5d8ee', 'fill-opacity': .7 } }, true);
    add({ id: 'water-line', type: 'line', source: 'water', layout: { visibility: vis(L.water.on) }, paint: { 'line-color': '#5fb3d6', 'line-width': .7 } }, true);
    add({ id: 'flood2015-line', type: 'line', source: 'flood2015', layout: { visibility: vis(L.flood2015.on), 'line-cap': 'round' },
      paint: { 'line-color': '#5c7cfa', 'line-opacity': .55, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 1, 15, 4] } }, true);
    add({ id: 'swd-line', type: 'line', source: 'swd', filter: ['==', ['geometry-type'], 'LineString'], layout: { visibility: vis(L.swd.on), 'line-cap': 'round' },
      paint: { 'line-color': '#1971c2', 'line-opacity': .8, 'line-width': ['interpolate', ['linear'], ['zoom'], 11, .5, 16, 2.6] } }, true);
    add({ id: 'swd-out', type: 'circle', source: 'swd', filter: ['==', ['geometry-type'], 'Point'], minzoom: 13, layout: { visibility: vis(L.swd.on) },
      paint: { 'circle-radius': 3.5, 'circle-color': '#fff', 'circle-stroke-color': '#1971c2', 'circle-stroke-width': 2 } }, true);
    // wards
    add({ id: 'wards-sel', type: 'fill', source: 'wards', filter: ['==', ['get', 'ward'], -1], paint: { 'fill-color': '#2b9ac4', 'fill-opacity': .08 } }, true);
    add({ id: 'wards-line', type: 'line', source: 'wards', layout: { visibility: vis(L.wards.on) },
      paint: { 'line-color': '#6f8590', 'line-opacity': ['interpolate', ['linear'], ['zoom'], 10, .35, 14, .7], 'line-width': ['interpolate', ['linear'], ['zoom'], 10, .5, 15, 1.4], 'line-dasharray': [3, 2] } }, true);
    add({ id: 'wards-sel-line', type: 'line', source: 'wards', filter: ['==', ['get', 'ward'], -1], paint: { 'line-color': '#2b9ac4', 'line-width': 3 } }, true);
    // flood-prone streets
    const sevColor = ['step', ['get', 'sev'], SEV[1], 2, SEV[2], 3, SEV[3], 4, SEV[4], 5, SEV[5]];
    // flood-prone streets: GCC road polygons (filled) - an outline keeps them visible when zoomed out
    add({ id: 'flood-fill', type: 'fill', source: 'flood_spots', filter: ['all', ['==', ['get', 'line'], 1], ['in', ['geometry-type'], ['literal', ['Polygon', 'MultiPolygon']]]],
      layout: { visibility: vis(L.flood_spots.on) }, paint: { 'fill-color': sevColor, 'fill-opacity': .85 } }, true);
    add({ id: 'flood-line', type: 'line', source: 'flood_spots', filter: ['==', ['get', 'line'], 1], layout: { visibility: vis(L.flood_spots.on), 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': sevColor, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 2.2, 14, 1.6, 17, 1], 'line-opacity': .95 } }, true);
    add({ id: 'flood-pt', type: 'circle', source: 'flood_spots', filter: ['all', ['!=', ['get', 'line'], 1], ['!=', ['get', 'prec'], 'street']], layout: { visibility: vis(L.flood_spots.on) },
      paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.2, 15, 6], 'circle-color': ['step', ['get', 'sev'], SEV[1], 2, SEV[2], 3, SEV[3], 4, SEV[4], 5, SEV[5]],
        'circle-opacity': ['case', ['in', ['get', 'prec'], ['literal', ['ward', 'zone']]], .45, .9], 'circle-stroke-color': '#fff', 'circle-stroke-width': 1 } });
    // point layers: filled = placed on the street / place; hollow = only known to the ward or division office
    for (const id of ['trees', 'assembly', 'ndrf', 'evacuation', 'subways', 'relief', 'pumps', 'tractors']) {
      const l = L[id]; if (!DATA[id]) continue;
      const approx = ['in', ['get', 'prec'], ['literal', [...APPROX]]];
      const small = id === 'trees';
      map.addLayer({ id: id + '-c', type: 'circle', source: id, layout: { visibility: vis(l.on) },
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, small ? 1.6 : 2.6, 12, small ? 3 : 5, 14, small ? 5 : 9.5, 17, small ? 7 : 13],
          'circle-color': ['case', approx, '#ffffff', l.color], 'circle-stroke-color': ['case', approx, l.color, '#ffffff'],
          'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 9, 1, 14, 2.4] } });
      if (l.letter) map.addLayer({ id: id + '-t', type: 'symbol', source: id, minzoom: 13.2, layout: { visibility: vis(l.on), 'text-field': l.letter, 'text-font': ['Noto Sans Bold'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 13.2, 9, 17, 13], 'text-allow-overlap': true, 'text-ignore-placement': true },
        paint: { 'text-color': ['case', approx, l.color, '#ffffff'] } });
    }
    map.addLayer({ id: 'ward-num', type: 'symbol', source: 'ward_labels', minzoom: 12.6, layout: { visibility: vis(L.wards.on), 'text-field': ['concat', 'Ward ', ['to-string', ['get', 'ward']]],
      'text-font': ['Noto Sans Bold'], 'text-size': 11, 'text-padding': 8 }, paint: { 'text-color': '#56707d', 'text-halo-color': 'rgba(249,245,237,.9)', 'text-halo-width': 1.6 } });
    map.addLayer({ id: 'hl', type: 'circle', source: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
      paint: { 'circle-radius': 20, 'circle-color': 'rgba(43,154,196,.18)', 'circle-stroke-color': '#2b9ac4', 'circle-stroke-width': 2.5 } });

    const clickable = ['tractors-c', 'pumps-c', 'relief-c', 'subways-c', 'evacuation-c', 'assembly-c', 'ndrf-c', 'trees-c', 'flood-pt', 'flood-fill', 'flood-line'];
    map.on('click', e => {
      const p = e.point, pad = window.innerWidth < 860 ? 12 : 7;
      const fs = map.queryRenderedFeatures([[p.x - pad, p.y - pad], [p.x + pad, p.y + pad]], { layers: clickable.filter(id => map.getLayer(id)) });
      if (fs.length) {
        const order = id => clickable.indexOf(id);
        fs.sort((a, b) => order(a.layer.id) - order(b.layer.id));
        const f = fs[0], src = f.source;
        showDetail(src, f.properties, f.geometry.type === 'Point' ? f.geometry.coordinates : [e.lngLat.lng, e.lngLat.lat], false);
        return;
      }
      if (L.wards.on) { const w = wardAt([e.lngLat.lng, e.lngLat.lat]); if (w) showWard(w, false); }
    });
    for (const id of clickable) {
      map.on('mouseenter', id, () => map.getCanvas().style.cursor = 'pointer');
      map.on('mouseleave', id, () => map.getCanvas().style.cursor = '');
    }
  }

  // ---------- geometry helpers
  function inRing(pt, ring) {
    let ins = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi) ins = !ins;
    }
    return ins;
  }
  function inPoly(pt, g) {
    const polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
    return polys.some(p => inRing(pt, p[0]) && !p.slice(1).some(h => inRing(pt, h)));
  }
  function wardAt(pt) { const f = WARDS && WARDS.features.find(f => inPoly(pt, f.geometry)); return f ? f.properties.ward : null; }
  function dist(a, b) {
    const R = 6371000, r = Math.PI / 180, dLa = (b[1] - a[1]) * r, dLo = (b[0] - a[0]) * r;
    const h = Math.sin(dLa / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(dLo / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  const fmtD = m => m < 1000 ? Math.round(m / 10) * 10 + ' m' : (m / 1000).toFixed(m < 10000 ? 1 : 0) + ' km';
  const pts = id => (DATA[id] ? DATA[id].features.filter(f => f.geometry.type === 'Point' && !f.properties.line) : []);
  function nearest(id, at, n, maxM = 1e9) {
    return pts(id).map(f => ({ f, d: dist(at, f.geometry.coordinates) })).filter(x => x.d <= maxM).sort((a, b) => a.d - b.d).slice(0, n);
  }
  const unplacedIn = (id, w) => UNPLACED.filter(u => u.layer === id && +u.ward === w).map(u => ({ f: { properties: u, unplaced: true, u }, d: null }));
  const prop = (p, k) => { const v = p[k]; if (typeof v === 'string' && (v[0] === '[' || v[0] === '{')) { try { return JSON.parse(v); } catch (e) {} } return v; };

  // ---------- HTML atoms
  const tel = (ph, who, sub) => ph.bad || !ph.n
    ? `<div class="call bad"><span class="ph">${PH}</span><span class="who"><b>${esc(who)}</b><span>Number as printed looks wrong${sub ? ' · ' + esc(sub) : ''}</span></span><span class="num">${esc(ph.d)}</span></div>`
    : `<a class="call" href="tel:${ph.n}"><span class="ph">${PH}</span><span class="who"><b>${esc(who)}</b>${sub ? `<span>${esc(sub)}</span>` : ''}</span><span class="num">${esc(ph.d)}</span></a>`;
  const pills = list => `<div class="nums">${(list || []).map(ph => ph.bad || !ph.n
    ? `<span class="num-pill bad" title="As printed — not a valid number">${esc(ph.d)}</span>`
    : `<a class="num-pill" href="tel:${ph.n}">${PH}${esc(ph.d)}${ph.label ? ` <small>${esc(ph.label)}</small>` : ''}</a>`).join('')}</div>`;
  const zlabel = z => z ? `Zone ${ROMAN[z]} · ${ZN[z - 1]}` : '';
  const precNote = p => ({
    street: '', place: '',
    office: `<span class="chip ok">At the ward office${p.match && /nearest/.test(p.match) ? ' (nearest office in TNGIS)' : ''}</span>`,
    locality: `<span class="chip approx">Placed at the centre of ${esc(p.match || 'the locality')}: exact spot not on the map</span>`,
    unplaced: `<span class="chip approx">Location not found on the map: listed under Ward ${esc(p.ward)}</span>`,
  }[p.prec] || '');
  const dot = (id, p) => { const l = L[id]; const ap = APPROX.has(p.prec) || p.prec === 'unplaced'; return `<span class="dot ${ap ? 'approx' : ''}" style="${ap ? `border-color:${l.color};color:${l.color}` : `background:${l.color}`}">${l.letter || '•'}</span>`; };
  const title = (id, p) => ({
    tractors: p.prec === 'office' ? `Division ${p.ward} office` : p.loc, pumps: p.loc, relief: p.name, subways: p.name, evacuation: p.name, assembly: p.name, ndrf: p.loc || p.name, trees: p.name, flood_spots: p.name,
  }[id] || p.name);
  const subtitle = (id, p) => ({
    tractors: `${p.tractor} · ${p.driver}`, pumps: `${p.pump || (p.kind === 'RP' ? 'RP pump' : 'Diesel pump')}${p.hp ? ' · ' + p.hp : ''}`,
    relief: `Relief centre${p.cap ? ' · ' + p.cap + ' people' : ''}`, flood_spots: floodSummary(p), subways: 'Subway',
  }[id] || L[id].name) + (p.ward ? ` · Ward ${p.ward}` : '');
  function floodSummary(p) {
    const yrs = prop(p, 'years') || [], c = { very_high: '>5 ft', high: '3–5 ft', medium: '2–3 ft', low: '<2 ft' }[p.cls];
    return [yrs.length ? `Flooded ${yrs.join(', ')}` : (prop(p, 'rain') || []).includes('heavy') ? 'Floods in heavy rain' : 'Water stagnates', c].filter(Boolean).join(' · ');
  }

  // ---------- panel / sheet
  const sheet = $('#sheet'), body = $('#body');
  const isMobile = () => window.innerWidth < 860;
  function setSheet(state) { if (!isMobile()) return; sheet.classList.remove('mid', 'full'); if (state) sheet.classList.add(state); }
  function render(html) { body.innerHTML = html; body.scrollTop = 0; }
  document.querySelectorAll('.tab').forEach(t => t.onclick = () => { openTab(t.dataset.tab); if (!sheet.classList.contains('full')) setSheet('mid'); });
  function openTab(tab) {
    current = tab; detailStack = [];
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.dataset.tab === tab));
    ({ near: renderNear, layers: renderLayers, help: renderHelp, live: renderLive, about: renderAbout })[tab]();
  }

  // drag the sheet on mobile
  (() => {
    let y0 = null, t0 = 0, base = 0, dy = 0;
    const H = () => sheet.getBoundingClientRect().height;
    const offsetOf = () => sheet.classList.contains('full') ? 0 : sheet.classList.contains('mid') ? H() - innerHeight * .52 : H() - parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sheet-peek'));
    const start = e => { if (!isMobile()) return; if (e.target.closest('#body') && body.scrollTop > 0 && sheet.classList.contains('full')) return;
      if (e.target.closest('#body') && !sheet.classList.contains('full') === false) return;
      y0 = e.touches ? e.touches[0].clientY : e.clientY; t0 = Date.now(); base = offsetOf(); dy = 0; sheet.style.transition = 'none'; };
    const move = e => { if (y0 === null) return; dy = (e.touches ? e.touches[0].clientY : e.clientY) - y0; sheet.style.transform = `translateY(${Math.max(0, base + dy)}px)`; };
    const end = () => { if (y0 === null) return; sheet.style.transition = ''; sheet.style.transform = '';
      const v = dy / Math.max(1, Date.now() - t0), pos = base + dy, h = H();
      const states = [[0, 'full'], [h - innerHeight * .52, 'mid'], [h - 168, '']];
      let target = states.reduce((a, b) => Math.abs(b[0] - pos) < Math.abs(a[0] - pos) ? b : a);
      if (Math.abs(v) > .5) { const i = states.findIndex(s => s[1] === (sheet.classList.contains('full') ? 'full' : sheet.classList.contains('mid') ? 'mid' : '')); target = states[Math.max(0, Math.min(2, i + (v > 0 ? 1 : -1)))]; }
      if (Math.abs(dy) < 6) target = sheet.classList.contains('full') || sheet.classList.contains('mid') ? states[2] : states[1];
      setSheet(target[1]); y0 = null; };
    for (const el of [$('#grab'), $('#tabs')]) { el.addEventListener('touchstart', start, { passive: true }); el.addEventListener('mousedown', start); }
    addEventListener('touchmove', move, { passive: true }); addEventListener('mousemove', move);
    addEventListener('touchend', end); addEventListener('mouseup', end);
  })();

  // ---------- Near me
  function hotline() {
    return `<div class="hot">
      <a href="tel:1913"><b>1913</b><span>GCC helpline</span></a>
      <a href="tel:1070"><b>1070</b><span>State control room</span></a>
      <a href="tel:112"><b>112</b><span>Emergency</span></a>
      <a href="tel:101"><b>101</b><span>Fire &amp; rescue</span></a>
      <a href="tel:108"><b>108</b><span>Ambulance</span></a>
      <a href="tel:100"><b>100</b><span>Police</span></a></div>`;
  }
  function renderNear() {
    if (!me) {
      render(`<h2>Water rising on your street?</h2>
        <p class="lede">Find the tractor pump drivers, diesel pumps, relief centres and ward officers closest to you, with their numbers.</p>
        <button class="bigbtn" id="nearLocate">${PIN} Use my location</button>
        <div class="row" style="gap:8px"><select id="wardpick" class="bigbtn ghost" style="appearance:auto;text-align:left">
          <option value="">…or choose your ward</option>${Array.from({ length: 200 }, (_, i) => `<option value="${i + 1}">Ward ${i + 1} · ${ZN[INFO ? INFO.wards[i + 1].zone - 1 : 0]}</option>`).join('')}</select></div>
        <h3>Emergency numbers</h3>${hotline()}
        <h3>On the map</h3>${countsBlock()}
        <p class="muted">Hollow markers are known only to their ward or division office. The source lists rarely give exact spots.</p>`);
      $('#nearLocate').onclick = locate;
      $('#wardpick').onchange = e => e.target.value && showWard(+e.target.value, true);
      return;
    }
    const at = me, w = wardAt(at);
    const near = (id, n, max) => nearest(id, at, n, max);
    const t = near('tractors', 6), p = near('pumps', 4), r = near('relief', 3), s = near('subways', 2, 3000), fl = near('flood_spots', 6, 700);
    const wi = w && INFO.wards[w];
    const keyc = wi ? keyContacts(wi).slice(0, 3) : [];
    render(`<div class="row" style="justify-content:space-between"><h2>${w ? `You're in Ward ${w}` : 'Outside GCC wards'}</h2><button class="back" id="relocate">Refresh</button></div>
      <p class="lede">${w ? zlabel(wi.zone) : 'The pump and contact lists cover the Greater Chennai Corporation.'}</p>
      ${w ? keyc.map(c => c.ph.map(ph => tel(ph, c.who, c.sub)).join('')).join('') + `<button class="bigbtn ghost" id="wardAll">All Ward ${w} contacts</button>` : ''}
      <h3>Nearest tractor pumps</h3>${list('tractors', t, true)}
      ${w && unplacedIn('tractors', w).length ? `<h3>Also in Ward ${w} (location not on map)</h3>${list('tractors', unplacedIn('tractors', w), true)}` : ''}
      <h3>Nearest diesel / RP pumps</h3>${list('pumps', p)}
      <h3>Nearest relief centres</h3>${list('relief', r)}
      ${s.length ? `<h3>Subways nearby</h3>${list('subways', s)}` : ''}
      ${fl.length ? `<h3>Flood-prone streets within 700 m</h3>${list('flood_spots', fl)}` : ''}
      <h3>Emergency numbers</h3>${hotline()}`);
    $('#relocate').onclick = locate;
    if ($('#wardAll')) $('#wardAll').onclick = () => showWard(w, true);
    bindList();
  }
  function countsBlock() {
    const n = id => pts(id).length;
    return `<div class="kv"><dt>Tractor pumps</dt><dd><b>${n('tractors')}</b> with drivers' numbers</dd>
      <dt>Diesel / RP pumps</dt><dd><b>${n('pumps')}</b></dd><dt>Flood-prone spots</dt><dd><b>${n('flood_spots')}</b></dd>
      <dt>Relief centres</dt><dd><b>${n('relief')}</b></dd><dt>Ward contacts</dt><dd><b>200</b> wards</dd></div>`;
  }
  function list(id, rows, callBtn) {
    if (!rows.length) return '<p class="muted">None found.</p>';
    return rows.map(({ f, d }, i) => {
      const p = f.properties, phs = prop(p, 'phones') || [];
      const ph = callBtn && phs.find(x => x.n);
      const idx = f.unplaced ? 'u' + UNPLACED.indexOf(f.u) : DATA[id].features.indexOf(f);
      return `<div class="item" data-l="${id}" data-i="${idx}">${dot(id, p)}
        <div class="main"><b>${esc(title(id, p))}</b><div class="s">${esc(subtitle(id, p))}</div></div>
        ${f.unplaced ? `<span class="dist">not on map</span>` : d != null ? `<span class="dist">${APPROX.has(p.prec) ? '≈ ' + fmtD(d) : fmtD(d)}</span>` : ''}
        ${ph ? `<a class="callmini" href="tel:${ph.n}" aria-label="Call ${esc(p.driver)}" onclick="event.stopPropagation()">${PH}</a>` : ''}</div>`;
    }).join('');
  }
  function bindList() {
    body.querySelectorAll('.item[data-l]').forEach(el => el.onclick = () => {
      if (el.dataset.i[0] === 'u') { const u = UNPLACED[+el.dataset.i.slice(1)]; showDetail(el.dataset.l, u, null, false); return; }
      const f = DATA[el.dataset.l].features[+el.dataset.i];
      showDetail(el.dataset.l, f.properties, f.geometry.coordinates, true);
    });
  }

  function locate() {
    const b = $('#locate'); b.classList.add('busy');
    if (!navigator.geolocation) { alert('Location is not available in this browser. Choose your ward instead.'); b.classList.remove('busy'); return; }
    navigator.geolocation.getCurrentPosition(pos => {
      b.classList.remove('busy'); b.classList.add('on');
      setMe([pos.coords.longitude, pos.coords.latitude]);
    }, err => { b.classList.remove('busy'); alert('Could not get your location (' + err.message + '). You can choose your ward instead.'); openTab('near'); },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  }
  $('#locate').onclick = locate;
  const pad = () => isMobile() ? { bottom: innerHeight * .5, top: 70, left: 20, right: 20 } : { left: 410, top: 40, right: 40, bottom: 40 };

  // ---------- details
  function showDetail(id, p, at, fly) {
    const back = detailStack.length || current ? `<button class="back" id="back">‹ Back</button>` : '';
    detailStack.push(id);
    const phs = prop(p, 'phones') || [];
    let h = `${back}<div class="row" style="margin-top:4px">${dot(id, p)}<span class="muted">${esc(L[id].name)}</span></div><h2>${esc(title(id, p))}</h2>`;
    const w = p.ward ? +p.ward : null;
    if (id === 'tractors') {
      h += `<p class="lede"><b>${esc(p.driver)}</b> drives tractor <b>${esc(p.tractor)}</b>. Call if water is stagnating in your street.</p>${pills(phs)}
        <dl class="kv"><dt>Location</dt><dd>${esc(p.loc)}</dd><dt>Division</dt><dd>${esc(p.ward)} · ${zlabel(+p.zone)}</dd>${p.match ? `<dt>Mapped to</dt><dd>${esc(p.match)}</dd>` : ''}</dl>
        ${precNote(p)}${p.note ? `<div class="warnbox">${esc(p.note)}</div>` : ''}`;
    } else if (id === 'pumps') {
      h += `<p class="lede">${p.kind === 'RP' ? 'RP pump' : 'Diesel-engine pump'}${p.pump ? ` <b>${esc(p.pump)}</b>` : ''}${p.hp ? ` (${esc(p.hp)})` : ''} placed for de-flooding.</p>
        <dl class="kv"><dt>Location</dt><dd>${esc(p.loc)}</dd><dt>Placed</dt><dd>${esc(p.placed || '—')}</dd><dt>Division</dt><dd>${esc(p.ward)} · ${zlabel(+p.zone)}</dd>${p.match ? `<dt>Mapped to</dt><dd>${esc(p.match)}</dd>` : ''}</dl>
        ${precNote(p)}${p.note ? `<div class="warnbox">${esc(p.note)}</div>` : ''}
        <p class="muted">These pumps have no driver number on the list. Call the ward's engineer:</p>${engineer(w)}`;
    } else if (id === 'flood_spots') {
      const yrs = prop(p, 'years') || [], rain = prop(p, 'rain') || [], pages = prop(p, 'pages') || [];
      const c = { very_high: 'Very high: above 5 ft', high: 'High: 3 to 5 ft', medium: 'Medium: 2 to 3 ft', low: 'Low: under 2 ft' }[p.cls];
      h += `<p class="lede">${esc(floodSummary(p))}</p><dl class="kv">
        ${c ? `<dt>Depth class</dt><dd><span class="sev" style="background:${SEV[p.sev] || SEV[1]}"></span>${c}</dd>` : ''}
        ${yrs.length ? `<dt>Recorded</dt><dd>${yrs.join(', ')}</dd>` : ''}
        ${rain.length ? `<dt>Stagnates in</dt><dd>${rain.map(r => ({ heavy: 'heavy rain', moderate: 'moderate rain', mild: 'mild rain', sewer_block: 'sewer blocks', recorded: 'rain' }[r] || r)).join(', ')}</dd>` : ''}
        ${p.depth ? `<dt>Max depth</dt><dd>${esc(p.depth)}</dd>` : ''}${p.drain ? `<dt>Drains in</dt><dd>${esc(p.drain)}</dd>` : ''}
        ${p.pump ? `<dt>Pump</dt><dd>${esc(p.pump)}</dd>` : ''}${p.disposal ? `<dt>Water goes to</dt><dd>${esc(p.disposal)}</dd>` : ''}
        ${p.reason ? `<dt>Reason</dt><dd>${esc(p.reason)}</dd>` : ''}
        <dt>Ward</dt><dd>${esc(p.ward ?? '—')} · ${zlabel(+p.zone)}</dd>${p.match && p.match !== p.name ? `<dt>Mapped to</dt><dd>${esc(p.match)}</dd>` : ''}</dl>
        ${precNote(p)}<p class="muted">Source: GCC City Disaster Management Plan ${ED}${pages.length ? ', PDF p. ' + pages.slice(0, 4).join(', ') : ''}.</p>
        <h3>Who to call</h3>${engineer(w)}`;
    } else if (id === 'relief') {
      const cs = prop(p, 'contacts') || [];
      const yn = (v, t) => v === true ? `<span class="chip ok">✓ ${t}</span>` : v === false ? `<span class="chip">✕ ${t}</span>` : '';
      h += `<p class="lede">Relief centre${p.cap ? ` for <b>${esc(p.cap)}</b> people` : ''}.</p><div class="row" style="flex-wrap:wrap;gap:6px">${yn(p.cook, 'Cooking')}${yn(p.water, 'Drinking water')}${yn(p.toilet, 'Toilets')}</div>
        ${p.shift ? `<dl class="kv"><dt>For people from</dt><dd>${esc(p.shift)}</dd></dl>` : ''}
        ${cs.map(c => (c.phones || []).map(ph => tel(ph, c.role || 'Officer in charge')).join('')).join('')}
        <dl class="kv"><dt>Ward</dt><dd>${esc(p.ward ?? '—')} · ${zlabel(+p.zone)}</dd>${p.match ? `<dt>Mapped to</dt><dd>${esc(p.match)}</dd>` : ''}</dl>${precNote(p)}`;
    } else if (id === 'evacuation') {
      h += `<p class="lede">${p.kind === 'evacuate' ? 'People were evacuated from here in past floods.' : 'Water entered houses here in past monsoons; no evacuation was needed.'}</p>
        <dl class="kv">${p.area ? `<dt>Area</dt><dd>${esc(p.area)}</dd>` : ''}${p.persons ? `<dt>People moved</dt><dd>${esc(p.persons)}</dd>` : ''}${p.year ? `<dt>Year</dt><dd>${esc(p.year)}</dd>` : ''}
        ${p.centre ? `<dt>Relief centre</dt><dd>${esc(p.centre)}</dd>` : ''}<dt>Ward</dt><dd>${esc(p.ward ?? '—')} · ${zlabel(+p.zone)}</dd></dl>${precNote(p)}<h3>Who to call</h3>${engineer(w)}`;
    } else if (id === 'subways') {
      h += `<dl class="kv">${p.len ? `<dt>Length</dt><dd>${esc(p.len)} m</dd>` : ''}${p.pumps ? `<dt>Pumps</dt><dd>${esc(p.pumps)}</dd>` : ''}${p.disposal ? `<dt>Water goes to</dt><dd>${esc(p.disposal)}</dd>` : ''}
        ${p.ward ? `<dt>Ward</dt><dd>${esc(p.ward)} · ${zlabel(+p.zone)}</dd>` : ''}</dl>${precNote(p)}<p class="muted">Subways flood fast. Don't drive through standing water.</p>`;
    } else {
      h += `<dl class="kv">${p.loc && p.loc !== p.name ? `<dt>Location</dt><dd>${esc(p.loc)}</dd>` : ''}${p.details ? `<dt>Details</dt><dd>${esc(p.details)}</dd>` : ''}
        ${p.kind && id === 'ndrf' ? `<dt>Type</dt><dd>${p.kind === 'ndrf' ? 'NDRF team' : 'Rescue boat'}</dd>` : ''}<dt>Ward</dt><dd>${esc(p.ward ?? '—')} · ${zlabel(+p.zone)}</dd></dl>${precNote(p)}`;
    }
    if (w) h += `<button class="bigbtn ghost" id="toWard">Ward ${w} contacts</button>`;
    if (at) h += `<a class="bigbtn ghost" style="text-decoration:none" target="_blank" rel="noopener" href="https://www.google.com/maps/search/?api=1&query=${at[1]},${at[0]}">Open in Google Maps</a>`;
    render(h); setSheet('mid');
    $('#back') && ($('#back').onclick = () => { detailStack = []; openTab(current); });
    $('#toWard') && ($('#toWard').onclick = () => showWard(w, true));
    map.getSource('hl').setData({ type: 'FeatureCollection', features: at ? [{ type: 'Feature', geometry: { type: 'Point', coordinates: at }, properties: {} }] : [] });
    if (!at) return;
    if (fly) map.flyTo({ center: at, zoom: Math.max(map.getZoom(), 15), padding: pad() });
    else if (isMobile()) map.easeTo({ center: at, padding: pad() });
  }

  const ORDER = ['councillor', 'engineering', 'electrical', 'health', 'solid waste', 'cmwssb', 'tangedco', 'police', 'fire', 'revenue', 'veterinary', 'park', 'pwd', 'highways', 'tnscb', 'bsnl'];
  function keyContacts(wi) {
    const vac = !wi.councillor.length && /vacant/i.test(wi.councillor_printed || '');
    const out = [{ who: wi.councillor_name ? `Councillor ${wi.councillor_name}` : 'Ward councillor', sub: vac ? 'Post vacant (as printed)' : 'GCC ward councillor', ph: wi.councillor }];
    const rank = c => { const s = (c.dept + ' ' + c.role).toLowerCase(); const i = ORDER.findIndex(k => s.includes(k)); return i < 0 ? 99 : i; };
    const DEPT = [[/engineering/i, 'GCC engineer', 'Roads, drains, pumps'], [/electrical/i, 'GCC electrical', 'Street lights'],
      [/health/i, 'GCC health', 'Sanitation, fogging'], [/solid waste|conservancy/i, 'GCC conservancy', 'Garbage, fallen trees'],
      [/cmwssb|metro ?water/i, 'Metrowater (CMWSSB)', 'Water supply, sewage'], [/tangedco|tneb|electricity/i, 'TANGEDCO', 'Power cuts, live wires'],
      [/police/i, 'Police station', ''], [/fire/i, 'Fire station', 'Rescue'], [/gcc ?- ?revenue/i, 'GCC revenue', ''], [/^revenue/i, 'Revenue dept.', 'Relief, enumeration'],
      [/veterinary/i, 'GCC veterinary', 'Animals'], [/park/i, 'GCC parks', 'Trees in parks'], [/pwd/i, 'PWD', 'Rivers, canals, lakes'],
      [/highways/i, 'Highways dept.', 'Main roads, bridges'], [/tnscb|tnuhdb/i, 'TNUHDB (housing board)', 'Tenements'], [/bsnl/i, 'BSNL', 'Phone lines'], [/nhai/i, 'NHAI', '']];
    [...wi.contacts].sort((a, b) => rank(a) - rank(b)).forEach(c => {
      const d = DEPT.find(([re]) => re.test(c.dept)) || [null, c.dept, ''];
      out.push({ who: d[1], sub: [c.role, d[2]].filter(Boolean).join(' · '), ph: c.phones });
    });
    return out;
  }
  function engineer(w) {
    const wi = w && INFO.wards[w]; if (!wi) return '<p class="muted">Call 1913 (GCC helpline).</p>';
    const ae = wi.contacts.find(c => /engineering/i.test(c.dept)) || wi.contacts[0];
    return (ae ? ae.phones.map(ph => tel(ph, `${ae.role} · Ward ${w}`, 'GCC engineering')).join('') : '') + tel({ n: '1913', d: '1913' }, 'GCC helpline', '24 × 7');
  }

  function highlightWard(w) {
    selWard = w;
    for (const id of ['wards-sel', 'wards-sel-line']) map.getLayer(id) && map.setFilter(id, ['==', ['get', 'ward'], w || -1]);
  }
  function showWard(w, fly) {
    const wi = INFO.wards[w]; if (!wi) return;
    highlightWard(w);
    const cs = keyContacts(wi);
    const inW = id => pts(id).filter(f => +f.properties.ward === w);
    const withU = (id, fs, sortFn) => [...fs.map(f => ({ f, d: me ? dist(me, f.geometry.coordinates) : null })), ...unplacedIn(id, w)];
    const t = inW('tractors'), p = inW('pumps'), r = inW('relief'), fl = inW('flood_spots');
    const z = INFO.zones[wi.zone];
    const zo = z ? z.officials.filter(o => (o.phones || []).length).slice(0, 14) : [];
    render(`<button class="back" id="back">‹ Back</button><h2>Ward ${w}</h2><p class="lede">${zlabel(wi.zone)}</p>
      ${cs.map(c => (c.ph || []).map(ph => tel(ph, c.who, c.sub)).join('')).join('')}
      <p class="muted">Numbers as published in GCC's City Disaster Management Plan ${ED}${wi.page ? ` (PDF p. ${wi.page})` : ''}. Officers change; if a number fails, call 1913.</p>
      ${wi.office ? `<p class="muted">Ward office: ${esc(wi.office.name)}</p>` : ''}
      <h3>Tractor pumps in this division (${withU('tractors', t).length})</h3>${list('tractors', withU('tractors', t), true)}
      <h3>Diesel / RP pumps (${withU('pumps', p).length})</h3>${list('pumps', withU('pumps', p))}
      <h3>Relief centres (${withU('relief', r).length})</h3>${list('relief', withU('relief', r))}
      <h3>Flood-prone streets (${withU('flood_spots', fl).length})</h3>${list('flood_spots', withU('flood_spots', fl.sort((a, b) => b.properties.sev - a.properties.sev)))}
      ${zo.length ? `<details><summary>Zone ${ROMAN[wi.zone]} officials</summary>${zo.map(o => o.phones.map(ph => tel(ph, o.role, [o.wards, o.table].filter(Boolean).join(' · '))).join('')).join('')}</details>` : ''}`);
    bindList(); setSheet('mid');
    $('#back').onclick = () => openTab(current);
    if (fly) {
      const f = WARDS.features.find(f => f.properties.ward === w);
      const b = new maplibregl.LngLatBounds(); (f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates).forEach(pl => pl[0].forEach(c => b.extend(c)));
      map.fitBounds(b, { padding: pad(), maxZoom: 15.5 });
    }
    const mp = (location.hash.match(/m=[^&]*/) || [])[0];
    history.replaceState(null, '', location.pathname + location.search + '#ward=' + w + (mp ? '&' + mp : ''));
  }

  // ---------- layers tab
  function renderLayers() {
    render(`<h2>Map layers</h2><p class="lede">Tap to show or hide. Filled markers are placed on the street; hollow ones only at their ward.</p>
      ${LAYERS.map(l => `<div class="lyr ${l.on ? 'on' : ''}" data-id="${l.id}"><span class="sw" style="background:${l.color}">${l.letter || ''}</span>
        <span class="nm"><b>${esc(l.name)}</b><span>${esc(l.sub)}${DATA[l.id] && l.letter !== undefined ? ' · ' + pts(l.id).length : ''}</span></span><span class="tg"></span></div>`).join('')}
      <h3>Flood-prone streets</h3><div class="legend-bar">${SEV.slice(1).map(c => `<i style="background:${c}"></i>`).join('')}</div>
      <div class="row muted" style="justify-content:space-between"><span>stagnates</span><span>heavy rain</span><span>3–5 ft</span><span>&gt;5 ft, repeated</span></div>`);
    body.querySelectorAll('.lyr').forEach(el => el.onclick = () => {
      const l = L[el.dataset.id]; l.on = !l.on; el.classList.toggle('on', l.on); saveLayers();
      layerIds(l.id).forEach(id => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', vis(l.on)));
    });
  }
  function layerIds(id) {
    return { flood_spots: ['flood-fill', 'flood-line', 'flood-pt'], water: ['water-fill', 'water-line'], flood2015: ['flood2015-line'], swd: ['swd-line', 'swd-out'],
      wards: ['wards-line', 'ward-num'] }[id] || [id + '-c', id + '-t'];
  }

  function renderHelp() {
    const row = (who, nums, sub) => nums.map(n => tel(n, who, sub)).join('');
    const m = (d, n) => ({ n: '+91' + n.replace(/^0/, ''), d });
    render(`<h2>Helplines</h2>${hotline()}
      <h3>Control rooms</h3>
      ${row('State Emergency Operation Centre', [{ n: '1070', d: '1070' }, m('044 2841 0540', '04428410540'), m('044 2841 4550', '04428414550')], 'Toll free · CRA office')}
      ${row('State Relief Commissioner', [m('044 2852 4981', '04428524981')])}
      ${row('Police control room', [m('044 2345 2359', '04423452359')], 'Commissioner of Police')}
      ${row('Fire & Rescue Services', [m('044 2855 3101', '04428553101')])}
      ${row('Chennai Collectorate', [m('044 2522 8025', '04425228025')])}
      ${row('IMD Chennai', [m('044 2827 1951', '04428271951')], 'Weather office')}
      ${row('Indian Coast Guard', [m('044 2539 1718', '04425391718')])}
      ${row('Home Guards', [m('94433 12255', '9443312255')])}
      <h3>Ambulance &amp; hospitals</h3>
      ${row('Traffic police', [{ n: '103', d: '103' }])}${row('Fire services ambulance', [{ n: '102', d: '102' }])}
      ${row('Government General Hospital', [m('044 2530 5000', '04425305000')])}${row('Govt. Stanley Hospital', [m('044 2528 1347', '04425281347')])}
      ${row('Govt. Kilpauk Hospital', [m('044 2836 4951', '04428364951')])}${row('Govt. Royapettah Hospital', [m('044 2848 3051', '04428483051')])}
      ${row('Institute of Child Health', [m('044 2819 1135', '04428191135')])}${row('Kasturba Hospital for Women', [m('044 2854 5449', '04428545449')])}
      ${row('Child helpline', [{ n: '1098', d: '1098' }])}${row('Women helpline', [{ n: '1091', d: '1091' }])}
      ${row('Blue Cross (animals)', [m('044 2235 4959', '04422354959')])}
      <p class="muted">From GCC's City Disaster Management Plan, Appendix I, plus 1913, GCC's 24×7 helpline.</p>`);
  }

  function renderLive() {
    const card = (href, color, icon, t, s) => `<a class="card live" href="${href}" target="_blank" rel="noopener"><span class="ic" style="background:${color}">${icon}</span><span><b>${t}</b><br><span class="muted">${s}</span></span></a>`;
    render(`<h2>Rain, radar &amp; lakes</h2><p class="lede">Live feeds we run alongside this map.</p>
      ${card('https://pol.reclaimchennai.city', '#1c7ed6', '<svg viewBox="0 0 24 24"><path d="M20 16.6A5 5 0 0 0 18 7h-1.3A8 8 0 1 0 4 15.3"/><path d="M8 19v2M8 13v2M16 19v2M16 13v2M12 21v2M12 15v2"/></svg>', 'Weather, radar &amp; satellite', 'pol.reclaimchennai.city · rain now, radar loop, cloud imagery')}
      ${card('https://water.reclaimchennai.city', '#0b7285', '<svg viewBox="0 0 24 24"><path d="M2 12h20M2 17c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2M12 3l4 6H8z"/></svg>', 'Reservoir levels', 'water.reclaimchennai.city · Chembarambakkam, Puzhal, Poondi… and releases')}
      ${card('https://maps.reclaimchennai.city/chn/', '#495057', '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>', 'Chennai from space', 'Latest satellite passes over the city')}
      <div class="warnbox">When reservoirs release surplus water, streets along the Adyar and Kosasthalaiyar and near the Buckingham Canal flood first. Watch the release figures.</div>`);
  }

  function renderAbout() {
    const k = (f, n, c) => `<a class="call" href="kml/${f}.kml" download><span class="ph" style="background:${c}"><svg viewBox="0 0 24 24"><path d="M12 3v12M6 11l6 6 6-6M4 21h16"/></svg></span><span class="who"><b>${n}</b><span>KML · import into Google My Maps</span></span></a>`;
    render(`<h2>Data &amp; downloads</h2>
      <h3>Use it in Google Maps</h3><p class="lede">Each file is one My Maps layer (a map holds up to 10 layers). In <a href="https://www.google.com/maps/d/" target="_blank" rel="noopener">Google My Maps</a>: Create a new map → Import → pick a file. Share the map; it opens in the Google Maps app.</p>
      ${k('tractor_pumps', 'Tractor pumps', '#e8590c')}${k('diesel_pumps', 'Diesel & RP pumps', '#6741d9')}${k('flood_prone_streets', 'Streets that flooded (2015–23)', '#d6336c')}${k('water_stagnation_streets', 'Streets where water stagnates', '#f59f00')}
      ${k('relief_centres', 'Relief centres', '#2f9e44')}${k('subways', 'Subways', '#1c7ed6')}${k('evacuation_streets', 'Evacuation-prone streets', '#ae3ec9')}
      ${k('assembly_points', 'Assembly points & parks', '#0ca678')}${k('ndrf_boats', 'NDRF teams & boats', '#f08c00')}${k('ward_contacts', 'Ward contacts (200 wards)', '#495057')}
      <h3>Where this comes from</h3>
      <dl class="kv"><dt>Tractor pumps</dt><dd>GCC line list of tractor pumps (510 rows; rows 187–233 not yet received)</dd>
      <dt>Diesel / RP pumps</dt><dd>GCC list of pumps placed in 151 flood-prone spots, with GPS install dates</dd>
      <dt>Flood spots, subways, relief, wards</dt><dd>GCC City Disaster Management Plan ${ED}: every table extracted by one script (year-wise inundation tables and the 15 zone chapters)</dd>
      <dt>Storm drains</dt><dd>GCC SWD sheets traced by @reclaimchennai (<a href="https://swd.reclaimchennai.city" target="_blank" rel="noopener">swd.reclaimchennai.city</a>)</dd>
      <dt>Streets, places</dt><dd>© OpenStreetMap contributors</dd><dt>Water bodies</dt><dd>TNGIS</dd><dt>2015 floods</dt><dd>osm-in/flood-map</dd></dl>
      <h3>How exact is it?</h3><p class="muted">The lists name a street or locality, not coordinates. Each one was matched, inside its own ward, against GCC's street names and TNGIS places (schools, parks, playgrounds, community halls, ward offices, landmarks), then OpenStreetMap. Filled markers sit on the matched street or place; hollow rings sit at the centre of the matched neighbourhood. Anything that could not be matched is not drawn at a guessed spot: it is listed under its ward and in search. Phone numbers are shown as printed. Numbers that can't be dialled as printed are greyed out.</p>
      <p class="muted">A project of <b>@reclaimchennai</b>. Spot a wrong number or location? Tell us so it can be fixed for everyone.</p>`);
  }

  // ---------- search
  let INDEX = [];
  function buildSearch() {
    INDEX = [];
    for (const id of ['tractors', 'pumps', 'relief', 'subways', 'flood_spots', 'evacuation', 'assembly', 'ndrf']) {
      (DATA[id] ? DATA[id].features : []).forEach((f, i) => {
        if (f.properties.line) return;
        const p = f.properties;
        const hay = [title(id, p), p.tractor, p.driver, p.pump, p.match, p.loc, p.name, (prop(p, 'phones') || []).map(x => x.d).join(' ')].filter(Boolean).join(' ').toLowerCase();
        INDEX.push({ id, i, hay });
      });
    }
    UNPLACED.forEach((u, k) => INDEX.push({ id: u.layer, i: 'u' + k, hay: [title(u.layer, u), u.tractor, u.driver, u.pump, u.loc, u.name].filter(Boolean).join(' ').toLowerCase() }));
  }
  const q = $('#q'), res = $('#results');
  $('#searchbtn').onclick = () => { document.body.classList.toggle('searching'); $('#searchbtn').classList.toggle('on'); if (document.body.classList.contains('searching')) setTimeout(() => q.focus(), 30); };
  q.oninput = () => {
    const s = q.value.trim().toLowerCase(); if (s.length < 2) { res.innerHTML = ''; return; }
    const out = [];
    const wm = s.match(/^(?:ward\s*)?(\d{1,3})$/);
    if (wm && +wm[1] >= 1 && +wm[1] <= 200) out.push(`<div class="res" data-w="${+wm[1]}"><span class="dot" style="background:#495057;width:26px;height:26px;border-radius:50%"></span><span><span class="t">Ward ${+wm[1]}</span><div class="s">${ZN[INFO.wards[+wm[1]].zone - 1]} zone · contacts &amp; pumps</div></span></div>`);
    const terms = s.split(/\s+/);
    INDEX.filter(x => terms.every(t => x.hay.includes(t))).slice(0, 14).forEach(x => {
      const f = String(x.i)[0] === 'u' ? { properties: UNPLACED[+x.i.slice(1)] } : DATA[x.id].features[x.i], p = f.properties;
      out.push(`<div class="res" data-l="${x.id}" data-i="${x.i}">${dot(x.id, p)}<span><span class="t">${esc(title(x.id, p))}</span><div class="s">${esc(subtitle(x.id, p))}</div></span></div>`);
    });
    res.innerHTML = out.join('') || '<div class="res"><span class="s">Nothing found. Try a street name, ward number, tractor number or driver.</span></div>';
    res.querySelectorAll('.res[data-l]').forEach(el => el.onclick = () => {
      closeSearch();
      if (el.dataset.i[0] === 'u') return showDetail(el.dataset.l, UNPLACED[+el.dataset.i.slice(1)], null, false);
      const f = DATA[el.dataset.l].features[+el.dataset.i]; showDetail(el.dataset.l, f.properties, f.geometry.coordinates, true);
    });
    res.querySelectorAll('.res[data-w]').forEach(el => el.onclick = () => { closeSearch(); showWard(+el.dataset.w, true); });
  };
  q.onkeydown = e => { if (e.key === 'Enter') { const r = res.querySelector('.res[data-l],.res[data-w]'); r && r.click(); } if (e.key === 'Escape') closeSearch(); };
  function closeSearch() { document.body.classList.remove('searching'); $('#searchbtn').classList.remove('on'); q.blur(); }

  // ---------- deep links
  function route() {
    // deep links: #ward=113  ·  #near=13.0418,80.2410 (show 'Near me' for a spot)  ·  #item=tractors:T12
    const m = location.hash.match(/ward=(\d+)/), n = location.hash.match(/near=(-?[\d.]+),(-?[\d.]+)/), it = location.hash.match(/item=(\w+):(\w+)/);
    openTab('near');
    if (n) { setMe([+n[2], +n[1]]); return; }
    if (it && DATA[it[1]]) {
      const f = DATA[it[1]].features.find(f => String(f.properties.id) === it[2]);
      if (f) return showDetail(it[1], f.properties, f.geometry.coordinates, true);
    }
    if (m) showWard(+m[1], true);
  }
  function setMe(at) {
    me = at;
    if (!meMarker) { const el = document.createElement('div'); el.className = 'me'; meMarker = new maplibregl.Marker({ element: el }); }
    meMarker.setLngLat(me).addTo(map);
    map.jumpTo({ center: me, zoom: Math.max(map.getZoom(), 14.5), padding: pad() });
    highlightWard(wardAt(me));
    openTab('near'); setSheet('mid');
  }
})();
