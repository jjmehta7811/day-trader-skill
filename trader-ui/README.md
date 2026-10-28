# Trader UI

A local web page for the day-trader-skill tools. No command prompt needed after the first start.

- Start: double-click `run-ui.bat` (or `python trader-ui\server.py --workdir C:\Janak\Git\trading`).
- Open: http://127.0.0.1:8765 (opens by itself).
- Needs Python 3.8+, nothing to install. Runs only on your computer.
- Opens on "Guide": a step-by-step list with the time for each step and a button that jumps to the right card. The step for the current time is marked NOW.
- First time: Settings, put your name and email in the SEC box, keep Paper ON, Save.
- Then Find > "Download stock list" once.

It never places or approves orders. "Show order tickets" is read only; your yes still goes to Claude.

**Results tab:** after a Daily setups or Opening-range scan finishes, the UI opens a table with a checkbox per stock. Sort by clicking a heading, filter by setup or ticker, tick names, then Send to News, Save shortlist (trader/shortlist.json) or Copy tickers. Ticks are remembered per scan.
