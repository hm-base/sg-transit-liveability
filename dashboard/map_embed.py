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


def load_map_html(map_path: Path, geojson_path: Path) -> str | None:
    """Read sg_map.html, inlining the local planning-area GeoJSON if present.

    Returns the HTML string, or None when the map file itself is missing.
    Leaves the placeholder (null fallback → API fetch) if the geojson file
    is absent or unreadable.
    """
    try:
        html = Path(map_path).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        geojson_text = Path(geojson_path).read_text(encoding="utf-8").strip()
    except OSError:
        return html
    if not geojson_text:
        return html
    return html.replace(GEOJSON_PLACEHOLDER,
                        f"let INLINE_GEOJSON = {geojson_text};")
