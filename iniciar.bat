@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem Usa o Python do venv do treino (no D:) se existir; senao, o Python normal.
set "PY=python"
if exist "D:\espantalho_treino\venv\Scripts\python.exe" set "PY=D:\espantalho_treino\venv\Scripts\python.exe"
echo Python: %PY%

"%PY%" -c "import fastapi, uvicorn, multipart, requests, yaml, cv2, onnxruntime, serial, paho.mqtt" 2>nul
if errorlevel 1 (
  echo Instalando dependencias...
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 ( echo. & echo Falhou a instalacao. & pause & exit /b 1 )
)

start "VIGIA - webapp" "%PY%" -m uvicorn webapp.servidor:app --port 8000
timeout /t 3 /nobreak >nul
start "VIGIA - processador" "%PY%" -m processador
timeout /t 2 /nobreak >nul
start "" http://localhost:8000
echo.
echo Dashboard: http://localhost:8000   (feche as 2 janelas pretas pra desligar)
timeout /t 5 >nul
