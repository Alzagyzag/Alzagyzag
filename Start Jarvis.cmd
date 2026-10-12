@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python local_launcher.py
) else (
  py -3 local_launcher.py
)
if errorlevel 1 (
  echo Install Python 3.12 or newer from https://www.python.org/downloads/
  echo Enable Python on PATH during installation.
  pause
)
