"""
dashboard/map_embed.py
======================
Prepare sg_map.html for embedding inside Streamlit.

The map page normally fetches /planning_areas.geojson from FastAPI. Inside
the Streamlit iframe that only works while the live pipeline is running —
but the polygon file sits right next to the map on disk, so we inline it at
embed time and the district borders render in every state.
"""
from pathlib import Path

GEOJSON_PLACEHOLDER = "let INLINE_GEOJSON = null; /*__INLINE_GEOJSON__*/"
COLOR_MODE_PLACEHOLDER = 'let MAP_COLOR_MODE = "vfm"; /*__MAP_COLOR_MODE__*/'
VFM_WEIGHT_PLACEHOLDER = "let MAP_VFM_WEIGHT = 0.5; /*__MAP_VFM_WEIGHT__*/"


def load_map_html(map_path: Path, geojson_path: Path,
                   color_mode: str = "vfm", vfm_weight: float = 0.5) -> str | None:
    """Read sg_map.html, inlining the local planning-area GeoJSON if present.

    color_mode: "vfm" colors districts by Value-for-Money (transit blended
    with resale-price affordability) — used on the Map & Housing Prices tab.
    "connectivity" keeps raw transit-only coloring — used on the Overview
    tab's mini map, which sits next to the plain Connectivity Score gauge and
    should match that number rather than a blended one.
    vfm_weight: transport weight (0-1) passed through to the /vfm call so the
    map's colors track the "Transport importance %" slider — the caller must
    re-embed (call this again) whenever that slider moves, since the map is a
    static HTML blob with no live link back to the Streamlit widget state.

    Returns the HTML string, or None when the map file itself is missing.
    Leaves the geojson placeholder (null fallback → API fetch) if that file
    is absent or unreadable.
    """
    try:
        html = Path(map_path).read_text(encoding="utf-8")
    except OSError:
        return None
    html = html.replace(COLOR_MODE_PLACEHOLDER,
                        f'let MAP_COLOR_MODE = "{color_mode}";')
    html = html.replace(VFM_WEIGHT_PLACEHOLDER,
                        f"let MAP_VFM_WEIGHT = {vfm_weight};")
    try:
        geojson_text = Path(geojson_path).read_text(encoding="utf-8").strip()
    except OSError:
        return html
    if not geojson_text:
        return html
    return html.replace(GEOJSON_PLACEHOLDER,
                        f"let INLINE_GEOJSON = {geojson_text};")
