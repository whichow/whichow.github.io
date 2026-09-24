@echo off
setlocal
set "COMFY=%~1"
if "%COMFY%"=="" set "COMFY=%CD%"

set "PY=%COMFY%\venv\Scripts\python.exe"
if exist "%COMFY%\python_embeded\python.exe" set "PY=%COMFY%\python_embeded\python.exe"
if not exist "%PY%" (
  echo ERROR: Could not find ComfyUI Python.
  echo Usage: launch_h3_1gb.bat D:\path\to\ComfyUI
  exit /b 2
)

echo Starting ComfyUI with 1 GB VRAM reserved...
"%PY%" "%COMFY%\main.py" --reserve-vram 1
endlocal
