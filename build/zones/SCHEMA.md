# Zone extraction schema (Chennai CDMP 2024, zone appendix)

Input: build/zones/zone_NN.txt — `pdftotext -layout` text of one zone's appendix, pages marked
`##### PDF page N`. Ward-committee pages were removed (parsed separately). Map pages show only a title.
Tables are multi-line: a cell's text can wrap onto lines above/below the row number. Re-join it.

Output: build/zones/zone_NN.json, one object:

{
  "zone": 1, "zone_name": "Thiruvottiyur",
  "zonal_office": {"address": "...", "phones": ["..."]},          // if given
  "officials": [ {"designation": "...", "name": "...", "wards": "1 to 14", "phones": ["9445190001"], "category": "zone|ward|electrical|health|medical|police|fire|other"} ],
  "inundation_streets": [ {"ward": 7, "street": "Radhakrishna Nagar", "max_depth": "2 Feet", "days_to_drain": "2 days",
                           "pump": "6.5 HP Diesel", "pump_location": "...", "disposal_point": "Kargil nagar drain", "page": 204} ],
  "water_stagnation": [ {"ward": 1, "street": "SVM Nagar", "rain": "mild|moderate|heavy|sewer_block", "page": 208} ],
  "relief_centres": [ {"ward": 1, "name": "Govt. Higher Sec. School, Kathivakkam", "capacity": 300,
                       "streets_to_shift": "Thalankuppam, Nettukuppam", "cooking": true, "drinking_water": true, "toilets": false,
                       "contacts": [{"designation": "Assistant Engineer", "phones": ["9445190301"]}], "page": 209} ],
  "subways": [ {"ward": 5, "name": "Manickkam Nagar subway", "length_m": 60, "disposal_point": "Railway pond", "pumps": "...", "page": 213} ],
  "evacuation_streets": [ {"ward": 4, "area": "Ernavoor", "streets": "A.D Colony", "persons": 300, "year": "2015",
                           "relief_centre": "Mahaliaman koil school st", "needs_evacuation": true, "page": 215} ],
  "water_entered_houses": [ {"ward": 0, "street": "...", "page": 214} ],      // "streets where water entered houses but do not require evacuation"
  "tree_fall": [ {"ward": 1, "street": "JJ nagar"} ],
  "ndrf_boats": [ {"ward": 4, "location": "...", "kind": "ndrf|boat", "details": "..."} ],
  "parks_assembly": [ {"ward": 19, "name": "Hansa Garden Park", "location": "Ajax TVT"} ],     // parks/playgrounds lists
  "hospitals": [ {"ward": 0, "name": "...", "phones": ["..."], "kind": "UPHC|hospital|..."} ],
  "pumping_stations": [ {"ward": 0, "name": "...", "capacity_mld": 0} ],
  "notes": ["anything important that does not fit, e.g. 'tables for X were missing'"]
}

Rules
- Copy names and phone numbers EXACTLY as printed. Never invent, normalise or "fix" a number.
  Phones: digits only, landlines keep their prefix e.g. "044-25993412". A cell with two numbers -> two entries.
- After writing, grep the zone text for every phone in your JSON to prove it exists (a quick Python check is fine).
- Use null for anything not given. Ward as an integer when a single ward; keep a string like "4, 5 & 8" otherwise.
- Include every row of every such table in the zone (all pages), not samples.
- `page` = the PDF page from the `##### PDF page N` marker.
- Valid JSON (json.load must succeed).
