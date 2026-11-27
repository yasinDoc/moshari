# 7-minute video script (onsite final)

One uncut take: screen and voice, no slides, no edits. It tells one story, a health officer's week from "something is coming" to "messages sent", and covers all five Phase 2 modules (resource allocation, hospital overflow routing, the vector control simulator, dispatch notices and offline mode) plus the Ward map, the Weekly briefing, the Peak shortcut and the English / Bangla switch. Rehearse until it fits in 6:45, so there's slack.

**Record from the final commit.** The brief penalises a commit hash mismatch, so pull `main`, note the hash (`git log -1 --format=%h`) and record only from that checkout. Ask the team not to merge anything until the take is done.

## Before you press record

1. Start the app and open every page once, so nothing loads on camera:
   ```powershell
   .venv\Scripts\streamlit run app.py
   ```
2. Open **Live outlook** once *with* the internet on, so its weather is cached for the offline part.
3. Full-screen browser at 100% zoom on a 1440px-wide or larger screen, sidebar open. Close other tabs, turn on Do Not Disturb, use a headset mic.
4. Sidebar: **ভাষা / Language: English**, click **Early** (Forecast issued 02 Jun 2025), **Weeks ahead: 3**, **Alert sensitivity: Cautious**, City corporations empty, **Offline mode** off.
5. Page controls: **Resources** stock 70%, crews 40; **Hospital beds** surge +0%; **Simulator** 30 crews, effect 20%, max 4 per ward, Plan: Recommended; **Dispatch** Send to: High risk, Language: English; **Weekly briefing** stock 70%, crews 40, surge +0%.
6. Practise setting **Forecast issued** to 07 Aug 2023 (drag close, fine-tune with the arrow keys). Getting back is one click on **Early**.
7. Record with Xbox Game Bar (`Win + Alt + R`) or OBS.

## Script

### Act 1: the warning (0:00 to 1:00)

| Time | On screen | Say |
|---|---|---|
| 0:00 | **Overview**, hold still | "Every monsoon, Dhaka's hospitals learn about dengue the same way: when patients arrive. Moshari, Bangla for mosquito net, learns about it three weeks earlier, ward by ward." |
| 0:12 | Point at the red alert line | "It's 2 June 2025. Before I've clicked anything, Moshari tells me the problem: 25 wards short on saline, 24 on test kits, 12 spraying crews short." |
| 0:25 | Point at the stat tiles | "In three weeks, 26 of 60 wards will be High risk and 399 cases are coming. Gazipur is hardest hit. This is the round-one forecast, now driving everything else." |
| 0:40 | Click **Ward map** | "The same risk on real ward outlines. The map ships inside the app with no map tiles, so it works offline. The data has no coordinates, so positions are illustrative, and the page says so." |

### Act 2: plan the response (1:00 to 4:10)

| Time | On screen | Say |
|---|---|---|
| 1:00 | Click **Resources** | "Module one: who gets the supplies. Every forecast case becomes demand: 2.38 saline bags, 1.16 test kits and 0.3 beds, fitted from the onsite data with an R-squared above 0.98, and always rounded up." |
| 1:20 | Point at the deficit list | "We only have 70% of what's needed. Moshari ranks wards by risk times population density and fills them top-down. Twenty-five wards come up short, and not one of them is High risk." |
| 1:35 | Drag stock to 30%, then back to 70% | "Cut stock to 30% and 47 wards go short, and the riskiest are still first in line. Crews follow the same order: every High ward gets one before anyone gets two." |
| 1:55 | Click **Hospital beds**; set **Forecast issued: 07 Aug 2023** | "Module two: where overflow patients go. The data has no bed counts, so each ward's capacity is its own 90th-percentile bed demand from 2016 to 2023. Let's jump to a real peak, 7 August 2023." |
| 2:15 | Point at the city cards, then the transfers | "Dhaka North needs 57 beds and has 56. One patient moves from Ward 1 to Ward 9, the least-loaded ward with a free bed. Patients never cross city lines." |
| 2:35 | Point at the red rows; drag **Surge beds per ward** to +30% | "Five patients still have nowhere to go. That's the honest answer, in red. Add 30% surge beds and seven patients move: nobody is left without a bed." |
| 2:55 | Surge back to +0%; click **Early**; click **Simulator** | "Module three: where spraying actually pays off. One click back to 2 June. Each crew removes 20% of a ward's breeding signal, with diminishing returns, capped at 75%." |
| 3:15 | Point at the totals card | "Then the forecast re-runs, with a model built so a crew can never make things worse. Thirty crews prevent about 220 cases over the next month: 48 in week three, 142 in week four." |
| 3:35 | Point at the chart and the ROI list | "The effect grows, because breeding stopped today prevents cases weeks later. Best buy: Dhaka North Ward 12, about 9 cases per crew. In the dry season Moshari keeps crews in reserve instead." |
| 3:55 | Click **Peak** in the sidebar | "And this is the season's worst week, picked by the model itself: 9 June, 60 wards High, 80 patients with no bed. This is what early warning is for." |

