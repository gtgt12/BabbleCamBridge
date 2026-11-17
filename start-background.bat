@echo off
rem Starts the camera server without a window (does nothing if it is already running).
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0bridge\server.py"
