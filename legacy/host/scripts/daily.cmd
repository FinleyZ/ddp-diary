@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-journal.ps1" -Job daily
exit /b %ERRORLEVEL%
