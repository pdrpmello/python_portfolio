@echo off
rem Roda o scraper com o Python do virtualenv do projeto (msu_scraper\.venv).
cd /d "%~dp0"

".venv\Scripts\python.exe" main.py

exit
