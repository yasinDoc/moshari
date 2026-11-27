# 7-minute video script (onsite final)

One uncut take: screen and voice, no slides, no edits. It covers all five Phase 2 modules (resource allocation, hospital overflow routing, the vector control simulator, dispatch notices and offline mode), plus the Ward map, Bangla notices and the Weekly briefing. Rehearse until it fits in 6:45, so there's slack.

**Record from the final commit.** The brief penalises a commit hash mismatch, so pull `main`, note the hash (`git log -1 --format=%h`) and record only from that checkout.

## Before you press record

1. Start the app and open every page once, so nothing loads on camera:
   ```powershell
   .venv\Scripts\streamlit run app.py
   ```
2. Open **Live outlook** once *with* the internet on, so its weather is cached for the offline part at the end.
3. Use a full-screen browser at 100% zoom on a 1440px-wide or larger screen, with the sidebar open. Close other tabs and turn on Do Not Disturb.
4. In the sidebar, click **Early** (Forecast issued: 02 Jun 2025), set **Weeks ahead: 3** and **Alert sensitivity: Cautious**, leave City corporations empty, and make sure **Offline mode** is off.
5. Reset the page controls: **Resources** stock 70%, crews 40; **Hospital beds** surge +0%; **Simulator** 30 crews, effect 20%, max 4 per ward, Plan: Recommended; **Dispatch** Send to: High risk, Language: English; **Weekly briefing** stock 70%, crews 40, surge +0%.
6. Practise moving **Forecast issued** to 07 Aug 2023 (drag the handle close, then fine-tune with the arrow keys). Getting back is one click on **Early**.
7. Record with Xbox Game Bar (`Win + Alt + R`) or OBS, using a headset mic in a quiet room.

## Script

| Time | On screen | Say |
|---|---|---|
| 0:00 | **Overview**, top of page | "This is Moshari, Bangla for mosquito net. In the first round it forecast dengue for 60 wards in Dhaka, Chattogram, Gazipur and Narayanganj, two to four weeks ahead. Today we turned that forecast into operations: who gets the saline, where overflow patients go, where spraying crews make the most difference, and the notices that tell officers what to do." |
| 0:25 | Point at the red alert line, then the stat tiles | "It's 2 June 2025, early in the season, looking three weeks ahead. 26 wards are expected to reach High risk. The red line already tells the officer the problem: 25 wards short on saline, 24 on test kits, 12 crews short." |
| 0:40 | Click **Ward map** | "The same risk on real ward outlines. The map ships inside the app, with no map tiles, so it works offline. The data has no coordinates, so positions are illustrative, and the page says so." |
| 0:55 | Click **Resources** | "Module one: resource allocation. Each forecast case becomes demand using ratios we fitted from the onsite data: 2.38 saline bags, 1.16 test kits and 0.3 beds per case, with an R-squared above 0.98. Demand is always rounded up." |
| 1:15 | Point at the stock slider (70%) and the deficit list | "Stock covers 70% of demand. Wards are served in priority order: risk, scaled by population density. The 35 highest-priority wards get everything; the other 25 are flagged with their exact gap, and none of them is High risk." |
| 1:35 | Drag the stock slider to 30%, then back to 70% | "At 30%, 47 wards go short, but the riskiest, densest wards are still served first. Crews follow the same order: every High ward gets one crew before any ward gets a second. With 40 crews and 52 needed, 12 wards are one short." |
| 2:00 | Click **Hospital beds**; set **Forecast issued: 07 Aug 2023** | "Module two: hospital overflow. The data has no bed counts, so each ward's capacity is its 90th-percentile weekly bed demand over 2016 to 2023. Let's jump to a busy week, 7 August 2023." |
| 2:20 | Point at the city cards, then the transfers table | "Each city card shows beds, demand and headroom. Dhaka North needs 57 beds and has 56, so one patient moves from Ward 1 to Ward 9, the least-loaded ward with a spare bed. Patients never cross city boundaries; we test that on 150 random weeks." |
| 2:45 | Point at the red rows, then drag **Surge beds per ward** to +30% | "Five patients still have no bed, in red. If wards open 30% more corridor beds, seven patients move and nobody is left without a bed." |
| 3:00 | Set surge back to +0%; click **Early** in the sidebar; click **Simulator** | "Module three: the vector control simulator. Back to 2 June with one click. Each crew removes 20% of a ward's recent breeding rain signal, with diminishing returns, capped at 75%." |
| 3:20 | Point at the controls, then the totals card | "Then the models re-run. A dedicated simulation model has monotone constraints, so adding a crew can never raise a forecast. 30 crews placed where they prevent the most cases: 48 fewer cases at three weeks, 142 fewer at four." |
| 3:45 | Point at the 2/3/4-week chart and the ROI ranking | "The effect grows with time, because breeding removed today stops later cases. Dhaka North Ward 12 is the best buy, about 9 cases per crew. The 20% is an assumption, so it's a slider." |
| 4:05 | Click **Dispatch** (Send to: **High risk**); **DSCC Ward 04** is previewed | "Module four: dispatch. Everything we planned becomes a message. Dhaka South Ward 4 is this week's top-priority ward." |
| 4:15 | **SMS** tab, then **WhatsApp** tab | "The SMS always fits one 160-character message: risk, cases, saline, kits and beds allocated against required, crews and the action. WhatsApp adds formatting for the ward officer." |
| 4:35 | Click **বাংলা** under Language; show the SMS | "One click switches every notice to Bangla. Bangla SMS use Unicode, so they're held to two parts, and supplies and shortages are never cut." |
| 4:50 | Click **English**; **Brief** tab, then scroll to **Send them all** | "The commissioner brief is one printable page per ward. All 26 High wards download as one zip or one printable file, and the same notices are in the exports folder. Plain templates, no AI, no internet." |
| 5:15 | Click **Weekly briefing** | "And this is the whole system as one decision for the city health officer: 26 wards High risk, approve 12 more crews, release 296 saline bags and 148 test kits for 25 short wards, no transfers needed. One button makes it a one-page PDF." |
| 5:40 | Turn on **Offline mode** in the sidebar, then open **Live outlook** | "Module five: offline. Field offices lose connectivity. Live outlook is the only page that ever calls an API, and now it uses the last cached weather." |
| 5:55 | Click through **Resources**, **Hospital beds**, **Simulator**, **Dispatch** | "Everything else runs locally from the saved model. Our offline check starts the real app with the internet cut off: 11 out of 11 pages pass, and 1,374 tests run on every push." |
| 6:20 | **Model accuracy**, stat tiles | "And the forecast underneath is honest: trained on 2016 to 2023, tested on 2024 and 2025, it misses by about one case per ward per week, 17% better than the best simple rule." |
| 6:40 | Sidebar **Model ready** card | "Moshari: from forecast to saline, beds, crews and a message, before dengue reaches the hospital." |

The **Say** column is about 720 words: about 5 minutes 30 seconds at a calm 130 words a minute, which leaves about 1 minute 15 seconds for clicks and pauses.

## If something goes wrong

- **A page is slow to load:** keep talking about what's on screen. Don't cut the video.
- **Live outlook says no weather is cached:** that is the offline message working. Say "with nothing cached it says so clearly, and every other page still works", then move on.
- **The numbers on screen differ from the script:** the sidebar or a page control isn't at its setting. Read what is on screen; don't stop.
- **You run past 7:00:** drop the 1:35 stock-slider step first, then the 2:45 surge step, then the 0:40 Ward map step.
