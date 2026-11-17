@echo off
rem NOTE: Fully vibe coded - written by an AI (Claude). The repo owner has no programming knowledge.
rem Stops the camera server.
powershell -NoProfile -Command "try { Invoke-RestMethod http://127.0.0.1:8079/quit -Headers @{'X-BabbleCamBridge'='1'} -TimeoutSec 3 | Out-Null; 'Stopped.' } catch { 'Server was not running.' }"
timeout /t 2 >nul
