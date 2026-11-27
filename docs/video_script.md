# 7-minute video script (onsite final)

One uncut take: screen and voice, no slides, no edits. It covers all five Phase 2 modules: resource allocation, hospital overflow routing, the vector control simulator, dispatch notices and offline mode. Rehearse until it fits in 6:45, so there's slack.

**Record from the final commit.** The brief penalises a commit hash mismatch, so pull `main`, note the hash (`git log -1 --format=%h`) and record only from that checkout.

## Before you press record

1. Start the app and open every page once, so nothing loads on camera:
   ```powershell
   .venv\Scripts\streamlit run app.py
   ```
2. Open **Live outlook** once *with* the internet on, so its weather is cached for the offline part at the end.
3. Use a full-screen browser at 100% zoom on a 1440px-wide or larger screen, with the sidebar open. Close other tabs and turn on Do Not Disturb.
4. In the sidebar, set **Forecast issued: 02 Jun 2025**, **Weeks ahead: 3**, **Alert sensitivity: Cautious**, leave City corporations empty, and make sure **Offline mode** is off.
5. Reset the page controls: **Resources** stock 70%, crews 40; **Hospital beds** surge +0%; **Simulator** 30 crews, effect 20%, max 4 per ward, Plan: Recommended; **Dispatch** Send to: High risk.
6. Practise moving **Forecast issued** from 02 Jun 2025 to 07 Aug 2023 and back: drag the handle close, then fine-tune with the arrow keys. It is the only fiddly move in the take.
7. Record with Xbox Game Bar (`Win + Alt + R`) or OBS, using a headset mic in a quiet room.

## Script

| Time | On screen | Say |
|---|---|---|
| 0:00 | **Overview**, top of page | "This is Moshari, Bangla for mosquito net. In the first round it forecast dengue for 60 wards in Dhaka, Chattogram, Gazipur and Narayanganj, two to four weeks ahead. Today we turned that forecast into operations: who gets the saline, where overflow patients go, where spraying crews make the most difference, and the notices that tell officers what to do." |
| 0:25 | Point at the stat tiles, then the ward tiles | "It's 2 June 2025, the start of the season, looking three weeks ahead. 26 wards are expected to reach High risk, and two are on Critical watch. Each tile is a ward, coloured by risk. The sidebar now follows an officer's working order: see the risk, allocate, place patients, deploy crews, notify." |
| 0:50 | Click **Resources** in the sidebar | "Module one: resource allocation. Each forecast case becomes demand using ratios we fitted from the onsite data: 2.38 saline bags, 1.16 test kits and 0.3 beds per case, with an R-squared above 0.98 for all three. Demand is always rounded up, so we never understate it." |
| 1:15 | Point at the stock slider (70%) and the deficit list | "Here regional stock covers 70% of total demand. Wards are served in priority order: risk, from the tier and the chance of High, scaled by population density. The 35 highest-priority wards get everything they need. The other 25 are flagged, each with its exact gap, like 'short 13 saline bags, 7 test kits'." |
| 1:40 | Drag the stock slider down to 30%, then back to 70% | "Drop stock to 30% and 47 wards go short, but the riskiest, densest wards are still served first. Crews follow the same order: every High ward gets one crew before any ward gets a second. With 40 crews and 52 needed, 12 wards are one crew short, and the page says so." |
| 2:05 | Click **Hospital beds**; in the sidebar set **Forecast issued: 07 Aug 2023** | "Module two: hospital overflow. The data has no bed counts, so each ward's capacity is its 90th-percentile weekly bed demand over 2016 to 2023, its normal planning level. Let's jump to a busy week, 7 August 2023." |
| 2:25 | Point at the city cards, then the transfers table | "Each city card shows beds, demand, utilisation and headroom. Dhaka North needs 57 beds and has 56. One patient moves from Ward 1 to Ward 9: the least-loaded ward with a spare bed, and ties go to the nearest ward. Patients never cross city boundaries. We test that on 150 random three-city weeks." |
| 2:55 | Point at the red rows, then drag **Surge beds per ward** to +30% | "Five patients still have no bed, shown in red. If wards open 30% more corridor or field beds, seven patients move and nobody is left without a bed. Extra beds are rounded down, so the plan never counts a bed that isn't there." |
| 3:20 | Set the slider back to +0%; set **Forecast issued** back to **02 Jun 2025**; click **Simulator** | "Module three: the vector control simulator. Back to 2 June. A spraying crew removes breeding sites, so in the model each crew removes 20% of a ward's recent breeding rain signal, with diminishing returns, capped at 75%." |
| 3:45 | Point at the controls, then the totals card | "Then the models re-run. A dedicated simulation model per horizon has monotone constraints, so adding a crew can never raise a forecast. With 30 crews placed where they prevent the most cases, we expect 48 fewer cases at three weeks, 399 down to 351, and 142 fewer at four weeks." |
| 4:15 | Point at the 2/3/4-week chart and the ROI ranking | "That's about 14 hospital beds and 114 saline bags saved at three weeks. The ranking shows cases prevented per crew. Dhaka North Ward 12 is the best buy, at about 9 cases per crew. The 20% effect is an assumption, so officers can change it here." |
| 4:40 | Click **Dispatch** (Send to: **High risk**); **DSCC Ward 04** is first in the list and already previewed | "Module four: dispatch notices. Everything we just planned becomes a message. This is Dhaka South Ward 4, the top-priority ward this week." |
| 4:55 | **SMS** tab, then the **WhatsApp** tab | "The SMS always fits one 160-character message: High risk, about 9 cases in the week of 23 June, saline, kits and beds allocated against required, two crews, and the action. The WhatsApp version adds formatting and line breaks for the ward officer." |
| 5:15 | **Brief** tab; point at **Print / Save as PDF** at the top of the brief | "The commissioner brief is one printable page per ward: risk and cases, a supplies table with the gap, deficit warnings, crews, overflow transfers and actions. It prints straight to PDF." |
| 5:35 | Scroll to **Send them all**; point at the two download buttons | "Officers can batch all 26 High wards into one zip or one printable file. The same notices are committed in the exports folder, made by one script. These are plain templates, with no AI model and no internet, so the same plan always gives the same text." |
| 5:55 | Turn on **Offline mode** in the sidebar, then open **Live outlook** | "Module five: offline. Field offices lose connectivity, so I'll switch the internet off. Live outlook is the only page that ever calls an API, and now it uses the last cached weather instead." |
| 6:15 | Click through **Resources**, **Hospital beds**, **Simulator** and **Dispatch** | "Allocation, routing, the simulator and dispatch all run locally from the saved model. Our test suite blocks network sockets and renders every page, so we know nothing reaches out." |
| 6:35 | **Model accuracy**, stat tiles | "And the forecast underneath is honest: trained on 2016 to 2023 and tested on 2024 and 2025, it misses by about one case per ward per week, 17% better than the best simple rule." |
| 6:50 | Sidebar **Model ready** card | "Moshari: from forecast to saline, beds, crews and a message, before dengue reaches the hospital." |

The **Say** column is about 780 words: about 6 minutes of speech at a calm 130 words a minute, which leaves about a minute for clicks and pauses.

## If something goes wrong

- **A page is slow to load:** keep talking about what's on screen. Don't cut the video.
- **Live outlook says no weather is cached:** that is the offline message working. Say "with nothing cached it says so clearly, and every other page still works", then move on.
- **The numbers on screen differ from the script:** the sidebar or a page control isn't at its setting. Read what is on screen; don't stop.
- **You run past 7:00:** drop the 1:40 stock-slider step first, then the 2:55 surge step.
