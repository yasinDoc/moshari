<p align="center">
  <img src="assets/logo.svg" width="88" alt="Moshari logo: a mosquito net with a mosquito kept outside">
</p>

<h1 align="center">Moshari (মশারি)</h1>

<p align="center"><b>Ward-level dengue early warning for Dhaka, Chattogram, Gazipur and Narayanganj.</b></p>

*Moshari* is Bangla for mosquito net. A net protects one family. Moshari helps protect whole wards by forecasting dengue cases **2 to 4 weeks ahead** from weather. That gives city corporations time to send larvicide and fogging teams *before* hospital admissions climb.

![Ward overview: all 60 wards as tiles in a net, coloured by forecast risk](docs/img/ward-net.png)

## Run it locally

Needs Python 3.10 or newer. The trained model and the dataset are in the repo, so no training or downloads are needed beyond the Python packages.

**Windows (PowerShell)**

```powershell
git clone https://github.com/yasinDoc/moshari.git
cd moshari
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

**macOS / Linux**

```bash
git clone https://github.com/yasinDoc/moshari.git
cd moshari
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The dashboard opens at http://localhost:8501.

## Tested on

| Operating system | Python | Setup time |
|---|---|---|
| Windows 11 Home Single Language | 3.15.2 | 7 min 40 sec |

Optional:

```bash
python scripts/train.py            # retrain and re-evaluate (about 1 minute on a laptop CPU)
pip install -r requirements-dev.txt && pytest   # 21 tests
docker build -t moshari . && docker run -p 8501:8501 moshari
```

## What it does

| Page | What a health officer gets |
|---|---|
| **Ward overview** | Every ward's risk for the chosen week as tiles in a net, grouped by city corporation, plus a whole-season view. Headline numbers, the six wards to send teams to first, and risk by city. |
| **Ward forecast** | One ward's 2-, 3- and 4-week outlook with an 80% range and the recommended response. A chart that lines up rain with later cases. The drivers behind the forecast, and what-if sliders for rain, temperature and humidity that re-run the model live. |
| **Model accuracy** | Hold-out results for 2024–25 against three simple baselines, a tier confusion matrix, a replay of both seasons, and the evidence for the 3-week breeding lag. |
| **Data** | Upload a newer weekly CSV. It is validated, then every page forecasts from it. |

![Ward forecast: outlook, rain-to-cases chart and drivers](docs/img/ward-forecast.png)

## REST API

The same forecasting service is available over HTTP for SMS alerts, hospital systems or a city GIS:

```bash
pip install -r requirements-api.txt
uvicorn moshari.api:app --app-dir src --port 8000   # interactive docs at http://localhost:8000/docs
```

| Endpoint | Returns |
|---|---|
| `GET /forecast?issue_date=2025-06-02&horizon=3&min_tier=High&city=Gazipur` | Ranked ward forecasts with 80% range, tier and response |
| `GET /wards/{ward_id}/outlook` | 2-, 3- and 4-week outlook for one ward |
| `GET /wards/{ward_id}/explain` | Driver multipliers behind a forecast |
| `POST /scenario` | What-if forecast with adjusted rain, temperature or humidity |
| `GET /health`, `GET /wards` | Model version, thresholds, ward profiles |

## How it works

1. **Validate** the weekly ward file: schema, plausible ranges, duplicates and gaps between weeks ([`data.py`](src/moshari/data.py)).
2. **Build lag features per ward**: rainfall 0–8 weeks back, the 2–4-week breeding window, temperature and humidity rolls, recent cases, ward vulnerability and season ([`features.py`](src/moshari/features.py)).
3. **Forecast** with LightGBM: a Poisson model per horizon for expected cases and quantile models for an 80% range calibrated with conformal prediction ([`model.py`](src/moshari/model.py)).
4. **Tier and respond**: Low, Medium, High or Critical from training-year thresholds, each with a response playbook ([`risk.py`](src/moshari/risk.py)).
5. **Explain**: TreeSHAP contributions computed natively by LightGBM, grouped into drivers like "Rainfall (breeding clock) ×4.5".

On 2024–25, which the model never saw, 3-week forecasts are off by **1.03 cases per ward per week** on average. That is 17% better than the best baseline, with 83% of ward-weeks in the right tier. Full method, split and cost controls are in **[ARCHITECTURE.md](ARCHITECTURE.md)**.

## Project structure

```
moshari/
├── app.py                  # Streamlit entry point
├── ui/                     # dashboard only: theme, cached state, pages
│   └── views/              # ward_net, ward_forecast, model_check, data_source
├── src/moshari/            # forecasting engine, no UI code
│   ├── config.py           # paths, schema, horizons, split dates
│   ├── data.py             # ingestion + validation
│   ├── features.py         # per-ward lag features
│   ├── model.py            # LightGBM bundle, inference, TreeSHAP
│   ├── risk.py             # tiers + response playbook
│   ├── evaluation.py       # metrics + baselines
│   ├── training.py         # chronological training pipeline
│   ├── service.py          # ForecastService used by the UI and API
│   └── api.py              # FastAPI REST layer
├── scripts/                # train.py, fetch_data.py
├── models/                 # serialized model bundle
├── artifacts/              # metrics.json, backtest.parquet
├── data/raw/dengue.csv     # challenge dataset
├── tests/                  # pytest suite
└── docs/                   # screenshots, demo script
```

## Team

Built by **Samiya**, **Ananya** and **Yasin** for the EDU AI Engineering Hackathon 2026, preliminary round (21 to 22 Nov 2026).

## AI assistants and external services

We disclose every AI tool and outside service used to build or run Moshari.

**AI assistants**

| Tool | Used for |
|---|---|
| Claude Code (Anthropic, model Claude Opus 5.5) | Pair-programming the pipeline, model, dashboard, tests and documentation; design review of the visual identity |
| GitHub Copilot (Copilot SDK in VS Code) | Updating the README test record and demo script |

*Teammates: add any other assistant you used (ChatGPT, Copilot, Gemini…) to this table before submission.*

**External APIs and services**

| Service | When | Notes |
|---|---|---|
| Google Sheets CSV export | Once, to download the challenge dataset | `scripts/fetch_data.py`; the CSV is committed, so the app never calls it |
| Google Fonts | When the dashboard loads in a browser | Bricolage Grotesque, Instrument Sans, Hind Siliguri; falls back to system fonts offline |

Moshari makes **no API calls while forecasting**: no weather API and no LLM. All inference runs locally.

## License

MIT
