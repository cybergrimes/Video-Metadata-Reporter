@echo off
rem Double-click to run. Keep this file, Run-MediaReport.ps1 and media_report.py in the same folder.
rem You can also drag one or more folders onto this file to scan them.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-MediaReport.ps1" %*
