"""Moshari REST API: the same ForecastService the dashboard uses, over HTTP.

    pip install -r requirements-api.txt
    uvicorn moshari.api:app --app-dir src --port 8000
    # docs at http://localhost:8000/docs

Model and features load once at startup; responses for repeated queries are
served from an in-process LRU cache, so a city dashboard polling every few
minutes costs one model call per distinct query.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import __version__
from . import config as C
from .data import load_dataset
from .model import ForecastBundle
from .risk import ALERT_POLICIES, DEFAULT_ALERT_POLICY, TIERS
from .service import ForecastService, Scenario

app = FastAPI(
    title="Moshari API",
    version=__version__,
    description="Ward-level dengue early warning for Dhaka, Chattogram, Gazipur and Narayanganj.",
)


@lru_cache(maxsize=1)
def service() -> ForecastService:
    return ForecastService(load_dataset(), ForecastBundle.load())


# --------------------------------------------------------------------------- schemas
class WardForecast(BaseModel):
    ward_id: str
    city: str
    issue_date: date
    target_date: date
    horizon_weeks: int
    expected_cases: float
    lower_80: float
    upper_80: float
    tier: str
    upside_tier: str
    response: str
    alert: bool = Field(False, description="On the watch list under the chosen alert policy")
    p_high: Optional[float] = Field(None, description="Probability that cases reach High")
    p_critical: Optional[float] = Field(None, description="Probability that cases reach Critical")
    critical_watch: bool = Field(False, description="Critical is likely enough to prepare for")
    actual_cases: Optional[float] = Field(None, description="Reported cases that week, when the data has it")


class Driver(BaseModel):
    group: str
    multiplier: float


class Explanation(BaseModel):
    ward_id: str
    issue_date: date
    horizon_weeks: int
    expected_cases: float
    tier: str
    drivers: list[Driver]


class ScenarioIn(BaseModel):
    ward_id: str
    issue_date: Optional[date] = None
    rain_factor: float = Field(1.0, ge=0, le=5, description="Multiply rainfall of the last 2 weeks")
    temp_offset: float = Field(0.0, ge=-10, le=10, description="°C added to the last 2 weeks")
    humidity_offset: float = Field(0.0, ge=-50, le=50, description="Percentage points added")


# --------------------------------------------------------------------------- helpers
def _issue(d: Optional[date]) -> pd.Timestamp:
    svc = service()
    if d is None:
        return svc.default_issue_date()
    ts = pd.Timestamp(d)
    if ts not in set(svc.issue_dates):
        raise HTTPException(422, f"No complete feature row for week {d}. Use a Monday between "
                                 f"{svc.issue_dates[0]:%Y-%m-%d} and {svc.issue_dates[-1]:%Y-%m-%d}.")
    return ts


def _horizon(h: int) -> int:
    if h not in service().bundle.horizons:
        raise HTTPException(422, f"horizon must be one of {service().bundle.horizons}")
    return h


def _ward(w: str) -> str:
    if w not in service().wards.index:
        raise HTTPException(404, f"Unknown ward_id {w!r}")
    return w


def _num(v) -> Optional[float]:
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 3)


@lru_cache(maxsize=512)
def _forecast_all(issue: pd.Timestamp, horizon: int, city: Optional[str],
                  policy: str = DEFAULT_ALERT_POLICY) -> list[WardForecast]:
    fc = service().forecast_all(issue, horizon, [city] if city else None, policy)
    return [
        WardForecast(
            ward_id=r[C.WARD_COL], city=r[C.CITY_COL], issue_date=issue.date(),
            target_date=pd.Timestamp(r["target_date"]).date(), horizon_weeks=horizon,
            expected_cases=_num(r["expected_cases"]), lower_80=_num(r["lower_80"]), upper_80=_num(r["upper_80"]),
            tier=r["tier"], upside_tier=r["upside_tier"], response=TIERS[r["tier"]].action,
            alert=bool(r["alert"]), actual_cases=_num(r["actual"]),
            p_high=_num(r.get("p_high")), p_critical=_num(r.get("p_crit")),
            critical_watch=bool(r.get("crit_watch", False)),
        )
        for _, r in fc.iterrows()
    ]


# --------------------------------------------------------------------------- routes
@app.get("/health")
def health() -> dict:
    svc = service()
    return {
        "status": "ok",
        "version": __version__,
        "model_trained_through": svc.bundle.metadata.get("trained_through"),
        "wards": len(svc.wards),
        "latest_week": f"{svc.issue_dates[-1]:%Y-%m-%d}",
        "horizons_weeks": svc.bundle.horizons,
        "tier_thresholds": dict(zip(C.TIER_NAMES[1:], svc.bundle.tier_thresholds)),
    }


@app.get("/wards")
def wards(city: Optional[str] = None) -> list[dict]:
    w = service().wards.reset_index()
    if city:
        w = w[w[C.CITY_COL] == city]
    return w.to_dict(orient="records")


@app.get("/forecast", response_model=list[WardForecast])
def forecast(
    issue_date: Optional[date] = Query(None, description="Monday the forecast is issued; default: a peak-season replay week"),
    horizon: int = Query(3, description="Weeks ahead: 2, 3 or 4"),
    city: Optional[str] = None,
    min_tier: str = Query("Low", description="Only return wards at or above this tier"),
    alert_policy: str = Query(DEFAULT_ALERT_POLICY, description="Standard, Balanced or Cautious"),
    alerts_only: bool = Query(False, description="Only return wards on alert"),
) -> list[WardForecast]:
    if min_tier not in C.TIER_NAMES:
        raise HTTPException(422, f"min_tier must be one of {list(C.TIER_NAMES)}")
    if alert_policy not in ALERT_POLICIES:
        raise HTTPException(422, f"alert_policy must be one of {list(ALERT_POLICIES)}")
    rows = _forecast_all(_issue(issue_date), _horizon(horizon), city, alert_policy)
    if alerts_only:
        rows = [r for r in rows if r.alert]
    floor = C.TIER_NAMES.index(min_tier)
    return [r for r in rows if C.TIER_NAMES.index(r.tier) >= floor]


@app.get("/wards/{ward_id}/outlook", response_model=list[WardForecast])
def outlook(ward_id: str, issue_date: Optional[date] = None) -> list[WardForecast]:
    issue = _issue(issue_date)
    ward = _ward(ward_id)
    out = []
    for h in service().bundle.horizons:
        out += [r for r in _forecast_all(issue, h, None) if r.ward_id == ward]
    return out


@app.get("/wards/{ward_id}/explain", response_model=Explanation)
def explain(ward_id: str, issue_date: Optional[date] = None, horizon: int = 3) -> Explanation:
    issue, ward, h = _issue(issue_date), _ward(ward_id), _horizon(horizon)
    groups, _, _ = service().explain(ward, issue, h)
    pred = service().bundle.predict(service().ward_row(ward, issue), h).iloc[0]
    return Explanation(
        ward_id=ward, issue_date=issue.date(), horizon_weeks=h,
        expected_cases=_num(pred["expected_cases"]), tier=pred["tier"],
        drivers=[Driver(group=r.group, multiplier=round(float(r.multiplier), 3))
                 for r in groups.sort_values("log_effect", ascending=False).itertuples()],
    )


@app.post("/scenario", response_model=list[WardForecast])
def scenario(body: ScenarioIn) -> list[WardForecast]:
    issue, ward = _issue(body.issue_date), _ward(body.ward_id)
    svc = service()
    out = svc.ward_outlook(ward, issue, Scenario(body.rain_factor, body.temp_offset, body.humidity_offset))
    city = svc.wards.loc[ward, C.CITY_COL]
    return [
        WardForecast(
            ward_id=ward, city=city, issue_date=issue.date(), target_date=pd.Timestamp(r["target_date"]).date(),
            horizon_weeks=int(r["horizon"]), expected_cases=_num(r["expected_cases"]),
            lower_80=_num(r["lower_80"]), upper_80=_num(r["upper_80"]), tier=r["tier"],
            upside_tier=r["upside_tier"], response=TIERS[r["tier"]].action, actual_cases=_num(r["actual"]),
            p_high=_num(r.get("p_high")), p_critical=_num(r.get("p_crit")),
            critical_watch=bool(r.get("crit_watch", False)),
        )
        for _, r in out.iterrows()
    ]


# --------------------------------------------------------------------------- Phase 2: operations
class AllocationOut(BaseModel):
    issue_date: date
    horizon_weeks: int
    stock_pct: float
    total_crews: int
    summary: dict
    wards: list[dict]


@app.get("/allocation", response_model=AllocationOut)
def allocation(
    issue_date: Optional[date] = None,
    horizon: int = Query(3, description="Weeks ahead: 2, 3 or 4"),
    stock_pct: float = Query(1.0, ge=0.3, le=1.0, description="Available regional stock, 0.3 to 1.0 of demand"),
    total_crews: int = Query(40, ge=0, le=1000),
    plan_for: str = Query("expected", description="expected or upper (upper end of the 80% range)"),
    city: Optional[str] = None,
) -> AllocationOut:
    """Constrained supply and crew allocation (saline, kits, beds, crews) with deficit flags."""
    from . import allocation as A

    if plan_for not in ("expected", "upper"):
        raise HTTPException(422, "plan_for must be 'expected' or 'upper'")
    issue, h = _issue(issue_date), _horizon(horizon)
    fc = service().forecast_all(issue, h, [city] if city else None)
    alloc = A.allocate(fc, service().wards, stock_pct, total_crews, plan_for)
    cols = [C.WARD_COL, C.CITY_COL, "tier", "planned_cases", "priority_rank", "priority_score",
            *[c for trio in A.RESOURCES for c in trio[:2]], "crews_needed", "crews_assigned",
            "fill_rate", "deficit_flag", "deficit_note"]
    rows = alloc[cols].round(3).to_dict(orient="records")
    return AllocationOut(issue_date=issue.date(), horizon_weeks=h, stock_pct=stock_pct, total_crews=total_crews,
                         summary=A.summarize(alloc, total_crews), wards=rows)


class SimulationIn(BaseModel):
    issue_date: Optional[date] = None
    total_crews: int = Field(30, ge=0, le=1000)
    per_crew: float = Field(0.20, gt=0, le=0.5, description="Share of remaining breeding pressure one crew removes")
    max_per_ward: int = Field(4, ge=1, le=6)
    plan: Optional[dict[str, int]] = Field(None, description="ward_id -> crews; omit for the recommended plan")


@app.post("/simulate")
def simulate(body: SimulationIn) -> dict:
    """Vector-control counterfactual: cases, beds and saline saved at 2–4 weeks, ROI per ward."""
    from . import simulation as S

    issue = _issue(body.issue_date)
    table = S.build_effect_table(service(), issue, body.per_crew)
    plan = body.plan if body.plan is not None else S.recommend(table, body.total_crews, body.max_per_ward)
    unknown = [w for w in plan if w not in set(table.wards[C.WARD_COL])]
    if unknown:
        raise HTTPException(404, f"Unknown ward_id(s): {', '.join(unknown)}")
    by_ward, by_h = S.simulate(table, plan)
    used = by_ward[by_ward["crews"] > 0].sort_values("roi", ascending=False)
    return {
        "issue_date": issue.date().isoformat(),
        "plan": plan,
        "crews_used": int(by_ward["crews"].sum()),
        "by_horizon": by_h.round(2).to_dict(orient="records"),
        "wards": used[[C.WARD_COL, C.CITY_COL, "tier", "crews", "cases_prevented", "roi", "next_crew_gain"]]
        .round(3).to_dict(orient="records"),
    }
