# Phase 2 tasks: 10-hour onsite final

We extend Moshari from *forecasting* to *operations*: how many saline bags, test kits and beds each ward needs, where overflow patients go, where spraying crews make the most difference, and the dispatch notices that tell officers what to do. Everything must keep working with the internet off.

**Split:** Yasin 50% · Samiya 25% · Ananya 25%. Each person owns separate files, so we never edit the same file at the same time.

| Who | Share | Owns |
|---|---|---|
| **Yasin** | 50% | New dataset and model, resource allocation engine (module 1), vector control simulator (module 3), offline mode (module 5), integration and deployment, the 7-minute video |
| **Samiya** | 25% | Hospital overflow routing (module 2), tests for allocation and routing, offline kill-switch check |
| **Ananya** | 25% | Dispatch notices (module 4), the `/exports` folder, ARCHITECTURE.md, README and AI disclosure |

---

## The onsite dataset (already checked)

Saved as `data/raw/dengue_onsite.csv` ([source sheet](https://docs.google.com/spreadsheets/d/1wAazQIRO-rzkrrlgD3YPcyyAPjMc1dN2pbr5rozA8BU/edit)). It's the Phase 1 data with three new columns: same 31,320 rows, 60 wards, 2016–2025, and the old columns are identical, so the trained model still applies.

| New column | Relation to `dengue_cases` | Use it for |
|---|---|---|
| `saline_bags_needed` | about **2.4 × cases** (exact for 96.5% of rows, r = 0.9998) | Saline demand |
| `diagnostic_kits_needed` | about **1.2 × cases** (exact for 88%, r = 0.9994) | Test-kit demand |
| `hospital_beds_required` | about **0.3 × cases** (exact for 96%, r = 0.990) | Bed demand |

- **Demand formulas (Yasin):** fit these ratios from the data (least squares on cases), store them in config, and apply them to *forecast* cases. Quote the fit in ARCHITECTURE.md; it's a strong answer to "where do your numbers come from?".
- **There is no bed-capacity column (Samiya):** estimate each ward's capacity as its **90th-percentile weekly `hospital_beds_required`** over 2016–2023, which comes to 1–4 beds per ward. That's its normal planning level; peak weeks need 8–12 beds, so routing has real overflow to move. Document this assumption.

---

## Rules for everyone

1. **Work on your own branch** (`yasin`, `samiya`, `ananya`). Pull `main` before you start and every time a pull request is merged:
   ```powershell
   git checkout <your-branch>; git pull origin main
   ```
2. **Start every commit message with `version-onsite-final:`**. The brief scores "continuous commit history (follow version-onsite-final for each commit)". Example:
   ```powershell
   git commit -m "version-onsite-final: add intra-city overflow routing"
   ```
3. **Commit small and often**, at least once an hour, so the history shows all three of us working through the day. One big commit at the end can score 0.
4. **Open a pull request into `main`** when a piece works. Yasin merges. Never push straight to `main`.
5. **No internet or LLM calls in core logic.** Forecasts, allocation, routing, simulation and dispatch templates must all run offline (module 5 is worth 15 points).
6. **Run the tests before every pull request:**
   ```powershell
   .venv\Scripts\python -m pytest
   ```
7. **Stick to the interfaces in the next section.** That's what lets us build in parallel.

---

## Shared interfaces (agree these first, 15 minutes at the start)

Yasin's allocation output is the input for Samiya's routing and Ananya's dispatch. Until it's ready, Samiya and Ananya can use a fake table with these columns.

**`allocate(...)` in `src/moshari/allocation.py` (Yasin) returns one row per ward:**

| Column | Meaning |
|---|---|
| `ward_id`, `city` | Ward and city corporation |
| `expected_cases`, `tier`, `p_crit` | From the forecast |
| `saline_bags_needed`, `diagnostic_kits_needed`, `hospital_beds_required` | Demand |
| `saline_bags_allocated`, `diagnostic_kits_allocated`, `hospital_beds_allocated` | After scarcity |
| `crews_assigned` | Spraying crews for this ward |
| `priority_score` | Higher = served first |
| `deficit_flag`, `deficit_note` | True if any demand isn't met, plus a short reason |

**`route_overflow(alloc_df, bed_capacity)` in `src/moshari/routing.py` (Samiya) returns:**
- `transfers`: `from_ward`, `to_ward`, `city`, `patients`
- `ward_summary`: `ward_id`, `city`, `beds_required`, `bed_capacity`, `net_deficit`, `received`, `sent`
- `city_summary`: `city`, `total_capacity`, `total_required`, `utilization`, `headroom`

**`dispatch.py` (Ananya) takes one row of the allocation and routing results and returns:**
- `sms(row)`: one plain-text SMS of 160 characters or fewer
- `whatsapp(row)`: a short message with a bit of formatting
- `brief_html(row)`: a printable one-page commissioner brief

---

## Yasin: 

### Y1. New dataset and model (first 1.5 hours)
- [x] Download the onsite dataset to `data/raw/dengue_onsite.csv` and check its columns (see "The onsite dataset" above).
- [ ] Update `config.py` and `data.validate()` for any new columns, and keep the old file working.
- [ ] Retrain with `python scripts/train.py`, check the hold-out metrics, and commit the new model and `artifacts/`.
- [x] Share the real column names (done: see "The onsite dataset").

### Y2. Constrained resource allocation engine (module 1, 15 pts) ✅ done: `allocation.py`, Resources page
File: `src/moshari/allocation.py`, plus a new page `ui/views/resources.py`.
- [x] **Demand per ward:** turn expected cases into saline bags, test kits and beds with the ratios fitted from the onsite data (about 2.4, 1.2 and 0.3 per case). Round up so demand is never understated, and keep the ratios in one config block.
- [x] **Scarcity:**
  - add an "Available regional stock" slider from 30% to 100% of total demand, and a "Total spraying crews" input
  - allocate in order of `priority_score` = risk (P(Critical), tier) × population density, so the riskiest and densest wards are served first
- [x] **Deficit warnings:** flag any ward that gets less than 100% of demand, with a live count and list.
- [x] **Crew assignment:** split crews by priority score, with a minimum of 1 for High and Critical wards while crews last.
- [x] **Page:** sliders, a table of demand against allocation, deficit alerts and totals.

### Y3. Vector control impact simulator (module 3, 10 pts) ✅ done: `simulation.py`, Simulator page
File: `src/moshari/simulation.py`, plus a new page `ui/views/simulator.py`.
- [x] Let officers choose wards and how many crews each gets.
- [x] **Model-driven counterfactual:** a crew reduces breeding, so lower that ward's effective breeding-window rainfall or recent cases by an effect size, then re-run the 2-, 3- and 4-week models. Reuse the what-if machinery in `service.py` (`Scenario`, `ward_outlook`). Document the effect size and why it was chosen.
- [x] Show the reduction in cases, beds and saline for each of the 2, 3 and 4 weeks ahead.
- [x] **ROI ranking:** cases prevented per crew, with a "best next crew" suggestion.

### Y4. Offline resilience and integration (module 5, 15 pts)
- [x] Check that every page and module runs with WiFi off (automated: `tests/test_offline.py`). Live outlook already falls back to cached weather; make sure nothing else calls the internet.
- [x] Add an "Offline mode" indicator, and an `MOSHARI_OFFLINE=1` switch that skips Open-Meteo entirely (plus a live sidebar toggle).
- [ ] Add the new pages to the sidebar in `app.py`, merge everyone's pull requests and keep CI green.
- [ ] Redeploy on Streamlit Cloud and check the live URL works.

### Y5. Video (10 pts)
- [ ] Record one uncut take of about 7 minutes, with voiceover and no slides, covering all 5 modules. Ananya writes the script.
- [ ] Record it from the **final commit**, because the brief penalises a commit hash mismatch.

---

## Samiya: 

### S1. Hospital overflow routing (module 2, 10 pts)
File: `src/moshari/routing.py`, plus a new page `ui/views/hospital.py`.
- [x] Take each ward's `hospital_beds_required` (from the allocation table) and its **bed capacity**. The dataset has none, so use each ward's 90th-percentile weekly `hospital_beds_required` over 2016–2023, as described in "The onsite dataset".
- [x] **Routing, strictly within the same city:**
  - wards over capacity send patients to wards with spare beds
  - start with the least loaded ward, ideally the nearest if ward numbers or neighbours are available, and stop when the overflow is placed or the city runs out of beds
- [x] Never route between cities. Add a test for this.
- [x] Output the three tables from the interface section: transfers, ward summary, city summary.
- [x] **Page:**
  - per-city cards with total beds, required beds, utilisation % and headroom
  - a table of transfers ("move 6 patients from DNCC Ward 12 to DNCC Ward 3")
  - wards still in deficit after routing, shown in red
- [x] Commit at least once an hour with the `version-onsite-final:` prefix.

### S2. Tests (shared quality)
File: `tests/test_routing.py`, plus tests for Yasin's allocation in `tests/test_allocation.py`.
- [x] **Routing:**
  - transfers never cross cities
  - total patients are conserved
  - no ward ends above capacity while its city still has headroom
- [x] **Allocation:**
  - allocated never exceeds stock
  - at 100% stock there are no deficits
  - at 30% stock the highest-priority wards are served first
  - crews add up to the total

### S3. Offline kill-switch check (supports module 5)
- [x] Turn WiFi off, restart the app and click through every page, including Live outlook, which should show its offline message.
- [x] Note anything that crashes and tell Yasin straight away.
- [x] Write the steps you followed into `docs/offline_check.md`, so we can repeat them in front of the judges.

---

## Ananya: 

### A1. Dispatch notices (module 4)
File: `src/moshari/dispatch.py`, plus a new page `ui/views/dispatch.py`.
- [x] **SMS:** 160 characters or fewer, for example: `MOSHARI DNCC-W12: HIGH risk, ~10 cases wk of 23 Jun. Saline 32/40, kits 9/12, beds 3/3. DEFICIT saline. Crews: 2. -DGHS`
- [x] **WhatsApp:** a short message with line breaks, covering predicted cases, allocated against required supplies, deficit alerts, assigned crews and the action to take.
- [x] **Commissioner brief (HTML, printable to PDF):**
  - one page per ward: header, risk and cases, a supplies table (required, allocated, gap), deficit warnings, crews, overflow transfers and the actions to take
  - add a "Print / Save as PDF" button
- [x] **Templates only.** No LLM or internet, so it works offline.
- [x] **Page:** pick a ward or "all High and Critical", preview all three formats, and download them.

### A2. `/exports` folder (part of 10 pts)
- [x] Write `scripts/export_dispatch.py` to generate sample files into `exports/` for the demo week:
  - `exports/sms/<ward>.txt`
  - `exports/whatsapp/<ward>.txt`
  - `exports/briefs/<ward>.html`
  - and at least one printed `exports/briefs/<ward>.pdf`
- [x] Commit the generated samples. The judges check the folder.

### A3. Documentation (part of 10 pts and the Q&A)
- [x] **ARCHITECTURE.md:** add Phase 2 to the data flow diagram (allocation, routing, simulation, dispatch), the allocation ratios and priority formula, the routing rules, the simulator's effect size, and the offline design. Keep it short.
- [x] **README:**
  - new pages
  - how to run the export script
  - the offline switch
  - the new dataset
  - Phase 2 in "Results at a glance"
- [x] **AI disclosure:** list every AI tool used today by all three of us.
- [x] **Video script:** write a 7-minute uncut script covering all 5 modules for Yasin, in the style of `docs/demo_script.md`.
- [x] **Q&A prep (30 pts):** write `docs/qa_prep.md` with likely judge questions and short answers. For example: why these supply ratios, how routing stays within a city, how the simulator is model-driven, what happens offline, model accuracy and validation.

---

## Timeline (10 hours)

| Time | Yasin | Samiya | Ananya |
|---|---|---|---|
| 0:00–0:30 | Agree interfaces, get the new dataset | Read `service.py` and `risk.py` | Read `service.py` and the UI pages |
| 0:30–2:00 | Y1 dataset and retrain | S1 routing logic on a fake table | A1 SMS and WhatsApp templates |
| 2:00–4:30 | Y2 allocation engine and page | S1 hospital page | A1 commissioner brief and dispatch page |
| 4:30–6:30 | Y3 simulator and page | S2 tests | A2 exports script and samples |
| 6:30–8:00 | Y4 integration, merge everything | S3 offline check, fix bugs | A3 ARCHITECTURE.md, README, AI disclosure |
| 8:00–9:00 | Redeploy, final fixes | Retest everything offline | Video script and Q&A prep |
| 9:00–10:00 | Record the 7-minute video from the final commit | Rehearse the Q&A | Rehearse the Q&A, final README check |

**Checkpoints:** a quick team check at **2:00, 4:30, 6:30 and 8:00**: what's merged, what's blocked.

---

## Done means

- [ ] All 5 modules work in the app and on the live URL
- [ ] The app runs with WiFi off, with no crashes
- [ ] The `exports/` folder has SMS, WhatsApp and printable brief samples
- [ ] ARCHITECTURE.md, README and the AI disclosure are updated
- [ ] Every commit starts with `version-onsite-final:`, and all three of us have commits through the day
- [ ] A 7-minute uncut video, recorded from the final commit
- [ ] Tests pass and CI is green
