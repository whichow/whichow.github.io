@echo off
setlocal
set "COMFY=%~1"
if "%COMFY%"=="" set "COMFY=%CD%"

echo ComfyUI root: %COMFY%
if not exist "%COMFY%\custom_nodes" (
  echo ERROR: custom_nodes not found under %COMFY%
  exit /b 2
)

if exist "%COMFY%\custom_nodes\ComfyUI-KJNodes\.git" (
  echo Updating ComfyUI-KJNodes...
  git -C "%COMFY%\custom_nodes\ComfyUI-KJNodes" pull --ff-only
) else (
  echo Installing ComfyUI-KJNodes...
  git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes.git "%COMFY%\custom_nodes\ComfyUI-KJNodes"
)

set "PY=%COMFY%\venv\Scripts\python.exe"
if exist "%COMFY%\python_embeded\python.exe" set "PY=%COMFY%\python_embeded\python.exe"
if not exist "%PY%" (
  echo ERROR: Could not find ComfyUI Python. Pass the ComfyUI root as the first argument.
  exit /b 3
)

"%PY%" -m pip install -r "%COMFY%\custom_nodes\ComfyUI-KJNodes\requirements.txt"
echo.
echo KJNodes installed/updated.
echo Next:
echo   "%PY%" minimax-h3-rtx5080\scripts\check_env.py
echo   "%PY%" minimax-h3-rtx5080\scripts\install_sage_blackwell.py
endlocal