### Act 3: act on it (4:10 to 5:45)

| Time | On screen | Say |
|---|---|---|
| 4:10 | Click **Early**, then **Dispatch** | "Module four: the plan becomes a message. Dhaka South Ward 4 is top priority this week." |
| 4:20 | **SMS** tab, then **WhatsApp** | "The SMS always fits one 160-character message: risk, cases, saline, kits, beds and crews against what's needed. WhatsApp gets the formatted version with a do-now list." |
| 4:38 | Dispatch **Language: বাংলা**; show the SMS | "Ward officers read Bangla, so one click switches every notice. Bangla SMS use Unicode, so we cap them at two parts, and shortages are never cut." |
| 4:52 | **English**; **Brief** tab; scroll to **Send them all** | "The commissioner gets a one-page printable brief. All 26 High wards download as one zip, and the same notices are in the exports folder. Fixed templates: no AI, no internet, the same text every time." |
| 5:12 | Click **Weekly briefing** | "And this is the whole system in four sentences for the city health officer: 26 wards High. Approve 12 more crews. Release 296 saline bags and 148 test kits. No transfers needed. One button, one-page PDF." |
| 5:32 | Sidebar **ভাষা / Language: বাংলা**, then back to **English** | "And the whole dashboard speaks Bangla too, every page and the PDF, built for the people who'll actually use it." |

### Act 4: proof it holds up (5:45 to 7:00)

| Time | On screen | Say |
|---|---|---|
| 5:45 | Turn on **Offline mode**; open **Live outlook** | "Module five: no internet, no problem. Field offices lose connection, so I'm cutting it off. Live outlook is the only page that ever calls an API, and now it uses saved weather." |
| 6:00 | Click through **Resources**, **Hospital beds**, **Simulator**, **Dispatch** | "Everything else runs on this laptop. Our offline check starts the real app with the internet blocked: 11 of 11 pages pass, and 1,400 automated tests run on every push." |
| 6:20 | **Model accuracy**, stat tiles | "And the forecast is honest. Trained on 2016 to 2023 and tested on 2024 and 2025, which it never saw: off by about one case per ward per week, 17% better than the best simple rule, with the alert out before the season's first high-risk week in 90% of ward-seasons." |
| 6:45 | Sidebar **Model ready** card, hold | "Moshari: from forecast to saline, beds, crews and a message in Bangla, before dengue reaches the hospital." |

The **Say** column is about 720 words: about 5 minutes 30 seconds at a calm 130 words a minute, which leaves about 1 minute 15 seconds for clicks and pauses. Pause for a second after the Weekly briefing's four sentences: it is the climax.

## If something goes wrong

- **A page is slow to load:** keep talking about what's on screen. Don't cut the video.
- **Live outlook says no weather is cached:** that is the offline message working. Say "with nothing cached it says so clearly, and every other page still works", then move on.
- **The numbers on screen differ from the script:** the sidebar or a page control isn't at its setting. Read what is on screen; don't stop.
- **You run past 7:00:** drop the 1:35 stock-slider step first, then the 3:55 Peak step, then the 0:40 Ward map step.
