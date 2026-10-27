@echo off
rem Double-click to start the Trader UI. Data lives in C:\Janak\Git\trading\trader
rem (the same folder you use with Claude Code, so both see the same plan and orders).
if not exist "C:\Janak\Git\trading" mkdir "C:\Janak\Git\trading"
cd /d "C:\Janak\Git\trading"
python "%~dp0server.py" --workdir "C:\Janak\Git\trading"
pause
