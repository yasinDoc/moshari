# What the tests guarantee

Run everything (about 25 seconds):

```powershell
.venv\Scripts\python -m pytest
```

Run just one area while you work on it:

```powershell
.venv\Scripts\python -m pytest tests/test_routing.py      # hospital overflow routing
.venv\Scripts\python -m pytest tests/test_allocation.py   # resource allocation rules
.venv\Scripts\python -m pytest -k "cities"                # any test with "cities" in its name
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

Edge cases covered: a quiet week, zero-capacity wards, ward ids without a
number, fractional or blank demand, duplicate wards, missing columns, an empty
table, stock outside 0–100%, and capacity history that must stop at 2023.

## A bug these tests found

When two wards had the same priority score and the same planned cases (common
for wards with zero cases), `allocate()` ranked them by input row order, so the
same week could produce a different plan if the rows arrived shuffled. The fix
adds ward id as the final tie-break in `src/moshari/allocation.py`.
