# Chennai monsoon map: data build

Builds the data for **maps.reclaimchennai.city/monsoon**. The web app lives in `maps-site/monsoon/`.

## Sources (`raw/`)
| file | what |
|---|---|
| `11–20.webp` | GCC "Line list of tractor pump" screenshots: S.No, tractor no., driver, mobile, location, zone, division. **Rows 187–233 are not in the screenshots.** |
| `21–25` | GCC list of diesel (DL-) / RP pumps placed in 151 flood-prone spots, with GPS install dates |
| `cdmp_2024-compressed.pdf` | GCC City Disaster Management Plan 2024 (807 pp.; PDF page = printed page + 19). Not committed (44 MB). |
| `osm/` | named streets / points / polygons over Chennai cut from the India PBF on the server (`~/projects/monsoon/osm/cut*.sh`) |
| `swd/network.json` | storm-water-drain network from swd.reclaimchennai.city |

## Pipeline
1. `build/ocr_tables.py`: finds the ruled grid in each screenshot and runs tesseract cell by cell (`build/ocr/*.json`).
2. `build/tractors_csv.py` and `build/pumps_csv.py` → `data/tractor_pumps.csv` and `data/diesel_pumps.csv`.
   - Plate and phone normalisation.
   - Manual fixes read off the images, listed in the `FIX`/`LOC` dicts.
   - `build/ocr_phone_check.py` is a second, independent digit-only OCR of the phone column. It disagreed on 2 of 463 rows, and both were resolved by eye.
   - Numbers that are invalid as printed are kept and flagged (`note`).
3. `build/parse_wards.py` reads the ward-committee tables (pdfplumber cells) and writes `data/ward_contacts.json`.
   - 199 wards. Ward 191's table is missing from the PDF.
   - Source typos such as "Ward Committee – 311" are mapped back to the right ward via the councillor's 9445467NNN number.
4. `build/parse_flood.py` reads the §4.2 inundation tables (2015, 2017–2023) with their depth class and writes `data/inundation_rows.json` (1,239 rows).
   - The 2022 detail table is mis-titled "2021" in the source.
5. `build/zones/zone_NN.json` holds the 15 zone appendices: relief centres, subways, evacuation streets, stagnation, NDRF/boats, parks, officials.
   - They were transcribed from `zone_NN.txt` against `SCHEMA.md`.
   - Every phone was checked against the text in both directions, and the hard tables against page renders.
   - Each file's `notes` lists source inconsistencies.
6. `build/geocode.py` places each free-text location inside its GCC ward (karthi209 `gcc-divisions-latest`).
   - It tries an OSM street of that name first, then an OSM place or POI.
   - It retries cleaned variants ("X Nagar 8th Street" → "X Nagar"; lists split on `,` / `&`).
   - Guards: a match must share a distinctive word with the query, and street numbers must agree. Generic names like "4th Cross Street" never match.
   - Results are tagged `prec`: `street` / `place` / `area` (locality only) / `office` (division office) / `ward` (not found).
7. `build/build_layers.py` → `web/data/*.geojson` + `wards_info.json`. Unmatched items are listed in `build/unmapped.csv`.
8. `build/export_kml.py` → `web/kml/*.kml`: one file per Google My Maps layer, ≤2,000 features each, 10 files = one My Maps map.

`build/run_all.sh` reruns steps 2, 7 and 8 and copies the output into maps-site.

## Feeding new information
- **More tractor rows** (e.g. 187–233): add them to `data/tractor_pumps.csv` (same columns), or OCR the screenshot with `ocr_tables.py` and extend `tractors_csv.py`. Then run `build/run_all.sh`.
- **More pumps**: same, via `data/diesel_pumps.csv`.
- **Fixing a location**: if a street isn't on OSM, the item stays a hollow ward marker. Add a better location string in the CSV, or an alias in `geocode.py` (`ALIAS`).

Data: GCC (lists, CDMP 2024), © OpenStreetMap contributors (ODbL), TNGIS water bodies, osm-in/flood-map, @reclaimchennai SWD extraction.
