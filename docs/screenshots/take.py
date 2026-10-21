"""Re-take the README screenshots: python docs/screenshots/take.py [base-url]
Needs `pip install playwright` and a local Google Chrome (channel='chrome')."""
import sys, os
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'https://maps.reclaimchennai.city/monsoon/'
OUT = os.path.dirname(os.path.abspath(__file__))
SHOTS = [('desktop_ward.png', {'width': 1440, 'height': 900}, 1, '#ward=113'),
         ('mobile_near_me.png', {'width': 390, 'height': 844}, 2, '#near=13.0418,80.2410'),
         ('mobile_tractor.png', {'width': 390, 'height': 844}, 2, '#item=tractors:T7')]
with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    for name, vp, scale, h in SHOTS:
        ctx = b.new_context(viewport=vp, device_scale_factor=scale, is_mobile=scale > 1, has_touch=scale > 1)
        pg = ctx.new_page()
        pg.goto(BASE + '?shot=1' + h, wait_until='networkidle')
        pg.wait_for_selector('#loader.gone', state='attached', timeout=60000)
        pg.wait_for_timeout(9000)               # basemap tiles + fly animation
        pg.screenshot(path=f'{OUT}/{name}')
        ctx.close()
        print('saved', name)
    b.close()
