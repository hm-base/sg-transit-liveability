import json

print("Loading planning areas...")
with open('planning_areas.json', 'r') as f:
    polygons = json.load(f)
print(f"Loaded {len(polygons)} areas")

with open('dashboard/sg_liveability.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Embed polygons as JS constant
js_data = 'const ONEMAP_POLYGONS = ' + json.dumps(polygons) + ';'

# Inject before addFallbackBoxes
html = html.replace('function addFallbackBoxes(){', js_data + '\n\nfunction addFallbackBoxes(){')

# Replace loadPlanningAreas to use real polygons
old = 'async function loadPlanningAreas(){\n  addFallbackBoxes();\n}'
new = '''async function loadPlanningAreas(){
  Object.entries(ONEMAP_POLYGONS).forEach(([paName, geojsonStr]) => {
    try {
      const distName = Object.entries(PA_NAME_MAP).find(([k,v]) => v===paName.toUpperCase())?.[0];
      const d = DISTRICTS.find(x=>x.name===distName);
      const color = d ? scoreColor(d.score) : "#94a3b8";
      const geojson = typeof geojsonStr==="string" ? JSON.parse(geojsonStr) : geojsonStr;
      L.geoJSON(geojson,{
        style:{color,weight:2,opacity:0.85,fill:true,fillColor:color,fillOpacity:0.08,dashArray:"5,4"}
      }).addTo(map);
    } catch(e){ console.log(e); }
  });
}'''

html = html.replace(old, new)

with open('dashboard/sg_liveability.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Done! 55 real polygon shapes embedded permanently into sg_liveability.html")
