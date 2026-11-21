# 3-minute demo script

One uncut take, screen + voice, no slides. Rehearse until it fits in 2:45. Start with the app already open at
http://localhost:8501 (first load takes a few seconds), sidebar on **02 Jun 2025**, look-ahead **3**.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Overview | "This is Moshari, Bangla for mosquito net. It forecasts dengue for each of 60 wards in Dhaka, Chattogram, Gazipur and Narayanganj, two to four weeks ahead, from weather." |
| 0:15 | Overview: point at the lede and the net | "It's the week of 2 June 2025. Moshari says 26 wards are heading for high risk three weeks from now, and tells the officer where to start. Each cell is a ward; colour is the risk tier; the number is expected cases." |
| 0:35 | Overview: drag the date slider back to May, then forward again | "Everything is computed live. If I move the forecast week, the model re-runs on only the data available that Monday." |
| 0:50 | Ward forecast: click CCC Ward 01 in the table | "Clicking a ward opens its forecast." |
| 0:55 | Ward forecast: hero + outlook strip | "High risk, about 10 cases expected, with an 80% range, and the response for that tier: larvicide and fogging this week. Two, three and four weeks out it climbs from Medium to Critical." |
| 1:15 | Ward forecast: rain now, cases later chart | "This is why: heavy rain in early June, inside the breeding window. Rain takes two to four weeks to become cases, so we compute rainfall lags per ward. The crosses are what really happened: 14 cases." |
| 1:35 | Ward forecast: drivers chart | "The drivers come straight from the model with TreeSHAP: rainfall multiplies expected cases by about four and a half." |
| 1:50 | Ward forecast: move rainfall slider to ×2 | "What if it had rained twice as much? Moshari rebuilds the lag features and re-runs the model: this ward goes to Critical." |
| 2:05 | Model accuracy | "We validated chronologically: trained on 2016 to 2023, tested on 2024 and 2025, which the model never saw. It's off by about one case per ward per week, 17% better than the best simple rule, with 83% of weeks in the right tier." |
| 2:25 | Model accuracy: breeding clock bar chart | "And the data backs the biology: cases track rain from three weeks earlier most closely." |
| 2:35 | Data | "Upload a newer weekly CSV here; it is validated before every page forecasts from it. Moshari runs locally with zero API calls, catching dengue before it reaches the hospital." |
