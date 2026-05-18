@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SidecarDeckAgent.ps1" %*
exit /b %ERRORLEVEL%
