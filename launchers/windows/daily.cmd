@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" -Job daily
exit /b %ERRORLEVEL%
