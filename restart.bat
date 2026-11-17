@echo off
rem Restarts the camera server in the background (restart Babble afterwards so it reconnects).
powershell -NoProfile -Command "try { Invoke-RestMethod http://127.0.0.1:8079/quit -Headers @{'X-BabbleCamBridge'='1'} -TimeoutSec 3 | Out-Null } catch { }; Start-Sleep 2"
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0bridge\server.py"
