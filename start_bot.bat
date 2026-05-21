@echo off
title TOP Bot
cd /d "C:\Users\Lenovo\Documents\discord_arman\bot"
:loop
python main.py
echo Bot stopped. Restarting in 5 seconds...
timeout /t 5
goto loop
