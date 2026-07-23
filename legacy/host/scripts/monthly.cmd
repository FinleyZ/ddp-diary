@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-journal.ps1" -Job monthly
exit /b %ERRORLEVEL%
