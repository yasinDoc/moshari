# Moshari architecture

Moshari forecasts dengue cases for each of 60 city wards 2, 3 and 4 weeks ahead and turns them into Low, Medium, High or Critical risk, each with a response. Forecasting runs locally from a saved model; the only runtime API call is one cached Open-Meteo request for the Live outlook.

## Data flow

```mermaid
flowchart LR
    A["Weekly ward CSV<br/>weather + ward profile + cases"] --> B["Validate<br/>schema, ranges,<br/>duplicates, weekly gaps"]
    B --> C["Feature builder<br/>groupby(ward_id)<br/>rain lags 0–8 wk, breeding window,<br/>temp/humidity rolls, case history"]
    C --> D["Chronological split<br/>by target week"]
    D -->|"2016–2022"| E["Train<br/>LightGBM per horizon (2, 3, 4 wk)"]
    D -->|"2023"| F["Validate<br/>early stopping, conformal range,<br/>probability cut-offs"]
    E --> G[("models/moshari_lgbm.joblib<br/>18 boosters: mean, quantiles,<br/>P(High), P(Critical), rain-forecast")]
    F --> G
    D -->|"2024–2025"| H["Hold-out test<br/>vs 3 baselines"]
    G --> H --> I[("artifacts/<br/>metrics.json, backtest.parquet")]
    G --> J["ForecastService<br/>(service.py)"]
    C --> J
    M["Open-Meteo<br/>1 batched request, 6 h cache"] -->|"weather, ward-adjusted,<br/>case nowcast (live.py)"| J
    J --> K["Streamlit dashboard"]
    J --> L["FastAPI REST"]
    I --> K
```

`src/moshari/` holds the engine (`data`, `features`, `model`, `risk`, `evaluation`, `training`, `service`, `live`); `ui/` holds the dashboard only. Neither the dashboard nor the API touches LightGBM directly. Both call `ForecastService`, so a fix reaches both at once.

## The breeding clock, as features

Larvae take 7 to 14 days to mature and symptoms follow incubation, so within each ward rainfall correlates with cases most strongly **3 weeks later (r = 0.75)**, against 0.53 for same-week rain. All features are computed within `groupby(ward_id)` and look only backwards from the issue week *t*; the target for horizon *h* is cases at *t + h*. Tests check that lags never cross wards and that changing a future week leaves earlier features unchanged.

| Group | Features |
|---|---|
| Rainfall | lags 0–8 weeks, 2/4/8-week sums, `rain_breeding_window` (lags 2–4), heavy-rain weeks |
| Temperature, humidity | 2- and 4-week means, value 3 weeks ago, day–night range |
| Ward vulnerability | density, water-logging, sanitation, composite index, city corporation |
| Recent transmission | cases this week, 1 and 2 weeks ago, 4-week mean, 2-week trend |
| Seasonality | week of year as sine and cosine |

## Chronological validation

Split by the **week being forecast**, never at random: train 2016–2022, validate 2023, test 2024–2025. 2023 chooses boosting rounds, calibrates the 80% range (conformalized quantile regression) and tunes probability cut-offs; the shipped model is then refit on 2016–2023 and scored once on 2024–25. Dashboard replays of 2024–25 are therefore out-of-sample. `scripts/train.py --production` refits on all years for deployment.

| Horizon | MAE | RMSE | This week | Last year | Seasonal avg | Tier accuracy | 80% coverage |
|---|---|---|---|---|---|---|---|
| 2 weeks | **1.01** | 2.05 | 1.66 | 1.69 | 1.24 | 83% | 82% |
| 3 weeks | **1.03** | 2.03 | 1.87 | 1.69 | 1.24 | 83% | 80% |
| 4 weeks | **1.19** | 2.33 | 2.06 | 1.69 | 1.24 | 81% | 85% |

MAE and RMSE are in cases per ward per week over 6,300 hold-out ward-weeks per horizon; the three middle columns are baseline MAEs.

