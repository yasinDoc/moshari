# What the tests guarantee

Run everything (about 30 seconds):

```powershell
.venv\Scripts\python -m pytest
```

Run just one area while you work on it:

```powershell
.venv\Scripts\python -m pytest tests/test_routing.py      # hospital overflow routing
.venv\Scripts\python -m pytest tests/test_allocation.py   # resource allocation rules
.venv\Scripts\python -m pytest -k "cities"                # any test with "cities" in its name
.venv\Scripts\python -m pytest tests/test_hospital_page.py # the Hospital beds page itself
.venv\Scripts\python -m pytest tests/test_ward_map.py     # the Ward map: outline data, colours, links, page
```

## Allocation and routing (S2)

Most of these are *property* tests. A property test checks a rule on hundreds of
seeded random weeks, not one hand-picked example, so it catches the edge cases
nobody thought to write down. Seeds are fixed, so a failure always reproduces.
Each group also runs once on the real model's forecast.

| Rule from TASKS.md | Test | Checked on |
| --- | --- | --- |
| Allocated never exceeds stock, and no stock is left unused while a ward is short | `test_allocated_never_exceeds_stock_and_uses_all_of_it` | 40 random weeks × 6 stock levels (30% to 100%) |
| At 100% stock there are no deficits | `test_full_stock_means_no_supply_deficit` | 40 random weeks |
| At 30% stock the highest-priority wards are served first | `test_scarce_stock_serves_priority_order` | 40 random weeks, all three supplies |
| Crews add up to the total | `test_crews_add_up_to_the_total` | 40 random weeks × 5 crew counts |
| Every High/Critical ward gets 1 crew before any gets 2 | `test_every_high_ward_gets_one_crew_before_any_gets_two` | 40 random weeks |
| Transfers never cross cities | `test_routing_invariants_hold_on_random_cities` | 150 random 3-city weeks |
| Total patients are conserved | same test | same |
| No ward ends above capacity while its city still has headroom | same test: each city places exactly min(overflow, spare beds), the most possible | same |
| Same input, same plan, whatever the row order | `test_routing_is_deterministic_whatever_the_row_order`, `test_result_does_not_depend_on_row_order_and_leaves_input_alone` | 30 and 10 random weeks |
| Allocation output plugs straight into routing | `test_real_allocation_feeds_routing` | real forecast, 1 July 2024, 4 weeks ahead |
| Equal priority and equal cases are ranked by ward id | `test_tied_wards_are_ranked_by_ward_id_whatever_the_row_order` | 7 hand-built wards in 3 row orders |
| The ward furthest over capacity is placed first when beds run short | `test_largest_overflow_is_placed_first_when_beds_run_short` | 3 hand-built wards |
| The Hospital beds page shows what the engine computes | `tests/test_hospital_page.py` | the real app, 1 July 2024, 4 weeks ahead |

Edge cases covered: a quiet week, zero-capacity wards, ward ids without a
number, fractional or blank demand, duplicate wards, missing columns, an empty
table, stock outside 0–100%, and capacity history that must stop at 2023.

## A bug these tests found

When two wards had the same priority score and the same planned cases (common
for wards with zero cases), `allocate()` ranked them by input row order, so the
same week could produce a different plan if the rows arrived shuffled. The fix
adds ward id as the final tie-break in `src/moshari/allocation.py`.

## The Hospital beds page

`tests/test_hospital_page.py` opens the real app with Streamlit's `AppTest` (no browser
or server needed, about 3 seconds) on the demo week, issued 1 July 2024 for 4 weeks ahead. It checks
that the page's Beds available, Beds needed, Patients moved and Still short numbers, and every
ward on the red list, equal `route_overflow(allocate(...))` called directly. Then it moves the
"Surge beds per ward" slider to +30% and checks that no ward is left short. So a page that
quietly used the wrong demand, showed a wrong total or ignored the slider would fail.

## Do the tests really catch bugs? (mutation check)

```powershell
.venv\Scripts\python scripts/mutation_check.py          # about 30 seconds
.venv\Scripts\python scripts/mutation_check.py --list   # what each mutant breaks
```

`scripts/mutation_check.py` plants 16 known bugs, one at a time, in a temporary copy of the
project: 7 in `routing.py` (for example transfers crossing cities, a receiver overfilled, the
smallest overflow handled first), 5 in `allocation.py` (stock exceeded, the tie-break removed,
demand rounded down) and 4 in `ui/views/hospital.py` (stand-in demand, a wrong stat, the surge
slider ignored, a ward missing from the red list). For each it runs the related tests, which must
fail. It prints `MUTATION CHECK: 16/16 killed` and exits 0 only when every bug is caught. Your
own files are never changed.

The first run caught a real gap: nothing tested that the ward furthest over capacity is placed
first, so the "smallest first" mutant survived. `test_largest_overflow_is_placed_first_when_beds_run_short`
now covers it.

## Coverage

CI also runs:

```powershell
.venv\Scripts\python -m pytest -q tests/test_routing.py tests/test_allocation.py tests/test_allocation_engine.py --cov=moshari.routing --cov=moshari.allocation --cov-report=term-missing --cov-fail-under=95
```

It fails the build if the routing and allocation modules drop below 95% line coverage (they are at
98%). `pytest-cov` is in `requirements-dev.txt`. Coverage only says a line ran; the mutation check
above is what shows the tests would notice that line being wrong.

## The speed guard

`test_routing_60_wards_is_fast` fails if routing the 60 wards takes over 1 second per run. Routing
takes about 1 ms, so the bound only catches a real blow-up (an accidental O(n^3) loop or a hang),
never a slow CI machine.

## Offline (S3)

`tests/test_offline_wifi_off.py` runs every page with Wi-Fi off: all internet connections are
refused and the `MOSHARI_OFFLINE` switch is not set. All 11 pages must render, and only Live outlook
may try the internet (it falls back to saved weather or a clear message). With the switch on,
nothing tries the internet at all. To rehearse the same thing with the real app server:

```powershell
.venv\Scripts\python scripts/offline_check.py   # prints "OFFLINE CHECK: 11/11 pages OK"
```

The step-by-step check for the judges, with Wi-Fi really off, is in [offline_check.md](offline_check.md).
