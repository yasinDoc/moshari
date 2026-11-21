from __future__ import annotations

import pytest

from moshari import config as C

pytest.importorskip("fastapi")
pytestmark = pytest.mark.skipif(not C.MODEL_PATH.exists(), reason="model not trained")

from fastapi.testclient import TestClient  # noqa: E402

from moshari.api import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/health").json()
    assert r["status"] == "ok" and r["wards"] == 60


def test_forecast_filters_by_tier_and_city():
    allw = client.get("/forecast", params={"issue_date": "2025-06-02", "horizon": 3}).json()
    high = client.get("/forecast", params={"issue_date": "2025-06-02", "horizon": 3, "min_tier": "High"}).json()
    dhaka = client.get("/forecast", params={"issue_date": "2025-06-02", "city": "Dhaka North"}).json()
    assert len(allw) == 60
    assert 0 < len(high) < 60 and all(r["tier"] in ("High", "Critical") for r in high)
    assert len(dhaka) == 20


def test_outlook_explain_and_scenario():
    o = client.get("/wards/CCC_Ward_01/outlook", params={"issue_date": "2025-06-02"}).json()
    assert [r["horizon_weeks"] for r in o] == [2, 3, 4]
    e = client.get("/wards/CCC_Ward_01/explain", params={"issue_date": "2025-06-02"}).json()
    assert e["drivers"][0]["multiplier"] > 1
    s = client.post("/scenario", json={"ward_id": "CCC_Ward_01", "issue_date": "2025-06-02", "rain_factor": 2.5}).json()
    assert s[1]["expected_cases"] > o[1]["expected_cases"]


def test_bad_inputs_get_clear_errors():
    assert client.get("/wards/NOPE/outlook").status_code == 404
    assert client.get("/forecast", params={"horizon": 7}).status_code == 422
    assert client.get("/forecast", params={"issue_date": "2019-01-02"}).status_code == 422


def test_alerts_only_and_policy():
    cau = client.get("/forecast", params={"issue_date": "2025-06-02", "alerts_only": True}).json()
    std = client.get("/forecast", params={"issue_date": "2025-06-02", "alerts_only": True,
                                          "alert_policy": "Standard"}).json()
    assert all(r["alert"] for r in cau) and len(cau) >= len(std)
    assert client.get("/forecast", params={"alert_policy": "Reckless"}).status_code == 422
