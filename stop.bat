@echo off
rem Stops the camera server.
powershell -NoProfile -Command "try { Invoke-RestMethod http://127.0.0.1:8079/quit -TimeoutSec 3 | Out-Null; 'Stopped.' } catch { 'Server was not running.' }"
timeout /t 2 >nul