## Model choice

**LightGBM, one set of models per horizon.** A Poisson model gives expected cases, two quantile models the 80% range, and two binary models the chance of reaching High and Critical.

- Small tabular data (31k rows, 33 features): boosted trees beat neural nets here with little tuning.
- Counts with many zeros suit a Poisson objective better than squared error.
- Direct per-horizon models avoid compounding errors from feeding forecasts back in.
- Explanations are exact and free: LightGBM's native TreeSHAP (`pred_contrib=True`) adds up to the prediction in log space (tested), shown as multipliers such as "rainfall ×4.5".
- Tier thresholds come from training-year quantiles (2, 7 and 13 cases a week) and are stored in the bundle.

## Peaks, alerts and the rain forecast

**Outbreak probability.** Expected cases smooth over peaks (about 4 cases low on actual Critical weeks). Peak-weighting, isotonic or power calibration and Tweedie all raised average error by 10–20%, so instead the binary models estimate P(Critical); a ward goes on **Critical watch** past a cut-off tuned on 2023. Critical weeks caught rise from **24/28/20% to 63/70/73%** at 2/3/4 weeks (AUC 0.96/0.95/0.92), at the cost of more false alarms (about two in three flags at 3 weeks stay below Critical).

**Alert sensitivity.** Who goes on the watch list is a separate, switchable rule (3-week horizon):

| Rule | Alerts when | High-risk weeks caught | Alerts that were real | Alerted by season onset |
|---|---|---|---|---|
| Standard | expected cases reach High | 71% | 67% | 35% |
| Balanced | midpoint of expected and upper bound | 87% | 59% | 57% |
| **Cautious (default)** | upper end of the 80% range | **98%** | 49% | **90%** |

Missing an outbreak costs more than an extra larviciding visit, so Cautious is the default.

**Rain forecast.** Cases 4 weeks out depend on next week's rain, which hasn't fallen at issue time, so stacking, seasonal priors and bigger models barely helped. Forecast-assisted models also see the next two weeks of weather, trained with noise (rain ±65%, temperature ±1 °C) so they don't over-trust it. 4-week MAE drops from **1.19 to 1.08** with a realistic forecast (1.07 with a perfect one; seasonal average 1.26). Live mode feeds them Open-Meteo's forecast; replays keep the base model, as past forecasts aren't archived.

## Compute and API cost controls

| Control | Effect |
|---|---|
| Local inference, no LLM | Forecasts, explanations and what-ifs run on the CPU; token cost is 0. |
| One batched, cached weather call (`live.py`) | All 5 cities in **one** Open-Meteo request, cached on disk for 6 h, manual refresh limited to once per 10 min, last good response used offline. |
| Serialized model | Training (about 2 min) happens once; startup loads a 9.7 MB joblib file with boosters in LightGBM's portable text format. |
| Caching | Model and features load once per server (`st.cache_resource`); results are keyed by data fingerprint, week, horizon and cities (`st.cache_data`); the API has an `lru_cache`. |
| Fast paths | All 60 wards in about 0.1 s; what-if sliders re-run only their card (`st.fragment`); the dashboard skips importing scikit-learn, cutting cold start from 12.4 s to 8.1 s. |
| Validation first | Bad uploads are rejected before any feature or model work. |

An LLM summary in the final round would follow the same pattern: one batched request, a disk cache keyed by date, capped output tokens, and a cached template as fallback.

## Limitations

- Weekly data, so forecasts update weekly; no ward coordinates, so the dashboard uses a schematic ward net, not a map.
- Expected cases understate peaks; the outbreak-probability models above compensate.
- Live mode has no reported cases yet: recent case history is a weather-driven nowcast from the model's own 2-week forecasts.
- Live weather is one point per city corporation, adjusted per ward. In the training data wards differ from their city by about 1% in rain and under 0.1 °C, so little is lost.
