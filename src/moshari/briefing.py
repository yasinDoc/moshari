"""Weekly briefing: the five modules turned into one decision for a city health officer.

One call, :func:`build`, runs the forecast, the allocation engine (module 1), overflow
routing (module 2), the crew simulator (module 3) and the dispatch selection (module 4)
for one week and returns plain numbers plus a four-sentence decision. The Weekly briefing
page and its PDF (:mod:`moshari.briefing_pdf`) only display this dict, so they always agree.

:func:`supply_alerts` and :func:`alert_text` give the short shortage line shown on the
Overview page ("25 wards short on saline · 24 wards short on test kits · 12 crews short").

Beds are routed the way the Hospital beds page routes them: *required* beds (scarcity of
regional stock does not apply to beds; ward capacity does) against the 90th-percentile
capacity, plus optional surge beds. Everything runs offline (module 5): no network and no
AI service.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import pandas as pd

from . import allocation as A
from . import config as C
from . import dispatch as D
from . import routing as R
from . import simulation as S
from .risk import DEFAULT_ALERT_POLICY

# The Overview strip uses the default scenario of the Resources and Hospital beds pages.
OVERVIEW_STOCK = 0.70
OVERVIEW_CREWS = 40
OVERVIEW_SURGE = 0

ALERT_SEP = " · "


def plural(n: int, word: str) -> str:
    """``plural(1, "ward") -> "1 ward"``; any other count adds an "s"."""
    return f"{n} {word}{'' if n == 1 else 's'}"


def beds_routing(svc, fc: pd.DataFrame, surge_pct: float = 0) -> R.RoutingResult:
    """Overflow routing exactly as the Hospital beds page does it."""
    return R.route_overflow(A.allocate(fc, svc.wards), R.with_surge(R.load_bed_capacity(), surge_pct))


def supply_alerts(alloc: pd.DataFrame, ward_summary: pd.DataFrame) -> dict[str, int]:
    """Shortage counts for the Overview strip.

    ``alloc``: :func:`moshari.allocation.allocate` output. ``ward_summary``: the routing
    result's ward summary (a ward is "out of beds" when patients remain without a bed
    after transfers).
    """
    return {
        "saline_wards": int((alloc["saline_bags_allocated"] < alloc["saline_bags_needed"]).sum()),
        "kits_wards": int((alloc["diagnostic_kits_allocated"] < alloc["diagnostic_kits_needed"]).sum()),
        "crews_short": int((alloc["crews_needed"] - alloc["crews_assigned"]).clip(lower=0).sum()),
        "out_of_beds_wards": int((ward_summary["net_deficit"] > 0).sum()),
    }


def alert_parts(alerts: Mapping[str, int]) -> list[tuple[str, str]]:
    """``(text, kind)`` for each non-zero shortage; kind is "supplies", "crews" or "beds"."""
    spec = [("saline_wards", "ward", " short on saline", "supplies"),
            ("kits_wards", "ward", " short on test kits", "supplies"),
            ("crews_short", "crew", " short", "crews"),
            ("out_of_beds_wards", "ward", " out of beds", "beds")]
    return [(plural(int(alerts[k]), w) + tail, kind) for k, w, tail, kind in spec if int(alerts.get(k, 0))]


def alert_text(alerts: Mapping[str, int]) -> str:
    """One line, e.g. "12 wards short on saline · 3 wards out of beds", or "All wards supplied"."""
    parts = [t for t, _ in alert_parts(alerts)]
    return ALERT_SEP.join(parts) if parts else "All wards supplied"


def _decision(target: pd.Timestamp, wards: int, high: int, needed: int, assigned: int, unmet: int,
              saline: int, kits: int, deficit: int, moved: int, unplaced: int) -> list[str]:
    s1 = f"{high} of {plural(wards, 'ward')} are High or Critical risk for the week of {target:%d %b %Y}."
    if needed == 0:
        s2 = "No spraying crews are needed this week."
    elif unmet:
        s2 = f"Approve {plural(unmet, 'more spraying crew')}: {needed} needed, {assigned} assigned."
    else:
        s2 = f"All {needed} crews needed are assigned."
    if deficit:
        s3 = (f"Release {plural(saline, 'more saline bag')} and {plural(kits, 'more test kit')} to cover "
              f"{plural(deficit, 'short ward')}.")
    else:
        s3 = "Every ward is fully supplied."
    if moved and unplaced:
        s4 = (f"Move {plural(moved, 'patient')} between wards in the same city; beds are still missing for "
              f"{plural(unplaced, 'patient')}.")
    elif moved:
        s4 = f"Move {plural(moved, 'patient')} between wards in the same city; every patient has a bed."
    elif unplaced:
        s4 = f"No transfer can help: beds are still missing for {plural(unplaced, 'patient')}."
    else:
        s4 = "No patient transfers are needed."
    return [s1, s2, s3, s4]


def _by_city(fc: pd.DataFrame, alloc: pd.DataFrame, rr: R.RoutingResult) -> list[dict[str, Any]]:
    """One row per city for the briefing's city table."""
    rows = []
    cs = rr.city_summary.set_index(C.CITY_COL)
    for city, grp in alloc.groupby(C.CITY_COL, sort=True):
        f = fc[fc[C.CITY_COL] == city]
        rows.append({
            "city": city,
            "wards": int(len(f)),
            "high_wards": int((f["tier_idx"] >= 2).sum()),
            "expected_cases": float(f["expected_cases"].sum()),
            "short_wards": int(grp["deficit_flag"].sum()),
            "crews_assigned": int(grp["crews_assigned"].sum()),
            "crews_needed": int(grp["crews_needed"].sum()),
            "patients_moved": int(cs.loc[city, "patients_moved"]) if city in cs.index else 0,
            "unplaced": int(cs.loc[city, "unplaced"]) if city in cs.index else 0,
        })
    return sorted(rows, key=lambda r: (-r["high_wards"], -r["expected_cases"], r["city"]))


