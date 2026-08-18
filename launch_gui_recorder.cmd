@echo off
rem Double-click launcher for the interactive RTSP recorder GUI.
powershell -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0interactive_recorder_gui.ps1"
