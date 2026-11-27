# Q&A prep (onsite final)

Likely judge questions with short answers we can give from memory. Every number here comes from the code, `artifacts/metrics.json` or the tests. Where to look in the code is in brackets, so anyone can open the file if a judge asks to see it. The method write-up is in [ARCHITECTURE.md](../ARCHITECTURE.md).

**How to answer:** lead with the number or the rule, then one sentence on why. If a question goes beyond what we built, say so plainly ("we assume X; real data would replace it") rather than guessing.

## Resource allocation (module 1)

### 1. Where do the supply ratios come from?
We fitted them from the onsite dataset by least squares through the origin: each supply column against `dengue_cases`. That gives **2.384 saline bags, 1.158 test kits and 0.295 beds per case**, with R² of 0.9997, 0.9988 and 0.9804. They match the "about 2.4, 1.2 and 0.3" pattern in the data. The app refits them from the file the first time they are needed, so new data updates them automatically. [`allocation.py`, `demand_ratios`]

### 2. Why fit through the origin?
Zero cases should mean zero saline. A free intercept would allocate stock to wards with no cases. The near-perfect R² shows the relationship really is proportional.

### 3. Why round demand up?
Understating demand is the dangerous error: a ward that needs 2.4 bags needs 3, not 2. Rounding up means a deficit flag is never hidden by rounding.

### 4. How is priority decided when stock is short?
`priority_score = 100 × (0.6 × tier/3 + 0.4 × P(High)) × (0.5 + 0.5 × density / max density)`. Risk decides most of the order. Population density moves a ward within its risk band: the densest ward keeps its full score, the sparsest keeps half. Stock then goes to wards in that order until it runs out. Ties are broken by planned cases and then ward id, so a shuffled input gives the same plan. [`allocation.py`, `priority_scores`]

### 5. What does an officer see at 70% stock in the demo week?
For the week of 23 June 2025, issued 2 June, the 35 highest-priority wards get everything. The other 25 are flagged with their exact gap, such as "Short 13 saline bags, 7 test kits". At 30% stock, 47 wards are short, but the riskiest and densest are still served first.

### 6. How are spraying crews split?
High and Critical wards need one crew per 5 expected cases. Every one of them gets one crew, in priority order, before any ward gets a second, and leftover crews then top up the highest needs. In the demo week the 26 High wards need 52 crews. With 40, every High ward has a crew and 12 are one short, which the page reports separately from supply deficits.

### 7. How do you know the allocation is right?
Property tests run each rule on 40 seeded random weeks, not one hand-picked example. They check that allocation never exceeds stock, that 100% stock means no deficits, that scarce stock follows priority order, and that crews add up to the total. They found one real bug: two wards with equal scores were ranked by input row order, so the plan could change with row order. Ward id is now the final tie-break. [`tests/test_allocation.py`, `docs/testing.md`]

## Hospital overflow routing (module 2)

### 8. The data has no bed capacity. How did you get one?
Each ward's capacity is its **90th-percentile weekly bed demand over 2016–2023**, rounded up and at least 1. That is the level a ward handles in a bad but normal week: 1 to 5 beds, against 4 to 12 in each ward's peak week. We only use years up to 2023 so the 2024–25 test seasons don't leak into capacity. It is an assumption, and real bed counts would replace it in one function. [`routing.py`, `estimate_bed_capacity`]

### 9. How does routing stay within a city?
We route each city corporation on its own: patients can only move to wards in the same city table, so a cross-city transfer can't happen. A property test on 150 random three-city weeks checks that no transfer crosses cities, that patients are conserved, and that no ward stays over capacity while its city still has spare beds. [`routing.py`, `route_overflow`; `tests/test_routing.py`]

### 10. Which ward receives the patients?
Senders go largest overflow first. Each sender fills the **least loaded** ward first, meaning the lowest share of its beds in use. Ties go to the nearest ward by ward number, then to the ward id. Routing stops when the overflow is placed or the city runs out of beds, and anything left is shown as unplaced, in red.

### 11. Show me a real transfer.
In the week of 7 August 2023, Dhaka North needs 57 beds and has 56, and one patient moves from Ward 01 to Ward 09. Across all cities, 2 patients move and 5 have no bed. With the surge slider at +30%, 7 patients move and nobody is left unplaced.

## Vector control simulator (module 3)

