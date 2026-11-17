@echo off
rem NOTE: Fully vibe coded - written by an AI (Claude). The repo owner has no programming knowledge.
rem Starts the camera server without a window (does nothing if it is already running).
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0bridge\server.py"
