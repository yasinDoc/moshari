# 3-minute demo script (round one)

> Kept for the record: this is the preliminary-round script. The onsite final uses [video_script.md](video_script.md).

One uncut take: screen and voice, no slides, no edits. Rehearse until it fits in 2:45, so there's slack.

## Before you press record

1. Start the app and open every page once, so nothing loads on camera:
   ```powershell
   .venv\Scripts\streamlit run app.py
   ```
2. Use a full-screen browser at 100% zoom on a 1440px-wide or larger screen, with the sidebar open. Close other tabs and turn on Do Not Disturb.
3. In the sidebar, set **Forecast issued: 02 Jun 2025**, **Weeks ahead: 3**, **Alert sensitivity: Cautious**, and leave City corporations empty.
4. On **Ward forecast**, make sure all three what-if sliders are back at their defaults.
5. Record with Xbox Game Bar (`Win + Alt + R`) or OBS, using a headset mic in a quiet room.

## Script

| Time | On screen | Say |
|---|---|---|
| 0:00 | **Overview**, top of page | "This is Moshari, Bangla for mosquito net. It forecasts dengue for each of 60 wards in Dhaka, Chattogram, Gazipur and Narayanganj, two to four weeks ahead, from weather." |
| 0:15 | Point at the four stat tiles | "It's 2 June 2025, the start of the season. Looking three weeks ahead, 26 wards are expected to hit high risk, and the cautious setting puts 34 more on watch, and 2 wards are on Critical watch. Gazipur is the hardest-hit city." |
| 0:28 | Point at the ward tiles, hover one tile | "Every tile is a ward, coloured by risk, showing expected cases. Hovering shows the details: the 80% range, what actually happened, and the response. The red rings are early alerts: wards whose likely upper range already reaches High." |
| 0:45 | Drag **Forecast issued** back to May, then return it to 2 June | "Everything is computed live. Moving the week re-runs the model, using only data available on that Monday." |
| 0:58 | Scroll to **Send teams here first**, then scroll back up and **click the CCC W01 tile** (Chattogram) | "This list ranks wards by urgency, with the response for each. Any tile opens that ward. Let's open Ward 01 in Chattogram." |
| 1:05 | **Ward forecast**: hero card and Outlook | "CCC Ward 01: High risk, about 10 cases, likely between 5 and 15. There's a 79% chance of High and a 20% chance of Critical, so it's on Critical watch. The action is targeted vector control this week." |
| 1:22 | Point at **Why**, then the **Rain and cases** chart | "Why? Heavy rain in early June. Rain takes two to four weeks to turn into cases, so the model uses rainfall lags for each ward. Rainfall multiplies expected cases by about four and a half." |
| 1:40 | Move the **Rainfall** what-if slider to ×2 | "What if it had rained twice as much? Moshari rebuilds the lag features and re-runs the model: this ward would go Critical." |
| 1:52 | **Live outlook** | "This is today's real weather from Open-Meteo, plus its 14-day rain forecast, for all five cities in one cached request. The rain forecast cuts our 4-week error by 9%. It's dry season, so every ward is low, which is the right answer for November." |
| 2:10 | **Model accuracy**: stat tiles | "We tested honestly: trained on 2016 to 2023, tested on 2024 and 2025, which the model never saw. It misses by about one case per ward per week, 17% better than the best simple rule." |
| 2:25 | **Catching outbreak weeks** card | "For early warning, missing an outbreak is the worst mistake. Our outbreak-probability models catch 70% of Critical weeks, against 28% from expected cases alone, and the cautious alert rule was on time for 90% of season onsets." |
| 2:38 | **Why lagged rain** chart | "And the data backs the biology: cases follow rain from three weeks earlier most closely." |
| 2:45 | Sidebar **Model ready** card | "It runs on a laptop from a saved model, with almost no API calls. Moshari: catching dengue before it reaches the hospital." |

## If something goes wrong

- **A page is slow to load:** keep talking about what's on screen. Don't cut the video.
- **Live outlook is offline:** it shows a clear message, so say "live mode needs one request; everything else runs offline" and move on.
- **You run past 3:00:** drop the 0:45 date-slider step first.
