import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.map_embed import load_map_html, GEOJSON_PLACEHOLDER

FAKE_MAP = f"""<html><script>
const API_BASE = "x";
{GEOJSON_PLACEHOLDER}
loadDistricts();
</script></html>"""

FAKE_GEOJSON = '{"type": "FeatureCollection", "features": []}'


def test_injects_geojson_when_both_files_exist(tmp_path):
    map_p = tmp_path / "map.html"
    geo_p = tmp_path / "areas.geojson"
    map_p.write_text(FAKE_MAP, encoding="utf-8")
    geo_p.write_text(FAKE_GEOJSON, encoding="utf-8")

    out = load_map_html(map_p, geo_p)
    assert out is not None
    assert GEOJSON_PLACEHOLDER not in out
    assert 'let INLINE_GEOJSON = {"type": "FeatureCollection"' in out


def test_returns_html_unchanged_when_geojson_missing(tmp_path):
    map_p = tmp_path / "map.html"
    map_p.write_text(FAKE_MAP, encoding="utf-8")

    out = load_map_html(map_p, tmp_path / "nope.geojson")
    assert out is not None
    assert GEOJSON_PLACEHOLDER in out  # placeholder left = null fallback


def test_returns_none_when_map_missing(tmp_path):
    assert load_map_html(tmp_path / "nope.html", tmp_path / "x.geojson") is None


def test_real_files_inject():
    root = Path(__file__).parent.parent / "dashboard"
    out = load_map_html(root / "sg_map.html", root / "planning_areas.geojson")
    assert out is not None
    assert "let INLINE_GEOJSON = {" in out
