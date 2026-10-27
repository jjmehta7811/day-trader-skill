# Trader UI

A local web page for the day-trader-skill tools. No command prompt needed after the first start.

- Start: double-click `run-ui.bat` (or `python trader-ui\server.py --workdir C:\Janak\Git\trading`).
- Open: http://127.0.0.1:8765 (opens by itself).
- Needs Python 3.8+, nothing to install. Runs only on your computer.
- Tabs follow the trade order: Find, Plan, Size & check, Monitor, Research, Settings.
- First time: Settings, put your name and email in the SEC box, keep Paper ON, Save.
- Then Find > "Download stock list" once.

It never places or approves orders. "Show order tickets" is read only; your yes still goes to Claude.