def build(svc, issue_date, horizon: int, cities: Iterable[str] = (), policy: str = DEFAULT_ALERT_POLICY,
          stock_pct: float = 0.70, crews: int = 40, surge_pct: float = 0) -> dict[str, Any]:
    """Everything the weekly briefing shows, for one forecast week and one supply scenario.

    ``svc``: a :class:`moshari.service.ForecastService`. ``cities``: city names to keep
    (empty = all five). ``stock_pct``: regional stock as a share of demand (0-1].
    ``crews``: spraying crews available. ``surge_pct``: extra surge beds per ward, in %.
    """
    cities = list(cities)
    issue = pd.Timestamp(issue_date)
    fc = svc.forecast_all(issue, horizon, cities or None, policy)
    alloc = A.allocate(fc, svc.wards, stock_pct, crews)
    summ = A.summarize(alloc, crews)
    rr = beds_routing(svc, fc, surge_pct)

    table = S.build_effect_table(svc, issue, cities=cities or None)
    plan = {w: int(c) for w, c in zip(alloc[C.WARD_COL], alloc["crews_assigned"]) if c > 0}
    by_h = S.simulate(table, plan)[1]

    # The notices Dispatch would send ("High risk" selection), routed as on that page.
    notices = D.select_rows(D.dispatch_table(alloc, R.route_overflow(alloc, R.load_bed_capacity())), "high")

    target = issue + pd.Timedelta(weeks=horizon)
    wards, high = len(fc), int((fc["tier_idx"] >= 2).sum())
    cr = summ["crews"]
    res = summ["resources"]
    transfers = [{"from_ward": str(t["from_ward"]), "to_ward": str(t["to_ward"]), "city": str(t["city"]),
                  "patients": int(t["patients"])} for t in rr.transfers.to_dict("records")]
    moved = sum(t["patients"] for t in transfers)
    unplaced = int(rr.ward_summary["net_deficit"].sum())
    top = fc.head(5)
    top_info = alloc.set_index(C.WARD_COL)

    return {
        "issue_date": issue,
        "target_week": target,
        "horizon": int(horizon),
        "cities": sorted(fc[C.CITY_COL].unique()),
        "stock_pct": stock_pct,
        "crews": int(crews),
        "surge_pct": surge_pct,
        "wards": wards,
        "high_wards": high,
        "critical_wards": int((fc["tier_idx"] == 3).sum()),
        "expected_cases": float(fc["expected_cases"].sum()),
        "top_wards": list(top[C.WARD_COL]),
        "top_rows": [{"ward_id": r.ward_id, "city": r.city, "tier": r.tier, "expected_cases": float(r.expected_cases),
                      "status": str(top_info.loc[r.ward_id, "deficit_note"])} for r in top.itertuples()],
        "saline_short_bags": int(res["saline bags"]["short"]),
        "kits_short": int(res["test kits"]["short"]),
        "deficit_wards": int(summ["deficit_wards"]),
        "resources": {k: dict(v) for k, v in res.items()},
        "alerts": supply_alerts(alloc, rr.ward_summary),
        "transfers": transfers,
        "patients_moved": int(moved),
        "unplaced": unplaced,
        "out_of_beds": [str(w) for w in rr.ward_summary.loc[rr.ward_summary["net_deficit"] > 0, C.WARD_COL]],
        "crews_needed": int(cr["needed"]),
        "crews_assigned": int(cr["assigned"]),
        "crews_unmet": int(cr["unmet"]),
        "cases_prevented": round(float(by_h["cases_prevented"].sum()), 1),
        "crew_wards": int(sum(1 for c in plan.values() if c > 0)),
        "notices_ready": int(len(notices)),
        "by_city": _by_city(fc, alloc, rr),
        "decision": _decision(target, wards, high, int(cr["needed"]), int(cr["assigned"]), int(cr["unmet"]),
                              int(res["saline bags"]["short"]), int(res["test kits"]["short"]),
                              int(summ["deficit_wards"]), int(moved), unplaced),
    }