### 12. Is the simulator model-driven or just a formula?
It's model-driven. A crew removes breeding sites, so we cut that ward's recent breeding signal (rain 0–4 weeks back, the breeding window and heavy-rain weeks) and **re-run the forecasting models** for 2, 3 and 4 weeks. Only the size of the cut is a formula: `effect(c) = min(0.75, 1 − 0.8^c)`, so one crew removes 20%, extra crews help less, and spraying never removes more than 75%. [`simulation.py`]

### 13. Couldn't the model say a crew makes things worse?
No. The simulator uses a dedicated LightGBM model per horizon with monotone constraints on the rain features, so less breeding rain can never raise a forecast. Its hold-out MAE is 1.00, 1.06 and 1.23 at 2, 3 and 4 weeks, close to the main model's 1.01, 1.03 and 1.19. We apply its proportional reduction to the main forecast, so the baseline matches every other page.

### 14. Why 20% per crew?
The data has no spraying records, so 20% is an assumption, not a measurement. It gives diminishing returns and a 75% cap, which matches how larviciding works: you can't reach every container. That's why it is a slider (10% to 35%) on the Simulator page. With spraying records we would fit it.

### 15. What does the simulator say for the demo week?
With 30 crews placed where each prevents the most cases, expected cases at 3 weeks fall from 399 to 351, which is 48 fewer. That saves about 14 beds and 114 saline bags, and 142 cases at 4 weeks. Dhaka North Ward 12 is the best buy, at about 9 cases prevented per crew. A crew that would prevent fewer than 0.1 cases is held in reserve.

## Dispatch notices (module 4)

### 16. Do you use an LLM to write the notices?
No. They are fixed string templates filled from the allocation and routing tables, so they work offline, cost nothing, and give the same text for the same plan. [`dispatch.py`]

### 17. How do you guarantee the SMS fits?
It always fits one 160-character GSM-7 segment. If it would be longer, optional details are dropped or shortened in a fixed order, and the risk, supplies and any deficit are never cut. Tests check the limit on every ward. The demo week's 26 High wards are in `exports/sms/`, generated by `scripts/export_dispatch.py`.

## Offline mode (module 5)

### 18. What happens with the WiFi off?
Everything works. Forecasting, allocation, routing, the simulator and dispatch run locally from the saved model. The only page that calls the internet is Live outlook (Open-Meteo). With `MOSHARI_OFFLINE=1` or the sidebar **Offline mode** toggle it skips the request and shows the last cached weather, or a clear message if nothing is cached. Fonts fall back to system fonts.

### 19. How do you prove it?
Three ways. `tests/test_offline.py` turns the kill switch on and blocks network sockets, so any HTTP call or DNS lookup fails the test, then renders the 9 original pages and runs the core pipeline; `tests/test_briefing_page.py` does the same for the Weekly briefing page and its PDF. `tests/test_offline_wifi_off.py` leaves the switch off and refuses every non-local connection, as with Wi-Fi off, and checks that only Live outlook tries the internet and falls back cleanly. They run in CI with the rest of the 1041 tests. And `python scripts/offline_check.py` starts the real app with the internet cut off and prints "OFFLINE CHECK: 9/9 pages OK" (it does not open the Weekly briefing page yet). The by-hand steps for the judges are in [offline_check.md](offline_check.md).

## Forecast accuracy and validation

### 20. How accurate is the forecast?
On 2024–25, two seasons the model never saw, 3-week forecasts miss by **1.03 cases per ward per week**, 17% better than the best simple rule. 83% of ward-weeks are in the right tier, and the 80% range covers 80% of actual counts.

### 21. How did you avoid leakage?
We split chronologically by the week being forecast: train 2016–2022, validate 2023, test 2024–2025. All features look only backwards and are computed within each ward. Tests check that lags never cross wards and that changing a future week leaves earlier features unchanged.

### 22. Expected cases understate peaks. Doesn't that hurt allocation?
That's why we have separate outbreak-probability models. They catch 70% of Critical weeks at 3 weeks, against 28% from expected cases alone. P(High) is also in the allocation priority score, so a ward likely to spike moves up the queue even when its expected cases are moderate.

### 23. Why LightGBM?
The data is small and tabular: 31,320 rows and 33 features. A Poisson objective suits counts with many zeros, and LightGBM gives exact explanations through TreeSHAP and supports the monotone constraints the simulator needs.

## Process

### 24. Did you use AI tools?
Yes, while building, and we disclose them in the README. We used exactly two: Claude Code and GitHub Copilot. Nothing in the running app calls an AI model.
