"""Ward map: the outline data, the SVG renderer and the page.

The map draws the dataset's 60 wards on real ward outlines (geoBoundaries, see
scripts/build_ward_map.py). These tests check the committed data file covers exactly the
dataset's wards, that ward_map_html colours, links and titles every ward from the forecast it is
given, and that the page renders in the real app.
"""

from __future__ import annotations

import html
import importlib.util
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from moshari import config as C
from ui import theme, wardmap

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")
LINK = {"issue": "2024-07-01", "h": "4"}
ELEMENT = re.compile(r'<(path|circle)\b([^>]*)\bdata-ward="([^"]+)"([^>]*)>(?:<title>(.*?)</title>)?', re.S)


def _build_module():
    spec = importlib.util.spec_from_file_location("build_ward_map", ROOT / "scripts" / "build_ward_map.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def build():
    return _build_module()


@pytest.fixture(scope="module")
def dataset_wards(raw) -> list[str]:
    return sorted(raw[C.WARD_COL].unique())


@pytest.fixture(scope="module")
def data() -> dict:
    return wardmap.load_map.__wrapped__(wardmap.MAP_PATH)


def _forecast(wards: list[str], shift: int = 0) -> pd.DataFrame:
    """A forecast table whose tiers rotate through the four tiers in a known pattern."""
    rows = []
    for i, w in enumerate(wards):
        t = (i + shift) % 4
        rows.append({"ward_id": w, "tier_idx": t, "tier": C.TIER_NAMES[t], "expected_cases": i + 0.25,
                     "lower_80": 0.0, "upper_80": i + 2.0})
    return pd.DataFrame(rows)


def _elements(out: str) -> dict[str, dict]:
    found = {}
    for kind, before, ward, after, title in ELEMENT.findall(out):
        attrs = before + after
        fill = re.search(r'fill="([^"]+)"', attrs).group(1)
        found[ward] = {"kind": kind, "fill": fill, "title": html.unescape(title or "")}
    return found


def _hrefs(out: str) -> dict[str, dict]:
    links = {}
    for href in re.findall(r'<a href="([^"]+)"', out):
        u = urlparse(html.unescape(href))
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        links[q.get("ward", "")] = {"path": u.path, **q}
    return links


# --------------------------------------------------------------------------- the data file
def test_data_file_has_exactly_the_dataset_wards(data, dataset_wards):
    ids = [w["ward_id"] for p in data["panels"] for w in p["wards"] + p["dots"]]
    assert sorted(ids) == dataset_wards
    assert len(ids) == len(set(ids)) == 60


def test_wards_sit_on_the_real_ward_the_placement_rule_names(data):
    expected = {}
    for i in range(1, 21):
        expected[f"DNCC_Ward_{i:02d}"] = i
        expected[f"DSCC_Ward_{i:02d}"] = 36 + i
    expected |= {f"CCC_Ward_{i:02d}": i for i in range(1, 11)}
    got = {w["ward_id"]: w["real_ward"] for p in data["panels"] for w in p["wards"]}
    assert got == expected


def test_every_outline_is_a_closed_path_inside_its_panel(data):
    num = re.compile(r"-?\d+(?:\.\d+)?")
    for p in data["panels"]:
        for w in p["wards"]:
            d = w["d"]
            assert d.startswith("M") and d.endswith("Z"), w["ward_id"]
            vals = [float(v) for v in num.findall(d)]
            xs, ys = vals[0::2], vals[1::2]
            assert len(xs) >= 4, f"{w['ward_id']} has too few vertices"
            assert 0 <= min(xs) and max(xs) <= p["width"], w["ward_id"]
            assert 0 <= min(ys) and max(ys) <= p["height"], w["ward_id"]
        for dot in p["dots"]:
            x, y = dot["xy"]
            assert 0 <= x <= p["width"] and 0 <= y <= p["height"], dot["ward_id"]
    outlines = [w["d"] for p in data["panels"] for w in p["wards"]]
    assert len(set(outlines)) == len(outlines), "two wards share one outline"


def test_data_file_credits_the_source_and_stays_small(data):
    assert "geoBoundaries" in data["source"] and "CC BY" in data["source"]
    assert wardmap.MAP_PATH.stat().st_size < 100 * 1024


# --------------------------------------------------------------------------- the renderer
@pytest.mark.parametrize("shift", [0, 1, 2, 3])
def test_each_ward_is_coloured_by_its_own_tier(dataset_wards, shift):
    fc = _forecast(dataset_wards, shift)
    els = _elements(wardmap.ward_map_html(fc, link=LINK))
    assert set(els) == set(dataset_wards)
    for r in fc.itertuples():
        assert els[r.ward_id]["fill"] == theme.TIER_COLORS[r.tier], (r.ward_id, r.tier)


def test_gazipur_and_narayanganj_wards_are_dots(dataset_wards):
    els = _elements(wardmap.ward_map_html(_forecast(dataset_wards)))
    for w, e in els.items():
        assert e["kind"] == ("circle" if w.startswith(("GCC", "NCC")) else "path"), w


def test_every_ward_links_to_its_forecast_with_the_same_settings(dataset_wards):
    out = wardmap.ward_map_html(_forecast(dataset_wards), link=LINK)
    links = _hrefs(out)
    assert set(links) == set(dataset_wards)
    for w, q in links.items():
        assert q["path"] == "ward_forecast" and q["issue"] == "2024-07-01" and q["h"] == "4", w
    assert 'target="_self"' in out


def test_without_a_link_the_map_has_no_links(dataset_wards):
    out = wardmap.ward_map_html(_forecast(dataset_wards), link=None)
    assert "<a " not in out and "href" not in out
    assert len(_elements(out)) == 60


def test_titles_name_the_ward_tier_and_expected_cases(dataset_wards):
    fc = _forecast(dataset_wards)
    els = _elements(wardmap.ward_map_html(fc))
    for r in fc.itertuples():
        t = els[r.ward_id]["title"]
        assert r.tier in t and f"{r.expected_cases:.1f} expected cases" in t, t


def test_filtered_out_city_is_grey_dimmed_and_unlinked(dataset_wards):
    kept = [w for w in dataset_wards if not w.startswith("CCC")]
    out = wardmap.ward_map_html(_forecast(kept), link=LINK)
    assert not any(w.startswith("CCC") for w in _elements(out))
    assert not any(w.startswith("CCC") for w in _hrefs(out))
    assert out.count(f'fill="{wardmap.NO_DATA_FILL}"') == 10
    assert re.search(r'class="pn dim"[^>]*><div class="t">Chattogram<', out)
    assert "Not selected in the sidebar" in out


def test_map_carries_the_source_note_and_tier_legend(dataset_wards):
    out = wardmap.ward_map_html(_forecast(dataset_wards), thresholds=[5, 15, 40])
    assert "illustrative" in out and "geoBoundaries" in out and "CC BY 3.0 IGO" in out
    for n in C.TIER_NAMES:
        assert f"<b>{n}</b>" in out
    assert "40+ cases" in out


# --------------------------------------------------------------------------- the build script geometry
def test_simplify_keeps_corners_and_drops_near_straight_points(build):
    line = [(0, 0), (1, 0.00001), (2, 0), (2, 2)]
    assert build.simplify(line, tol=0.001) == [(0, 0), (2, 0), (2, 2)]
    square = [[0, 0], [0.5, 0], [1, 0], [1, 1], [0, 1]]
    assert len(build.simplify_ring(square, tol=0.001)) == 4


def test_inside_and_dots_fall_inside_the_outline(build):
    ring = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]]          # an L shape
    assert build.inside((0.5, 3), ring) and not build.inside((3, 3), ring)
    dots = build.dots_inside([ring], 5)
    assert len(dots) == 5
    assert all(build.inside(p, ring) for p in dots)


# --------------------------------------------------------------------------- the page
@pytest.mark.skipif(not C.MODEL_PATH.exists(), reason="model not trained")
def test_page_renders_the_map_in_the_app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=180)
    at.query_params["issue"] = "2024-07-01"
    at.query_params["h"] = "4"
    at.switch_page("ui/views/ward_map.py")
    at.run()
    assert not at.exception, at.exception
    page = "\n".join(e.value for e in at.get("html"))
    # The map must go through st.markdown: st.html sanitises in the browser and strips inline
    # <svg>, so a map sent through st.html shows only the panel titles.
    md = "\n".join(m.value for m in at.markdown)
    assert "Ward map" in page
    assert len(set(re.findall(r'data-ward="([^"]+)"', md))) == 60
    assert "data-ward" not in page
    page += md
    assert "geoBoundaries" in page and "illustrative" in page
